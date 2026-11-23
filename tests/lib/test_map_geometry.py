import numpy as np
import pytest

from src.lib.map_geometry import (
    clip_polyline,
    coastline_water,
    join_lines,
    signed_area,
)

RECT = (0.0, 10.0, 0.0, 10.0)  # xmin, xmax, ymin, ymax


def _contains(poly, x, y):
    """Even-odd point-in-polygon test."""
    pts = np.asarray(poly)
    inside = False
    for (x1, y1), (x2, y2) in zip(pts, np.roll(pts, -1, axis=0)):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


class TestSignedArea:
    def test_anticlockwise_square_is_positive(self):
        assert signed_area([(0, 0), (1, 0), (1, 1), (0, 1)]) == pytest.approx(1.0)

    def test_clockwise_square_is_negative(self):
        assert signed_area([(0, 0), (0, 1), (1, 1), (1, 0)]) == pytest.approx(-1.0)


class TestJoinLines:
    def test_joins_two_halves_into_a_ring_even_if_one_is_reversed(self):
        a = [(0, 0), (1, 0), (1, 1)]
        b = [(0, 0), (0, 1), (1, 1)]  # runs the "wrong" way
        rings, chains = join_lines([a, b])
        assert len(rings) == 1 and not chains
        assert abs(signed_area(rings[0])) == pytest.approx(1.0)

    def test_directed_mode_keeps_direction(self):
        a = [(0, 0), (1, 0)]
        b = [(1, 0), (2, 0)]
        c = [(3, 0), (2, 0)]  # reversed: must not be joined in directed mode
        rings, chains = join_lines([a, b, c], directed=True)
        assert not rings
        lengths = sorted(len(ch) for ch in chains)
        assert lengths == [2, 3]


class TestClipPolyline:
    def test_line_crossing_the_rect(self):
        pieces = clip_polyline([(-5, 5), (15, 5)], RECT)
        assert len(pieces) == 1
        assert np.allclose(pieces[0], [(0, 5), (10, 5)])

    def test_line_outside_the_rect(self):
        assert clip_polyline([(-5, -5), (-1, 20)], RECT) == []

    def test_line_that_leaves_and_comes_back(self):
        pieces = clip_polyline([(-1, 2), (5, 2), (5, 20), (8, 20), (8, 5), (12, 5)], RECT)
        assert len(pieces) == 2


class TestCoastlineWater:
    def test_water_is_on_the_right_of_the_coastline(self):
        # Heading east: land to the north (left), sea to the south (right).
        water, islands = coastline_water([[(-2, 5), (12, 5)]], RECT)
        assert len(water) == 1 and not islands
        assert abs(signed_area(water[0])) == pytest.approx(50.0)
        assert _contains(water[0], 5, 2) and not _contains(water[0], 5, 8)

    def test_reversed_coastline_puts_the_sea_on_the_other_side(self):
        water, _ = coastline_water([[(12, 5), (-2, 5)]], RECT)
        assert _contains(water[0], 5, 8) and not _contains(water[0], 5, 2)

    def test_coastline_split_over_several_ways(self):
        ways = [[(-2, 5), (4, 5)], [(4, 5), (6, 3)], [(6, 3), (12, 3)]]
        water, _ = coastline_water(ways, RECT)
        assert len(water) == 1
        assert _contains(water[0], 8, 1) and not _contains(water[0], 8, 4)

    def test_bay_crossing_one_edge_twice(self):
        # A bay entering through the bottom edge: the sea is inside the "U".
        coast = [(3, -1), (3, 6), (7, 6), (7, -1)]
        water, _ = coastline_water([coast], RECT)
        total = sum(abs(signed_area(w)) for w in water)
        assert total == pytest.approx(4 * 6)
        assert any(_contains(w, 5, 3) for w in water)
        assert not any(_contains(w, 1, 3) for w in water)

    def test_island_inside_the_frame_means_sea_all_around(self):
        island = [(4, 4), (6, 4), (6, 6), (4, 6), (4, 4)]  # anticlockwise: land inside
        water, islands = coastline_water([island], RECT)
        assert len(water) == 1 and abs(signed_area(water[0])) == pytest.approx(100.0)
        assert len(islands) == 1

    def test_coastline_that_stops_inside_the_frame_is_rejected(self):
        assert coastline_water([[(-2, 5), (5, 5)]], RECT) is None

    def test_no_coastline_means_no_sea(self):
        assert coastline_water([], RECT) == ([], [])
