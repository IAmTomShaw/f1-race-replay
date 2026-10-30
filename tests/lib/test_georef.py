import numpy as np
import pytest

from src.lib.georef import (
    fit_outline,
    local_m_to_lonlat,
    lonlat_to_local_m,
    resample_closed,
)

LON0, LAT0 = -73.525, 45.505  # roughly Montreal


def _circuit_m(n=400):
    """An asymmetric closed 'circuit' outline in metres (east, north)."""
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = 900 + 260 * np.cos(3 * t) + 140 * np.sin(5 * t + 0.3) + 70 * np.cos(2 * t + 0.4)
    return np.column_stack([r * np.cos(t), 0.6 * r * np.sin(t)])


def _to_lonlat(local_m):
    lon, lat = local_m_to_lonlat(local_m[:, 0], local_m[:, 1], LON0, LAT0)
    return np.column_stack([lon, lat])


def _to_world(local_m, scale=0.1, rotation_deg=37.0, offset=(5200.0, -800.0), mirrored=False):
    """Inverse of a known similarity transform: what FastF1 coordinates might look like."""
    th = np.radians(rotation_deg)
    c, s = np.cos(th), np.sin(th)
    e, n = local_m[:, 0] / scale, local_m[:, 1] / scale
    x = c * e + s * n
    y = -s * e + c * n
    if mirrored:
        y = -y
    return np.column_stack([x + offset[0], y + offset[1]])


class TestProjection:
    def test_lonlat_round_trip(self):
        lon = np.array([-73.53, -73.52, -73.51])
        lat = np.array([45.50, 45.505, 45.51])
        e, n = lonlat_to_local_m(lon, lat, LON0, LAT0)
        lon2, lat2 = local_m_to_lonlat(e, n, LON0, LAT0)
        assert np.allclose(lon, lon2) and np.allclose(lat, lat2)

    def test_one_millidegree_of_latitude_is_about_110_m(self):
        _, n = lonlat_to_local_m(LON0, LAT0 + 0.001, LON0, LAT0)
        assert n == pytest.approx(110.5, abs=0.5)


class TestResample:
    def test_returns_requested_count_and_ignores_closing_point(self):
        square = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], dtype=float)
        pts = resample_closed(square, 40)
        assert pts.shape == (40, 2)
        steps = np.hypot(*np.diff(np.vstack([pts, pts[:1]]), axis=0).T)
        assert np.allclose(steps, 1.0)

    def test_rejects_degenerate_outline(self):
        with pytest.raises(ValueError):
            resample_closed([[1, 1], [1, 1], [1, 1]], 10)


class TestFitOutline:
    @pytest.mark.parametrize("mirrored", [False, True])
    @pytest.mark.parametrize("reverse", [False, True])
    def test_recovers_known_transform(self, mirrored, reverse):
        local = _circuit_m()
        lonlat = _to_lonlat(local)
        world = _to_world(local, mirrored=mirrored)
        world = np.roll(world, 123, axis=0)       # the lap starts somewhere else
        if reverse:
            world = world[::-1]                    # and runs the other way round
        world = world[::2]                         # with a different point density

        fit = fit_outline(world, lonlat)

        assert fit.is_trustworthy()
        assert fit.residual_m < 2.0
        assert fit.mirrored is mirrored
        assert fit.scale == pytest.approx(0.1, rel=1e-3)
        # Every fitted point lands on the real outline (within its point spacing).
        lon, lat = fit.world_to_lonlat(world[:, 0], world[:, 1])
        e, n = lonlat_to_local_m(lon, lat, LON0, LAT0)
        real = np.column_stack(lonlat_to_local_m(lonlat[:, 0], lonlat[:, 1], LON0, LAT0))
        dists = np.min(np.hypot(e[:, None] - real[None, :, 0], n[:, None] - real[None, :, 1]), axis=1)
        assert dists.max() < 15.0

    def test_world_local_round_trip(self):
        local = _circuit_m()
        world = _to_world(local, mirrored=True)
        fit = fit_outline(world, _to_lonlat(local))
        e, n = fit.world_to_local(world[:, 0], world[:, 1])
        x, y = fit.local_to_world(e, n)
        assert np.allclose(x, world[:, 0]) and np.allclose(y, world[:, 1])

    def test_wrong_circuit_is_not_trusted(self):
        local = _circuit_m()
        t = np.linspace(0, 2 * np.pi, 300, endpoint=False)
        oval = np.column_stack([1500 * np.cos(t), 300 * np.sin(t)])
        fit = fit_outline(_to_world(local), _to_lonlat(oval))
        assert not fit.is_trustworthy()

    def test_needs_enough_points(self):
        with pytest.raises(ValueError):
            fit_outline(np.zeros((3, 2)), np.zeros((3, 2)))
