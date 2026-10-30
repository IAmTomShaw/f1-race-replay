"""
Real-world map underlay for the track, drawn from OpenStreetMap data.

Runs once per circuit, off the UI thread:

1. Find the circuit's real outline in the open f1-circuits dataset and fit
   the FastF1 reference lap to it (see ``src/lib/georef.py``).
2. Download the OpenStreetMap features around the circuit (water, parks,
   woods, buildings, roads...) from the Overpass API. The download is cached
   on disk, so each circuit is only fetched once.
3. Render those features into an image that lines up with the replay
   window's (rotated) world frame, so drawing the map costs one textured
   rectangle per frame.

No API key is needed. Map data is © OpenStreetMap contributors (ODbL) and
the attribution must stay visible whenever the map is shown.
"""

from __future__ import annotations

import gzip
import json
import math
import os
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

from src.lib.georef import GeoFit, fit_outline
from src.lib.map_geometry import coastline_water, join_lines, signed_area

ATTRIBUTION = "Map data © OpenStreetMap contributors"

CIRCUITS_URL = "https://raw.githubusercontent.com/bacinger/f1-circuits/master/f1-circuits.geojson"
OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
USER_AGENT = "f1-race-replay map underlay (+https://github.com/IAmTomShaw/f1-race-replay)"

CIRCUITS_MAX_AGE_S = 30 * 24 * 3600     # refresh the outline dataset monthly
HTTP_TIMEOUT_S = 180

MARGIN_FRACTION = 0.22                  # map extends this far past the track (x its size)
MIN_MARGIN_M = 300.0
TARGET_LONG_SIDE_PX = 2400              # final texture size along its long side
SUPERSAMPLE = 2                         # render at 2x, then downscale = anti-aliasing
VIGNETTE_START = 0.80                   # fade the map edge into the black background

# Dark, desaturated palette so the grey track and the team colours stay on top.
STYLE: Dict[str, Tuple[int, int, int]] = {
    "land": (18, 19, 22),
    "urban": (22, 23, 27),
    "farm": (22, 27, 22),
    "green": (20, 33, 25),
    "wood": (17, 31, 23),
    "scrub": (21, 30, 23),
    "sand": (35, 33, 26),
    "wetland": (19, 31, 30),
    "parking": (25, 26, 31),
    "aeroway": (28, 29, 34),
    "water": (15, 37, 60),
    "pier": (26, 27, 31),
    "building": (29, 31, 36),
    "building_edge": (37, 40, 47),
    "rail": (44, 46, 54),
    "path": (33, 36, 42),
    "road_minor": (44, 47, 55),
    "road_major": (57, 61, 72),
    "road_motorway": (68, 73, 87),
}

# Areas are painted in this order (later ones on top). Water is composited
# separately so islands inside rivers keep whatever was painted under them.
AREA_ORDER = ("urban", "farm", "sand", "wetland", "green", "scrub", "wood",
              "parking", "aeroway", "pier")

ROAD_CLASSES = {
    # highway=*: (style key, width in metres)
    "motorway": ("road_motorway", 16.0), "motorway_link": ("road_motorway", 8.0),
    "trunk": ("road_major", 13.0), "trunk_link": ("road_major", 7.0),
    "primary": ("road_major", 11.0), "primary_link": ("road_major", 6.0),
    "secondary": ("road_major", 9.0), "secondary_link": ("road_minor", 6.0),
    "tertiary": ("road_minor", 8.0), "tertiary_link": ("road_minor", 5.0),
    "unclassified": ("road_minor", 6.0), "residential": ("road_minor", 6.0),
    "living_street": ("road_minor", 5.0), "service": ("road_minor", 4.0),
    "pedestrian": ("path", 4.0), "track": ("path", 3.0), "road": ("road_minor", 5.0),
    "footway": ("path", 1.8), "path": ("path", 1.8), "cycleway": ("path", 1.8),
    "steps": ("path", 1.8), "bridleway": ("path", 1.8),
}
WATERWAY_WIDTHS = {"river": 20.0, "canal": 12.0, "stream": 4.0, "drain": 2.5, "ditch": 2.0}


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Area:
    kind: str
    outers: List[np.ndarray]
    inners: List[np.ndarray] = field(default_factory=list)
    height_m: Optional[float] = None    # buildings only (used by 3D views)


@dataclass
class Line:
    kind: str
    coords: np.ndarray
    width_m: float


@dataclass
class OsmLayers:
    """OpenStreetMap features. Coordinates are (n, 2) arrays in one frame."""

    areas: List[Area] = field(default_factory=list)
    lines: List[Line] = field(default_factory=list)
    coastlines: List[np.ndarray] = field(default_factory=list)

    def transformed(self, fn: Callable[[np.ndarray], np.ndarray]) -> "OsmLayers":
        return OsmLayers(
            areas=[Area(a.kind, [fn(r) for r in a.outers], [fn(r) for r in a.inners], a.height_m)
                   for a in self.areas],
            lines=[Line(l.kind, fn(l.coords), l.width_m) for l in self.lines],
            coastlines=[fn(c) for c in self.coastlines],
        )


@dataclass
class MapFrame:
    """Axis-aligned region of the rotated world frame covered by the map image."""

    x0: float
    x1: float
    y0: float
    y1: float
    width_px: int
    height_px: int

    @property
    def px_per_unit(self) -> float:
        return self.width_px / (self.x1 - self.x0)

    @property
    def bounds(self) -> Tuple[float, float, float, float]:
        return (self.x0, self.x1, self.y0, self.y1)


@dataclass
class TrackMapImage:
    """A rendered map plus where it goes in the rotated world frame."""

    image: Image.Image
    bounds: Tuple[float, float, float, float]   # (x0, x1, y0, y1)
    circuit_id: str
    circuit_name: str
    residual_m: float
    attribution: str = ATTRIBUTION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def default_cache_dir() -> str:
    """``<computed data folder>/maps`` (see Settings)."""
    try:
        from src.lib.settings import get_settings
        base = get_settings().computed_data_location or "computed_data"
    except Exception:
        base = "computed_data"
    path = os.path.join(base, "maps")
    os.makedirs(path, exist_ok=True)
    return path


def rotate_about(points, center: Tuple[float, float], rotation_deg: float) -> np.ndarray:
    """Rotate points about ``center`` exactly like the replay window does."""
    pts = np.asarray(points, dtype=float)
    if not rotation_deg:
        return pts.copy()
    th = math.radians(rotation_deg)
    c, s = math.cos(th), math.sin(th)
    x = pts[:, 0] - center[0]
    y = pts[:, 1] - center[1]
    return np.column_stack([x * c - y * s + center[0], x * s + y * c + center[1]])


def _http_get(url: str, timeout: float = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _http_post(url: str, data: Dict[str, str], timeout: float) -> bytes:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def normalise_name(text: Optional[str]) -> str:
    """'Montréal' -> 'montreal', 'Spa-Francorchamps' -> 'spafrancorchamps'."""
    if not text:
        return ""
    ascii_text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    return "".join(ch for ch in ascii_text.lower() if ch.isalnum())


# FastF1 location names that differ from the f1-circuits dataset.
LOCATION_ALIASES = {
    "yasisland": "yasmarina",
    "marinabay": "singapore",
    "montecarlo": "monaco",
    "mugello": "scarperiaesanpiero",
    "nurburgring": "nurburg",
    "losail": "lusail",
}


# ---------------------------------------------------------------------------
# Step 1: circuit outline + fit
# ---------------------------------------------------------------------------

def load_circuit_outlines(cache_dir: str,
                          fetch: Optional[Callable[[str], bytes]] = None) -> List[dict]:
    """Return the f1-circuits GeoJSON features (cached, refreshed monthly)."""
    fetch = fetch or _http_get
    path = os.path.join(cache_dir, "f1-circuits.geojson")
    fresh = os.path.exists(path) and (time.time() - os.path.getmtime(path)) < CIRCUITS_MAX_AGE_S
    if not fresh:
        try:
            raw = fetch(CIRCUITS_URL)
            json.loads(raw)  # validate before overwriting a good cache
            with open(path, "wb") as f:
                f.write(raw)
        except Exception as exc:
            if not os.path.exists(path):
                raise RuntimeError(f"could not download circuit outlines: {exc}") from exc
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f).get("features", [])


def _outline_lonlat(feature: dict) -> Optional[np.ndarray]:
    geom = feature.get("geometry") or {}
    coords = geom.get("coordinates")
    if geom.get("type") == "MultiLineString" and coords:
        coords = max(coords, key=len)
    if not coords or len(coords) < 8:
        return None
    return np.asarray(coords, dtype=float)[:, :2]


def _name_score(feature: dict, location: str, country: str, event_name: str) -> int:
    props = feature.get("properties") or {}
    loc = normalise_name(props.get("Location"))
    name = normalise_name(props.get("Name"))
    want = normalise_name(location)
    want = LOCATION_ALIASES.get(want, want)
    score = 0
    if want and loc and want == loc:
        score += 4
    elif want and loc and (want in loc or loc in want):
        score += 3
    for text in (country, event_name):
        t = normalise_name(text)
        if t and (t in name or (loc and loc in t)):
            score += 1
    return score


def match_circuit(features: Sequence[dict], reference_xy, location: str = "",
                  country: str = "", event_name: str = "") -> Optional[Tuple[dict, GeoFit]]:
    """
    Find the dataset outline that matches the reference lap and fit it.

    Name matches are tried first; if none of them fits (renamed venue,
    unexpected naming), every outline is tried by shape alone. Only a fit
    within ``DEFAULT_MAX_RESIDUAL_M`` is accepted.
    """
    scored = []
    for feature in features:
        outline = _outline_lonlat(feature)
        if outline is not None:
            scored.append((_name_score(feature, location, country, event_name), feature, outline))
    scored.sort(key=lambda item: -item[0])

    by_name = [item for item in scored if item[0] > 0]
    for _, feature, outline in by_name:
        fit = fit_outline(reference_xy, outline)
        if fit.is_trustworthy():
            return feature, fit

    best = None
    for _, feature, outline in scored:
        try:
            fit = fit_outline(reference_xy, outline)
        except ValueError:
            continue
        if fit.is_trustworthy() and (best is None or fit.residual_m < best[1].residual_m):
            best = (feature, fit)
    return best


# ---------------------------------------------------------------------------
# Step 2: OpenStreetMap download
# ---------------------------------------------------------------------------

def overpass_query(south: float, west: float, north: float, east: float) -> str:
    bbox = f"{south:.5f},{west:.5f},{north:.5f},{east:.5f}"
    return f"""[out:json][timeout:120][bbox:{bbox}];
(
  way["natural"="coastline"];
  way["natural"~"^(water|wood|scrub|heath|grassland|wetland|beach|sand)$"];
  relation["natural"~"^(water|wood|scrub|heath|grassland|wetland|beach|sand)$"];
  way["waterway"~"^(river|riverbank|canal|stream|dock|drain|ditch)$"];
  relation["waterway"~"^(riverbank|dock)$"];
  way["landuse"~"^(reservoir|basin|forest|grass|meadow|recreation_ground|village_green|cemetery|farmland|orchard|vineyard|allotments|residential|commercial|industrial|retail|railway|construction|brownfield)$"];
  relation["landuse"~"^(reservoir|basin|forest|grass|meadow|recreation_ground|village_green|cemetery|farmland|orchard|vineyard|allotments|residential|commercial|industrial|retail)$"];
  way["leisure"~"^(park|garden|golf_course|pitch|nature_reserve|recreation_ground)$"];
  relation["leisure"~"^(park|garden|golf_course|nature_reserve)$"];
  way["amenity"="parking"];
  way["aeroway"~"^(runway|taxiway|apron)$"];
  way["man_made"~"^(pier|breakwater|groyne)$"];
  way["building"];
  relation["building"];
  way["highway"];
  way["railway"~"^(rail|light_rail|tram|subway|narrow_gauge|monorail)$"];
);
out geom qt;"""


def _bbox_contains(outer: Sequence[float], inner: Sequence[float]) -> bool:
    s, w, n, e = outer
    s2, w2, n2, e2 = inner
    return s <= s2 and w <= w2 and n >= n2 and e >= e2


def fetch_osm(circuit_id: str, bbox: Sequence[float], cache_dir: str,
              post: Optional[Callable[[str, Dict[str, str], float], bytes]] = None) -> dict:
    """
    Return Overpass JSON covering ``bbox`` (south, west, north, east).

    Cached per circuit. A cached download is reused whenever it already
    covers the requested area, so the public Overpass servers are only hit
    the first time a circuit is opened.
    """
    post = post or _http_post
    path = os.path.join(cache_dir, f"osm_{circuit_id}.json.gz")
    if os.path.exists(path):
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                cached = json.load(f)
            if _bbox_contains(cached["bbox"], bbox):
                return cached["data"]
        except Exception:
            pass  # corrupt cache: download again

    # Round outwards (~1 km) so small differences between sessions reuse the cache.
    s, w, n, e = bbox
    grid = 0.01
    rounded = (math.floor(s / grid) * grid, math.floor(w / grid) * grid,
               math.ceil(n / grid) * grid, math.ceil(e / grid) * grid)

    query = overpass_query(*rounded)
    last_error: Optional[Exception] = None
    for url in OVERPASS_URLS:
        try:
            data = json.loads(post(url, {"data": query}, HTTP_TIMEOUT_S))
            break
        except Exception as exc:  # busy server, timeout, offline...
            last_error = exc
    else:
        raise RuntimeError(f"OpenStreetMap download failed: {last_error}")

    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump({"bbox": list(rounded), "fetched": int(time.time()), "data": data}, f)
    return data


# ---------------------------------------------------------------------------
# Step 3: parse
# ---------------------------------------------------------------------------

def _parse_height(tags: dict) -> Optional[float]:
    raw = tags.get("height") or tags.get("building:height")
    if raw:
        try:
            return float(str(raw).lower().replace("m", "").strip())
        except ValueError:
            pass
    levels = tags.get("building:levels")
    if levels:
        try:
            return float(levels) * 3.2 + 1.0
        except ValueError:
            pass
    return None


def classify_area(tags: dict) -> Optional[str]:
    """Style class for a closed way / multipolygon, or None to skip it."""
    if not tags or tags.get("area") == "no":
        return None
    if tags.get("building") and tags.get("building") != "no":
        return "building"
    natural = tags.get("natural")
    landuse = tags.get("landuse")
    leisure = tags.get("leisure")
    waterway = tags.get("waterway")
    if natural == "water" or landuse in ("reservoir", "basin") or waterway in ("riverbank", "dock"):
        return "water"
    if natural == "wood" or landuse == "forest":
        return "wood"
    if natural in ("scrub", "heath"):
        return "scrub"
    if natural in ("sand", "beach"):
        return "sand"
    if natural == "wetland":
        return "wetland"
    if natural == "grassland" or landuse in ("meadow", "farmland", "orchard", "vineyard", "allotments"):
        return "farm"
    if leisure in ("park", "garden", "golf_course", "pitch", "nature_reserve", "recreation_ground") \
            or landuse in ("grass", "recreation_ground", "village_green", "cemetery"):
        return "green"
    if tags.get("amenity") == "parking":
        return "parking"
    if tags.get("aeroway") == "apron":
        return "aeroway"
    if tags.get("man_made") in ("pier", "breakwater", "groyne"):
        return "pier"
    if landuse in ("residential", "commercial", "industrial", "retail", "railway",
                   "construction", "brownfield"):
        return "urban"
    return None


def classify_line(tags: dict) -> Optional[Tuple[str, float]]:
    """(style class, width in metres) for a line feature, or None to skip it."""
    if not tags:
        return None
    if tags.get("tunnel") in ("yes", "building_passage", "culvert"):
        return None
    highway = tags.get("highway")
    if highway:
        # The circuit itself (highway=raceway) is drawn by the replay window.
        return ROAD_CLASSES.get(highway)
    if tags.get("railway") in ("rail", "light_rail", "tram", "subway", "narrow_gauge", "monorail"):
        return ("rail", 2.5)
    if tags.get("waterway") in WATERWAY_WIDTHS:
        return ("water", WATERWAY_WIDTHS[tags["waterway"]])
    aeroway = tags.get("aeroway")
    if aeroway == "runway":
        return ("aeroway", 45.0)
    if aeroway == "taxiway":
        return ("aeroway", 20.0)
    if tags.get("man_made") in ("pier", "breakwater", "groyne"):
        return ("pier", 6.0)
    return None


def _geom(element_or_member: dict) -> Optional[np.ndarray]:
    pts = element_or_member.get("geometry")
    if not pts:
        return None
    coords = [(p["lon"], p["lat"]) for p in pts if p and "lon" in p and "lat" in p]
    if len(coords) < 2:
        return None
    return np.asarray(coords, dtype=float)


def _close_rings(lines: List[np.ndarray]) -> List[np.ndarray]:
    rings, chains = join_lines(lines, directed=False)
    for chain in chains:
        # Tolerate small gaps (about 10 m) left by partial downloads.
        if len(chain) >= 3 and np.hypot(*(chain[0] - chain[-1])) < 1e-4:
            rings.append(np.vstack([chain, chain[:1]]))
    return rings


def parse_osm(data: dict) -> OsmLayers:
    """Turn Overpass ``out geom`` JSON into styled areas, lines and coastlines."""
    layers = OsmLayers()
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        etype = el.get("type")

        if etype == "way":
            coords = _geom(el)
            if coords is None:
                continue
            if tags.get("natural") == "coastline":
                layers.coastlines.append(coords)
                continue
            closed = len(coords) >= 4 and np.allclose(coords[0], coords[-1])
            is_line_feature = bool(tags.get("highway") or tags.get("railway")
                                   or tags.get("waterway") in WATERWAY_WIDTHS
                                   or tags.get("aeroway") in ("runway", "taxiway"))
            if closed and not is_line_feature:
                kind = classify_area(tags)
                if kind:
                    height = _parse_height(tags) if kind == "building" else None
                    layers.areas.append(Area(kind, [coords], [], height))
                    continue
            line = classify_line(tags)
            if line:
                layers.lines.append(Line(line[0], coords, line[1]))

        elif etype == "relation":
            kind = classify_area(tags)
            if not kind:
                continue
            outers, inners = [], []
            for member in el.get("members", []):
                if member.get("type") != "way":
                    continue
                coords = _geom(member)
                if coords is None:
                    continue
                (inners if member.get("role") == "inner" else outers).append(coords)
            outer_rings = _close_rings(outers)
            if outer_rings:
                height = _parse_height(tags) if kind == "building" else None
                layers.areas.append(Area(kind, outer_rings, _close_rings(inners), height))
    return layers


# ---------------------------------------------------------------------------
# Step 4: render
# ---------------------------------------------------------------------------

def frame_for_track(reference_rot: np.ndarray, scale_m_per_unit: float,
                    target_px: int = TARGET_LONG_SIDE_PX,
                    margin_fraction: float = MARGIN_FRACTION) -> MapFrame:
    """Map region around the (already rotated) reference lap, plus a margin."""
    x0, y0 = reference_rot.min(axis=0)
    x1, y1 = reference_rot.max(axis=0)
    size = max(x1 - x0, y1 - y0)
    margin = max(margin_fraction * size, MIN_MARGIN_M / max(scale_m_per_unit, 1e-9))
    x0, y0, x1, y1 = x0 - margin, y0 - margin, x1 + margin, y1 + margin
    long_side = max(x1 - x0, y1 - y0)
    k = target_px / long_side
    return MapFrame(float(x0), float(x1), float(y0), float(y1),
                    max(1, int(round((x1 - x0) * k))), max(1, int(round((y1 - y0) * k))))


def _vignette(width: int, height: int, start: float = VIGNETTE_START) -> np.ndarray:
    """Alpha mask (0-255) that fades out towards the edges (rounded-rectangle shape)."""
    u = np.abs(np.linspace(-1.0, 1.0, width))[None, :]
    v = np.abs(np.linspace(-1.0, 1.0, height))[:, None]
    p = 5.0
    r = (u ** p + v ** p) ** (1.0 / p)
    t = np.clip((r - start) / (1.0 - start), 0.0, 1.0)
    fade = 1.0 - t * t * (3.0 - 2.0 * t)  # smoothstep
    return (fade * 255).astype(np.uint8)


def render_map(layers: OsmLayers, frame: MapFrame, px_per_m: float,
               supersample: int = SUPERSAMPLE, vignette: bool = True) -> Image.Image:
    """
    Paint layers (already in the frame's coordinates) into an RGBA image.

    ``px_per_m`` is the final image resolution in pixels per metre, used to
    give roads and rivers their real-world width.
    """
    ss = max(1, int(supersample))
    w, h = frame.width_px * ss, frame.height_px * ss
    k = frame.px_per_unit * ss
    x0, y1 = frame.x0, frame.y1
    m_to_px = px_per_m * ss

    def to_px(pts: np.ndarray) -> List[Tuple[float, float]]:
        return list(zip(((pts[:, 0] - x0) * k).tolist(), ((y1 - pts[:, 1]) * k).tolist()))

    base = Image.new("RGB", (w, h), STYLE["land"])
    draw = ImageDraw.Draw(base)

    by_kind: Dict[str, List[Area]] = {}
    for area in layers.areas:
        by_kind.setdefault(area.kind, []).append(area)

    # 1. Land cover (largest first so small parks sit on top of big districts).
    for kind in AREA_ORDER:
        areas = sorted(by_kind.get(kind, []), key=lambda a: -abs(signed_area(a.outers[0])))
        for area in areas:
            for ring in area.outers:
                if len(ring) >= 3:
                    draw.polygon(to_px(ring), fill=STYLE[kind])

    # 2. Water, composited through a mask so river islands keep their land cover.
    mask = Image.new("L", (w, h), 0)
    mdraw = ImageDraw.Draw(mask)
    if layers.coastlines:
        sea = coastline_water(layers.coastlines, frame.bounds)
        if sea is not None:
            water_polys, islands = sea
            for poly in water_polys:
                mdraw.polygon(to_px(poly), fill=255)
            for island in islands:
                mdraw.polygon(to_px(island), fill=0)
    for area in sorted(by_kind.get("water", []), key=lambda a: -abs(signed_area(a.outers[0]))):
        for ring in area.outers:
            mdraw.polygon(to_px(ring), fill=255)
        for ring in area.inners:
            mdraw.polygon(to_px(ring), fill=0)
    for line in layers.lines:
        if line.kind == "water":
            mdraw.line(to_px(line.coords), fill=255,
                       width=max(1, int(round(line.width_m * m_to_px))), joint="curve")
    base.paste(Image.new("RGB", (w, h), STYLE["water"]), (0, 0), mask)

    # 3. Piers / breakwaters over the water, then buildings.
    for line in layers.lines:
        if line.kind == "pier":
            draw.line(to_px(line.coords), fill=STYLE["pier"],
                      width=max(1, int(round(line.width_m * m_to_px))), joint="curve")
    for area in by_kind.get("building", []):
        for ring in area.outers:
            if len(ring) >= 3:
                draw.polygon(to_px(ring), fill=STYLE["building"], outline=STYLE["building_edge"])

    # 4. Transport network, minor roads first.
    def line_rank(line: Line) -> int:
        return {"path": 0, "rail": 1, "aeroway": 1, "road_minor": 2,
                "road_major": 3, "road_motorway": 4}.get(line.kind, -1)

    for line in sorted(layers.lines, key=line_rank):
        if line.kind in ("water", "pier") or line.kind not in STYLE:
            continue
        width = max(1, int(round(line.width_m * m_to_px)))
        draw.line(to_px(line.coords), fill=STYLE[line.kind], width=width,
                  joint="curve" if width > 2 else None)

    out = base.resize((frame.width_px, frame.height_px), Image.LANCZOS) if ss > 1 else base
    out = out.convert("RGBA")
    if vignette:
        out.putalpha(Image.fromarray(_vignette(frame.width_px, frame.height_px)))
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

@dataclass
class CircuitMapData:
    """Map features for one circuit, projected into a (rotated) world frame."""

    circuit_id: str
    circuit_name: str
    fit: GeoFit
    frame: MapFrame
    layers: OsmLayers        # coastlines oriented with the water on their right

    @property
    def px_per_m(self) -> float:
        return self.frame.px_per_unit / self.fit.scale


def load_circuit_map_data(reference_xy, rotation_deg: float = 0.0,
                          rotation_center: Tuple[float, float] = (0.0, 0.0),
                          location: str = "", country: str = "", event_name: str = "",
                          cache_dir: Optional[str] = None,
                          target_px: int = TARGET_LONG_SIDE_PX,
                          margin_fraction: float = MARGIN_FRACTION) -> Optional[CircuitMapData]:
    """
    Match the circuit, download (or load cached) OpenStreetMap data around it
    and project everything into the replay's rotated world frame.

    Args:
        reference_xy: (n, 2) FastF1 X/Y points of the reference lap.
        rotation_deg / rotation_center: the window's circuit rotation, so the
            data lines up with what is on screen (0 for the raw world frame).
        location / country / event_name: from ``session.event``; used to pick
            the circuit outline (shape matching is the fallback).
        margin_fraction: how far the map extends past the track (x its size).

    Returns:
        :class:`CircuitMapData`, or None when no outline matches the lap
        closely enough (e.g. a layout the dataset doesn't have).

    Raises:
        RuntimeError: when data can't be downloaded and isn't cached yet.
    """
    reference = np.asarray(reference_xy, dtype=float)
    reference = reference[np.isfinite(reference).all(axis=1)]
    cache_dir = cache_dir or default_cache_dir()

    features = load_circuit_outlines(cache_dir)
    match = match_circuit(features, reference, location, country, event_name)
    if match is None:
        return None
    feature, fit = match
    props = feature.get("properties") or {}
    circuit_id = str(props.get("id") or "circuit")

    frame = frame_for_track(rotate_about(reference, rotation_center, rotation_deg), fit.scale,
                            target_px, margin_fraction)

    # Frame corners -> world -> lon/lat gives the area to download.
    corners_rot = np.array([[frame.x0, frame.y0], [frame.x1, frame.y0],
                            [frame.x1, frame.y1], [frame.x0, frame.y1]])
    corners_world = rotate_about(corners_rot, rotation_center, -rotation_deg)
    lon, lat = fit.world_to_lonlat(corners_world[:, 0], corners_world[:, 1])
    bbox = (float(lat.min()), float(lon.min()), float(lat.max()), float(lon.max()))

    layers = parse_osm(fetch_osm(circuit_id, bbox, cache_dir))

    def to_frame(lonlat: np.ndarray) -> np.ndarray:
        x, y = fit.lonlat_to_world(lonlat[:, 0], lonlat[:, 1])
        return rotate_about(np.column_stack([x, y]), rotation_center, rotation_deg)

    projected = layers.transformed(to_frame)
    if fit.mirrored:
        # Mirroring flips which side of a coastline the water is on.
        projected.coastlines = [c[::-1] for c in projected.coastlines]

    return CircuitMapData(circuit_id=circuit_id, circuit_name=str(props.get("Name") or ""),
                          fit=fit, frame=frame, layers=projected)


def build_track_map(reference_xy, rotation_deg: float = 0.0,
                    rotation_center: Tuple[float, float] = (0.0, 0.0),
                    location: str = "", country: str = "", event_name: str = "",
                    cache_dir: Optional[str] = None,
                    target_px: int = TARGET_LONG_SIDE_PX) -> Optional[TrackMapImage]:
    """
    Build the map image for the replay window (see :func:`load_circuit_map_data`).

    Returns:
        A :class:`TrackMapImage`, or None when no outline matches the lap.

    Raises:
        RuntimeError: when data can't be downloaded and isn't cached yet.
    """
    data = load_circuit_map_data(reference_xy, rotation_deg, rotation_center, location,
                                 country, event_name, cache_dir, target_px)
    if data is None:
        return None
    image = render_map(data.layers, data.frame, data.px_per_m)
    return TrackMapImage(
        image=image,
        bounds=data.frame.bounds,
        circuit_id=data.circuit_id,
        circuit_name=data.circuit_name,
        residual_m=data.fit.residual_m,
    )
