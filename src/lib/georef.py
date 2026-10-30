"""
Georeferencing: line up FastF1 track coordinates with the real world.

FastF1 positions (``X`` / ``Y``) use a circuit-local frame in 1/10 m with an
arbitrary origin and orientation. To draw a real map under the track we need
the similarity transform (uniform scale + rotation + translation, possibly
mirrored) that maps that frame onto the circuit's real outline in
latitude/longitude.

The real outline comes from the open f1-circuits dataset
(https://github.com/bacinger/f1-circuits, MIT licence). We don't know where
the reference lap starts on that outline, or which way round the dataset
draws it, so every possible start offset is tested at once with an FFT
cross-correlation, for both directions and both mirror states. The best
least-squares fit wins and its RMS error (in metres) tells us whether the
match can be trusted.

Everything here is plain NumPy so it can be unit tested without network
access, FastF1 or an OpenGL context.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

EARTH_M_PER_DEG_LAT = 110_540.0
EARTH_M_PER_DEG_LON_EQUATOR = 111_320.0

# Number of points both outlines are resampled to before matching. Dense
# enough (a few metres apart) that the best whole-sample shift lands within a
# metre or two of the true start offset; the FFT keeps it well under 1 ms.
DEFAULT_SAMPLES = 2048

# A correct match is typically 5-15 m RMS (the racing line wanders across the
# track width). A wrong circuit or layout is hundreds of metres off.
DEFAULT_MAX_RESIDUAL_M = 40.0


def lonlat_to_local_m(lon, lat, lon0: float, lat0: float):
    """
    Project lon/lat (degrees) to metres east/north of ``(lon0, lat0)``.

    Uses an equirectangular projection, which is accurate to well under a
    metre across the few kilometres a circuit covers.
    """
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    east = (lon - lon0) * EARTH_M_PER_DEG_LON_EQUATOR * np.cos(np.radians(lat0))
    north = (lat - lat0) * EARTH_M_PER_DEG_LAT
    return east, north


def local_m_to_lonlat(east, north, lon0: float, lat0: float):
    """Inverse of :func:`lonlat_to_local_m`."""
    east = np.asarray(east, dtype=float)
    north = np.asarray(north, dtype=float)
    lon = lon0 + east / (EARTH_M_PER_DEG_LON_EQUATOR * np.cos(np.radians(lat0)))
    lat = lat0 + north / EARTH_M_PER_DEG_LAT
    return lon, lat


def resample_closed(points, n: int) -> np.ndarray:
    """
    Resample a closed polyline to ``n`` points evenly spaced by arc length.

    The polyline may or may not repeat its first point at the end.
    """
    pts = np.asarray(points, dtype=float)
    pts = pts[np.isfinite(pts).all(axis=1)]
    if len(pts) > 1 and np.allclose(pts[0], pts[-1]):
        pts = pts[:-1]
    if len(pts) < 3:
        raise ValueError("need at least 3 distinct points to resample a closed outline")

    closed = np.vstack([pts, pts[:1]])
    seg = np.hypot(*np.diff(closed, axis=0).T)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    if cum[-1] <= 0:
        raise ValueError("outline has zero length")

    t = np.linspace(0.0, cum[-1], n, endpoint=False)
    return np.column_stack([
        np.interp(t, cum, closed[:, 0]),
        np.interp(t, cum, closed[:, 1]),
    ])


@dataclass(frozen=True)
class GeoFit:
    """
    Similarity transform between FastF1 world coordinates and the real world.

    ``local`` coordinates are metres east/north of ``(lon0, lat0)``.
    """

    lon0: float
    lat0: float
    world_cx: float
    world_cy: float
    local_cx: float
    local_cy: float
    scale: float          # metres per world unit (~0.1 for FastF1 data)
    rotation: float       # radians, world -> local
    mirrored: bool        # True if the world frame is a mirror image of the map
    residual_m: float     # RMS distance between the fitted and the real outline

    def world_to_local(self, x, y):
        """World (FastF1) coordinates -> metres east/north."""
        x = np.asarray(x, dtype=float) - self.world_cx
        y = np.asarray(y, dtype=float) - self.world_cy
        if self.mirrored:
            y = -y
        c, s = np.cos(self.rotation), np.sin(self.rotation)
        east = self.scale * (c * x - s * y) + self.local_cx
        north = self.scale * (s * x + c * y) + self.local_cy
        return east, north

    def local_to_world(self, east, north):
        """Metres east/north -> world (FastF1) coordinates."""
        e = (np.asarray(east, dtype=float) - self.local_cx) / self.scale
        n = (np.asarray(north, dtype=float) - self.local_cy) / self.scale
        c, s = np.cos(self.rotation), np.sin(self.rotation)
        x = c * e + s * n
        y = -s * e + c * n
        if self.mirrored:
            y = -y
        return x + self.world_cx, y + self.world_cy

    def lonlat_to_world(self, lon, lat):
        east, north = lonlat_to_local_m(lon, lat, self.lon0, self.lat0)
        return self.local_to_world(east, north)

    def world_to_lonlat(self, x, y):
        east, north = self.world_to_local(x, y)
        return local_m_to_lonlat(east, north, self.lon0, self.lat0)

    def is_trustworthy(self, max_residual_m: float = DEFAULT_MAX_RESIDUAL_M) -> bool:
        """True when the outlines matched closely enough to draw a map."""
        return bool(np.isfinite(self.residual_m) and self.residual_m <= max_residual_m
                    and self.scale > 0)


def fit_outline(world_xy, lonlat, samples: int = DEFAULT_SAMPLES) -> GeoFit:
    """
    Fit the reference-lap outline (world units) to a real outline (lon, lat).

    Args:
        world_xy: (n, 2) array of FastF1 X/Y points along one lap.
        lonlat: (m, 2) array of [lon, lat] points along the real circuit.
        samples: points both outlines are resampled to before matching.

    Returns:
        The best :class:`GeoFit`. Check ``residual_m`` (or
        :meth:`GeoFit.is_trustworthy`) before relying on it.
    """
    world = np.asarray(world_xy, dtype=float)
    geo = np.asarray(lonlat, dtype=float)
    world = world[np.isfinite(world).all(axis=1)]
    geo = geo[np.isfinite(geo).all(axis=1)]
    if len(world) < 8 or len(geo) < 8:
        raise ValueError("need at least 8 points in each outline")

    lon0 = float(geo[:, 0].mean())
    lat0 = float(geo[:, 1].mean())
    east, north = lonlat_to_local_m(geo[:, 0], geo[:, 1], lon0, lat0)

    a_pts = resample_closed(world, samples)
    g_pts = resample_closed(np.column_stack([east, north]), samples)
    ca = a_pts.mean(axis=0)
    cg = g_pts.mean(axis=0)

    # Work with complex numbers: a similarity transform is then a single
    # complex multiply (scale * e^(i*rotation)) plus an offset.
    z = (a_pts[:, 0] - ca[0]) + 1j * (a_pts[:, 1] - ca[1])
    w = (g_pts[:, 0] - cg[0]) + 1j * (g_pts[:, 1] - cg[1])
    zz = float(np.sum(np.abs(z) ** 2))
    ww = float(np.sum(np.abs(w) ** 2))
    if zz <= 0 or ww <= 0:
        raise ValueError("degenerate outline")

    best = None
    for mirrored in (False, True):
        zf = np.conj(z) if mirrored else z          # mirror = flip the Y axis
        fz = np.fft.fft(zf)
        for reverse in (False, True):
            wf = w[::-1] if reverse else w
            # corr[k] = sum_j wf[j] * conj(zf[j - k]) for every circular shift k
            corr = np.fft.ifft(np.fft.fft(wf) * np.conj(fz))
            k = int(np.argmax(np.abs(corr)))
            a = corr[k] / zz                         # least-squares complex gain
            err = ww - (abs(corr[k]) ** 2) / zz      # remaining squared error
            if best is None or err < best[0]:
                best = (err, a, mirrored)

    err, a, mirrored = best
    return GeoFit(
        lon0=lon0,
        lat0=lat0,
        world_cx=float(ca[0]),
        world_cy=float(ca[1]),
        local_cx=float(cg[0]),
        local_cy=float(cg[1]),
        scale=float(abs(a)),
        rotation=float(np.angle(a)),
        mirrored=bool(mirrored),
        residual_m=float(np.sqrt(max(err, 0.0) / samples)),
    )
