"""
2D geometry helpers for drawing OpenStreetMap data.

OpenStreetMap stores big areas (lakes, rivers, parks) as several ways that
have to be joined end-to-end into closed rings, and stores the sea only
indirectly, as "coastline" lines with the land on their left. These helpers
turn that raw data into closed polygons that can be filled.

All functions work in a y-up coordinate frame (maths convention), where a
ring with positive signed area runs counter-clockwise.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

Rect = Tuple[float, float, float, float]  # (xmin, xmax, ymin, ymax)


def signed_area(ring) -> float:
    """Shoelace area. Positive = counter-clockwise (y-up frame)."""
    pts = np.asarray(ring, dtype=float)
    if len(pts) < 3:
        return 0.0
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def is_closed(points, tol: float = 1e-9) -> bool:
    pts = np.asarray(points, dtype=float)
    return len(pts) >= 4 and bool(np.allclose(pts[0], pts[-1], atol=tol, rtol=0))


def _key(pt, ndigits: int) -> Tuple[float, float]:
    return (round(float(pt[0]), ndigits), round(float(pt[1]), ndigits))


def join_lines(lines: Iterable[Sequence], directed: bool = False,
               ndigits: int = 7) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """
    Join polylines that share end points into longer chains.

    Args:
        lines: polylines as (n, 2) sequences.
        directed: keep each line's direction (needed for coastlines, whose
            direction tells you which side is water). When False, lines may
            be reversed to make them fit.
        ndigits: rounding used to decide that two end points are the same
            node (7 decimals of a degree is about 1 cm).

    Returns:
        (rings, chains): closed rings, and chains that could not be closed.
    """
    pieces = [np.asarray(l, dtype=float) for l in lines if len(l) >= 2]
    used = [False] * len(pieces)

    starts = {}
    ends = {}
    for i, p in enumerate(pieces):
        starts.setdefault(_key(p[0], ndigits), []).append(i)
        ends.setdefault(_key(p[-1], ndigits), []).append(i)

    def take(candidates):
        for j in candidates:
            if not used[j]:
                used[j] = True
                return j
        return None

    rings, chains = [], []
    for i, first in enumerate(pieces):
        if used[i]:
            continue
        used[i] = True
        chain = [first]

        # Extend forwards from the chain's end.
        while True:
            end_key = _key(chain[-1][-1], ndigits)
            if end_key == _key(chain[0][0], ndigits) and sum(len(c) for c in chain) > 3:
                break
            j = take(starts.get(end_key, []))
            if j is not None:
                chain.append(pieces[j])
                continue
            if not directed:
                j = take(ends.get(end_key, []))
                if j is not None:
                    chain.append(pieces[j][::-1])
                    continue
            break

        # Extend backwards from the chain's start.
        while True:
            start_key = _key(chain[0][0], ndigits)
            if start_key == _key(chain[-1][-1], ndigits) and sum(len(c) for c in chain) > 3:
                break
            j = take(ends.get(start_key, []))
            if j is not None:
                chain.insert(0, pieces[j])
                continue
            if not directed:
                j = take(starts.get(start_key, []))
                if j is not None:
                    chain.insert(0, pieces[j][::-1])
                    continue
            break

        merged = chain[0]
        for part in chain[1:]:
            merged = np.vstack([merged, part[1:]])
        if is_closed(merged):
            rings.append(merged)
        else:
            chains.append(merged)
    return rings, chains


def _clip_segment(p0, p1, rect: Rect) -> Optional[Tuple[float, float]]:
    """Liang-Barsky: parameter range [t0, t1] of segment p0->p1 inside rect."""
    xmin, xmax, ymin, ymax = rect
    x0, y0 = p0
    dx, dy = p1[0] - x0, p1[1] - y0
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, x0 - xmin), (dx, xmax - x0), (-dy, y0 - ymin), (dy, ymax - y0)):
        if p == 0:
            if q < 0:
                return None
            continue
        r = q / p
        if p < 0:
            if r > t1:
                return None
            t0 = max(t0, r)
        else:
            if r < t0:
                return None
            t1 = min(t1, r)
    return t0, t1


def clip_polyline(points, rect: Rect) -> List[np.ndarray]:
    """Clip an open polyline to an axis-aligned rectangle; returns the inside pieces."""
    pts = np.asarray(points, dtype=float)
    pieces: List[np.ndarray] = []
    current: Optional[list] = None
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        clipped = _clip_segment(a, b, rect)
        if clipped is None:
            if current is not None:
                pieces.append(np.array(current))
                current = None
            continue
        t0, t1 = clipped
        pa = a + t0 * (b - a)
        pb = a + t1 * (b - a)
        if current is None:
            current = [pa]
        elif not np.allclose(current[-1], pa):
            current.append(pa)
        current.append(pb)
        if t1 < 1.0:  # leaves the rectangle on this segment
            pieces.append(np.array(current))
            current = None
    if current is not None:
        pieces.append(np.array(current))
    return [p for p in pieces if len(p) >= 2]


def _on_edge(pt, rect: Rect, tol: float) -> bool:
    xmin, xmax, ymin, ymax = rect
    x, y = pt
    inside = xmin - tol <= x <= xmax + tol and ymin - tol <= y <= ymax + tol
    near = min(abs(x - xmin), abs(x - xmax), abs(y - ymin), abs(y - ymax)) <= tol
    return inside and near


def _perimeter_t(pt, rect: Rect) -> float:
    """Clockwise distance along the rectangle edge, starting at the top-left corner."""
    xmin, xmax, ymin, ymax = rect
    w, h = xmax - xmin, ymax - ymin
    x, y = pt
    edges = (
        (abs(y - ymax), lambda: min(max(x - xmin, 0.0), w)),                  # top, going right
        (abs(x - xmax), lambda: w + min(max(ymax - y, 0.0), h)),              # right, going down
        (abs(y - ymin), lambda: w + h + min(max(xmax - x, 0.0), w)),          # bottom, going left
        (abs(x - xmin), lambda: 2 * w + h + min(max(y - ymin, 0.0), h)),      # left, going up
    )
    return min(edges, key=lambda e: e[0])[1]()


def _corners_between(t_from: float, t_to: float, rect: Rect) -> List[Tuple[float, float]]:
    """Rectangle corners met when walking clockwise along the edge from t_from to t_to."""
    xmin, xmax, ymin, ymax = rect
    w, h = xmax - xmin, ymax - ymin
    perimeter = 2 * (w + h)
    corners = ((0.0, (xmin, ymax)), (w, (xmax, ymax)), (w + h, (xmax, ymin)), (2 * w + h, (xmin, ymin)))
    span = (t_to - t_from) % perimeter
    found = []
    for t_corner, pt in corners:
        d = (t_corner - t_from) % perimeter
        if 0 < d < span:
            found.append((d, pt))
    return [pt for _, pt in sorted(found)]


def _start_outside(ring: np.ndarray, rect: Rect) -> Optional[np.ndarray]:
    """Rotate a closed ring so it starts at a vertex outside the rectangle."""
    xmin, xmax, ymin, ymax = rect
    body = ring[:-1]
    outside = np.where((body[:, 0] < xmin) | (body[:, 0] > xmax) |
                       (body[:, 1] < ymin) | (body[:, 1] > ymax))[0]
    if len(outside) == 0:
        return None
    k = int(outside[0])
    rolled = np.vstack([body[k:], body[:k]])
    return np.vstack([rolled, rolled[:1]])


def coastline_water(coastlines: Sequence, rect: Rect):
    """
    Build the sea polygons inside ``rect`` from coastline lines.

    Coastlines must already be oriented with the water on their RIGHT (that
    is the OpenStreetMap convention; reverse them first if the frame they
    were projected into is mirrored).

    Returns:
        (water_polygons, island_rings), or None if the data has gaps that
        make the sea ambiguous (in that case it is safer to draw no sea).
    """
    xmin, xmax, ymin, ymax = rect
    tol = 1e-6 * max(xmax - xmin, ymax - ymin, 1.0)
    rings, chains = join_lines(coastlines, directed=True)

    pieces: List[np.ndarray] = []
    islands: List[np.ndarray] = []
    water: List[np.ndarray] = []

    for ring in rings:
        rotated = _start_outside(ring, rect)
        if rotated is None:  # whole ring inside the rectangle
            if signed_area(ring) > 0:   # anticlockwise: land on the left = an island
                islands.append(ring)
            else:                       # clockwise: water inside (enclosed sea/lake)
                water.append(ring)
            continue
        pieces.extend(clip_polyline(rotated, rect))

    for chain in chains:
        pieces.extend(clip_polyline(chain, rect))

    for piece in pieces:
        if not (_on_edge(piece[0], rect, tol) and _on_edge(piece[-1], rect, tol)):
            return None  # a coastline stops inside the map: data gap

    if not pieces:
        if islands and not water:
            # Only islands inside the frame: everything around them is sea.
            frame = np.array([(xmin, ymax), (xmax, ymax), (xmax, ymin), (xmin, ymin), (xmin, ymax)])
            return [frame], islands
        return water, islands

    perimeter = 2 * ((xmax - xmin) + (ymax - ymin))
    t_in = [_perimeter_t(p[0], rect) for p in pieces]
    t_out = [_perimeter_t(p[-1], rect) for p in pieces]

    unused = set(range(len(pieces)))
    while unused:
        start = min(unused)
        unused.discard(start)
        polygon = [tuple(pt) for pt in pieces[start]]
        current = start
        for _ in range(len(pieces) + 1):
            candidates = list(unused) + [start]
            nxt = min(candidates, key=lambda j: ((t_in[j] - t_out[current]) % perimeter, j != start))
            polygon.extend(_corners_between(t_out[current], t_in[nxt], rect))
            if nxt == start:
                break
            polygon.extend(tuple(pt) for pt in pieces[nxt])
            unused.discard(nxt)
            current = nxt
        if len(polygon) >= 3:
            polygon.append(polygon[0])
            water.append(np.array(polygon))
    return water, islands
