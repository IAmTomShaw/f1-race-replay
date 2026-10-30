import gzip
import json

import numpy as np
import pytest

from src.lib.georef import local_m_to_lonlat
from src.services import circuit_map as cm

LON0, LAT0 = -73.525, 45.505


def _outline_m(n=300, phase=0.0):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    r = 900 + 260 * np.cos(3 * t + phase) + 140 * np.sin(5 * t + 0.3) + 70 * np.cos(2 * t + 0.4)
    return np.column_stack([r * np.cos(t), 0.6 * r * np.sin(t)])


def _lonlat(local):
    lon, lat = local_m_to_lonlat(local[:, 0], local[:, 1], LON0, LAT0)
    return np.column_stack([lon, lat])


def _world(local, scale=0.1, rotation_deg=-20.0):
    th = np.radians(rotation_deg)
    c, s = np.cos(th), np.sin(th)
    e, n = local[:, 0] / scale, local[:, 1] / scale
    return np.column_stack([c * e + s * n + 1000.0, -s * e + c * n - 2000.0])


def _feature(cid, location, name, lonlat):
    return {
        "type": "Feature",
        "properties": {"id": cid, "Location": location, "Name": name},
        "geometry": {"type": "LineString", "coordinates": lonlat.tolist()},
    }


def _way(wid, tags, lonlat):
    return {"type": "way", "id": wid, "tags": tags,
            "geometry": [{"lon": float(lo), "lat": float(la)} for lo, la in lonlat]}


def _square(cx, cy, half):
    """Closed anticlockwise square in lon/lat around (cx, cy) metres from the origin."""
    local = np.array([[cx - half, cy - half], [cx + half, cy - half],
                      [cx + half, cy + half], [cx - half, cy + half], [cx - half, cy - half]])
    return _lonlat(local)


class TestNames:
    def test_normalise_name(self):
        assert cm.normalise_name("Montréal") == "montreal"
        assert cm.normalise_name("Spa-Francorchamps") == "spafrancorchamps"
        assert cm.normalise_name(None) == ""


class TestClassification:
    def test_areas(self):
        assert cm.classify_area({"natural": "water"}) == "water"
        assert cm.classify_area({"leisure": "park"}) == "green"
        assert cm.classify_area({"landuse": "forest"}) == "wood"
        assert cm.classify_area({"building": "yes"}) == "building"
        assert cm.classify_area({"building": "no"}) is None
        assert cm.classify_area({"shop": "bakery"}) is None

    def test_lines(self):
        assert cm.classify_line({"highway": "primary"}) == ("road_major", 11.0)
        assert cm.classify_line({"highway": "raceway"}) is None      # the replay draws the track
        assert cm.classify_line({"highway": "primary", "tunnel": "yes"}) is None
        assert cm.classify_line({"waterway": "river"})[0] == "water"


class TestParseOsm:
    def test_parses_ways_relations_and_coastlines(self):
        outer = _square(0, 0, 100)
        inner = _square(0, 0, 20)
        data = {"elements": [
            _way(1, {"natural": "water"}, _square(500, 0, 50)),
            _way(2, {"building": "yes", "building:levels": "4"}, _square(-300, 0, 10)),
            _way(3, {"highway": "primary"}, _lonlat(np.array([[-800, 0], [800, 0]]))),
            _way(4, {"highway": "raceway"}, _lonlat(np.array([[-800, 50], [800, 50]]))),
            _way(5, {"natural": "coastline"}, _lonlat(np.array([[-900, -500], [900, -500]]))),
            {
                "type": "relation", "id": 9, "tags": {"type": "multipolygon", "leisure": "park"},
                "members": [
                    # outer ring split over two ways, one of them reversed
                    {"type": "way", "role": "outer",
                     "geometry": [{"lon": lo, "lat": la} for lo, la in outer[:3]]},
                    {"type": "way", "role": "outer",
                     "geometry": [{"lon": lo, "lat": la} for lo, la in outer[2:][::-1]]},
                    {"type": "way", "role": "inner",
                     "geometry": [{"lon": lo, "lat": la} for lo, la in inner]},
                ],
            },
        ]}
        layers = cm.parse_osm(data)
        kinds = sorted(a.kind for a in layers.areas)
        assert kinds == ["building", "green", "water"]
        building = next(a for a in layers.areas if a.kind == "building")
        assert building.height_m == pytest.approx(4 * 3.2 + 1.0)
        park = next(a for a in layers.areas if a.kind == "green")
        assert len(park.outers) == 1 and len(park.inners) == 1
        assert [l.kind for l in layers.lines] == ["road_major"]   # raceway skipped
        assert len(layers.coastlines) == 1


class TestMatchCircuit:
    def test_picks_the_named_circuit(self):
        local = _outline_m()
        features = [
            _feature("xx-1", "Elsewhere", "Other", _lonlat(_outline_m(phase=1.0))),
            _feature("ca-1978", "Montreal", "Circuit Gilles-Villeneuve", _lonlat(local)),
        ]
        feature, fit = cm.match_circuit(features, _world(local), location="Montréal")
        assert feature["properties"]["id"] == "ca-1978"
        assert fit.residual_m < 2

    def test_falls_back_to_shape_when_the_name_is_unknown(self):
        local = _outline_m()
        features = [
            _feature("xx-1", "Elsewhere", "Other", _lonlat(_outline_m(phase=1.0))),
            _feature("ca-1978", "Montreal", "Circuit Gilles-Villeneuve", _lonlat(local)),
        ]
        feature, _ = cm.match_circuit(features, _world(local), location="Somewhere new")
        assert feature["properties"]["id"] == "ca-1978"

    def test_returns_none_when_nothing_fits(self):
        t = np.linspace(0, 2 * np.pi, 200, endpoint=False)
        oval = np.column_stack([1500 * np.cos(t), 300 * np.sin(t)])
        features = [_feature("xx-1", "Montreal", "Oval", _lonlat(oval))]
        assert cm.match_circuit(features, _world(_outline_m()), location="Montreal") is None


class TestCaching:
    def test_outline_dataset_is_cached_and_stale_copy_used_offline(self, tmp_path):
        calls = []

        def fetch(url):
            calls.append(url)
            return json.dumps({"features": [{"id": 1}]}).encode()

        assert cm.load_circuit_outlines(str(tmp_path), fetch=fetch) == [{"id": 1}]
        assert cm.load_circuit_outlines(str(tmp_path), fetch=fetch) == [{"id": 1}]
        assert len(calls) == 1

        path = tmp_path / "f1-circuits.geojson"
        old = 0
        import os
        os.utime(path, (old, old))

        def offline(url):
            raise OSError("no network")

        assert cm.load_circuit_outlines(str(tmp_path), fetch=offline) == [{"id": 1}]

    def test_osm_download_is_reused_when_it_covers_the_area(self, tmp_path):
        calls = []

        def post(url, data, timeout):
            calls.append(data["data"])
            return json.dumps({"elements": []}).encode()

        cm.fetch_osm("ca-1978", (45.50, -73.53, 45.51, -73.52), str(tmp_path), post=post)
        cm.fetch_osm("ca-1978", (45.501, -73.529, 45.509, -73.521), str(tmp_path), post=post)
        assert len(calls) == 1
        cm.fetch_osm("ca-1978", (45.40, -73.70, 45.60, -73.40), str(tmp_path), post=post)
        assert len(calls) == 2
        with gzip.open(tmp_path / "osm_ca-1978.json.gz", "rt") as f:
            assert json.load(f)["bbox"][0] <= 45.40

    def test_falls_back_to_the_second_overpass_server(self, tmp_path):
        urls = []

        def post(url, data, timeout):
            urls.append(url)
            if len(urls) == 1:
                raise OSError("429 Too Many Requests")
            return b'{"elements": []}'

        assert cm.fetch_osm("x", (1, 1, 2, 2), str(tmp_path), post=post) == {"elements": []}
        assert urls == list(cm.OVERPASS_URLS)

    def test_raises_when_every_server_fails(self, tmp_path):
        def post(url, data, timeout):
            raise OSError("offline")

        with pytest.raises(RuntimeError):
            cm.fetch_osm("x", (1, 1, 2, 2), str(tmp_path), post=post)


class TestRender:
    def _frame(self):
        return cm.MapFrame(0.0, 100.0, 0.0, 50.0, 200, 100)

    def test_paints_water_buildings_and_fades_the_edges(self):
        water = np.array([[5, 5], [45, 5], [45, 45], [5, 45], [5, 5]], dtype=float)
        building = np.array([[60, 20], [80, 20], [80, 30], [60, 30], [60, 20]], dtype=float)
        layers = cm.OsmLayers(areas=[cm.Area("water", [water]), cm.Area("building", [building])])
        img = cm.render_map(layers, self._frame(), px_per_m=1.0)
        assert img.size == (200, 100) and img.mode == "RGBA"
        r, g, b, a = img.getpixel((50, 50))        # centre of the water square
        assert (r, g, b) == cm.STYLE["water"] and a == 255
        r, g, b, _ = img.getpixel((140, 50))       # inside the building
        assert (r, g, b) == cm.STYLE["building"]
        assert img.getpixel((0, 0))[3] == 0          # faded corner

    def test_sea_from_coastline_and_island_hole(self):
        coast = np.array([[-10, 25], [110, 25]], dtype=float)  # sea to the south
        layers = cm.OsmLayers(coastlines=[coast])
        img = cm.render_map(layers, self._frame(), px_per_m=1.0, vignette=False)
        assert img.getpixel((100, 80))[:3] == cm.STYLE["water"]   # south (image bottom)
        assert img.getpixel((100, 20))[:3] == cm.STYLE["land"]    # north (image top)


class TestBuildTrackMap:
    def test_end_to_end_with_fake_network(self, tmp_path, monkeypatch):
        local = _outline_m()
        lonlat = _lonlat(local)
        features = {"features": [_feature("ca-1978", "Montreal", "Circuit Gilles-Villeneuve", lonlat)]}
        lake = _square(0, 0, 150)
        osm = {"elements": [_way(1, {"natural": "water"}, lake)]}
        monkeypatch.setattr(cm, "_http_get", lambda url, timeout=60: json.dumps(features).encode())
        monkeypatch.setattr(cm, "_http_post", lambda url, data, timeout: json.dumps(osm).encode())

        world = _world(local)
        result = cm.build_track_map(world, rotation_deg=30.0, rotation_center=(1000.0, -2000.0),
                                    location="Montréal", cache_dir=str(tmp_path), target_px=400)
        assert result is not None
        assert result.circuit_id == "ca-1978"
        assert result.residual_m < 2
        x0, x1, y0, y1 = result.bounds
        assert result.image.size[0] == 400 or result.image.size[1] == 400
        # The lake (at the circuit centre) must be drawn where the rotated world
        # frame says the circuit centre is.
        fit_centre = cm.rotate_about(np.array([[1000.0, -2000.0]]), (1000.0, -2000.0), 30.0)[0]
        w, h = result.image.size
        px = int((fit_centre[0] - x0) / (x1 - x0) * w)
        py = int((y1 - fit_centre[1]) / (y1 - y0) * h)
        assert result.image.getpixel((px, py))[:3] == cm.STYLE["water"]

    def test_returns_none_for_unknown_layout(self, tmp_path, monkeypatch):
        t = np.linspace(0, 2 * np.pi, 200, endpoint=False)
        oval = np.column_stack([1500 * np.cos(t), 300 * np.sin(t)])
        features = {"features": [_feature("xx", "Montreal", "Oval", _lonlat(oval))]}
        monkeypatch.setattr(cm, "_http_get", lambda url, timeout=60: json.dumps(features).encode())
        assert cm.build_track_map(_world(_outline_m()), location="Montreal",
                                  cache_dir=str(tmp_path)) is None
