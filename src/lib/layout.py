import json
import os
from copy import deepcopy
from typing import Dict, Optional, Tuple

PanelRect = Dict[str, float]

# Normalized defaults (x/top/width/height are stored as ratios of the window)
DEFAULT_LAYOUT = {
    "track_map": {"x": 0.12, "top": 0.97, "width": 0.54, "height": 0.94},
    "leaderboard": {"x": 0.82, "top": 0.95, "width": 0.18, "height": 0.88},
    "telemetry": {"x": 0.66, "top": 0.95, "width": 0.16, "height": 0.55},
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


class LayoutManager:
    """
    Persisted layout helper that stores normalized positions in JSON and
    converts them to pixel coordinates for the active window size.
    Coordinates are top-left anchored (x, top) with width/height.
    """

    HANDLE_SIZE = 10
    MIN_SIZE = 120

    def __init__(self, path: Optional[str] = None, defaults: Optional[Dict[str, PanelRect]] = None):
        self.path = path
        self.layout_norm: Dict[str, PanelRect] = deepcopy(defaults or DEFAULT_LAYOUT)
        self.layout_px: Dict[str, PanelRect] = {}
        self._active: Optional[Dict] = None
        self._load()

    def _load(self):
        if self.path and os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self.layout_norm.update(loaded)
            except Exception:
                # Fallback to defaults on any read/parse failure
                pass

    def _save(self):
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.layout_norm, f, indent=2)
        except Exception:
            # Swallow errors to avoid crashing the UI when filesystem is read-only
            pass

    def _validated_norm(self) -> Dict[str, PanelRect]:
        """
        Clamp normalized values to sane ranges (0..1) and enforce minimum sizes.
        """
        validated: Dict[str, PanelRect] = {}
        min_ratio = 0.05  # 5% of screen
        for name, rect in self.layout_norm.items():
            x = _clamp(rect.get("x", 0.0), 0.0, 0.95)
            width = _clamp(rect.get("width", 0.2), min_ratio, 1.0)
            top = _clamp(rect.get("top", 1.0), 0.0, 1.0)
            height = _clamp(rect.get("height", 0.2), min_ratio, 1.0)
            if x + width > 1.0:
                width = _clamp(1.0 - x, min_ratio, 1.0)
            if height > top:
                height = _clamp(top, min_ratio, 1.0)
            validated[name] = {"x": x, "top": top, "width": width, "height": height}
        return validated

    def as_pixels(self, width: float, height: float) -> Dict[str, PanelRect]:
        self.layout_px = {}
        for name, rect in self._validated_norm().items():
            self.layout_px[name] = {
                "x": rect["x"] * width,
                "top": rect["top"] * height,
                "width": rect["width"] * width,
                "height": rect["height"] * height,
            }
        return deepcopy(self.layout_px)

    def _normalize(self, width: float, height: float):
        """Update normalized layout from current pixel layout."""
        if not self.layout_px:
            return
        for name, rect in self.layout_px.items():
            self.layout_norm[name] = {
                "x": rect["x"] / max(width, 1),
                "top": rect["top"] / max(height, 1),
                "width": rect["width"] / max(width, 1),
                "height": rect["height"] / max(height, 1),
            }

    def _panel_bounds(self, rect: PanelRect) -> Tuple[float, float, float, float]:
        left = rect["x"]
        right = rect["x"] + rect["width"]
        top = rect["top"]
        bottom = rect["top"] - rect["height"]
        return left, bottom, right, top

    def hit_test(self, x: float, y: float) -> Optional[Dict]:
        """
        Identify which panel is under the cursor and whether the user is near an edge for resizing.
        Returns a dict describing the interaction target or None.
        """
        for name, rect in self.layout_px.items():
            left, bottom, right, top = self._panel_bounds(rect)
            if not (left <= x <= right and bottom <= y <= top):
                continue
            edge = []
            if abs(x - left) <= self.HANDLE_SIZE:
                edge.append("left")
            elif abs(x - right) <= self.HANDLE_SIZE:
                edge.append("right")
            if abs(y - top) <= self.HANDLE_SIZE:
                edge.append("top")
            elif abs(y - bottom) <= self.HANDLE_SIZE:
                edge.append("bottom")

            mode = "move"
            if edge:
                mode = "resize"
            return {
                "panel": name,
                "mode": mode,
                "edge": "-".join(edge) if edge else "",
            }
        return None

    def start_interaction(self, x: float, y: float) -> Optional[Dict]:
        hit = self.hit_test(x, y)
        if not hit:
            return None
        panel = hit["panel"]
        self._active = {
            "panel": panel,
            "mode": hit["mode"],
            "edge": hit["edge"],
            "start": (x, y),
            "original": deepcopy(self.layout_px.get(panel, {})),
        }
        return self._active

    def update_interaction(self, x: float, y: float, window_w: float, window_h: float):
        if not self._active:
            return
        start_x, start_y = self._active["start"]
        dx, dy = x - start_x, y - start_y
        panel = self._active["panel"]
        rect = deepcopy(self._active["original"])

        if self._active["mode"] == "move":
            rect["x"] += dx
            rect["top"] += dy
        else:
            edge = self._active["edge"]
            # Horizontal resizing
            if "left" in edge:
                new_left = rect["x"] + dx
                rect["width"] -= dx
                rect["x"] = new_left
            elif "right" in edge:
                rect["width"] += dx
            # Vertical resizing
            if "top" in edge:
                rect["top"] += dy
                rect["height"] -= dy
            elif "bottom" in edge:
                rect["height"] += dy

        # Clamp size and position
        rect["width"] = _clamp(rect["width"], self.MIN_SIZE, window_w)
        rect["height"] = _clamp(rect["height"], self.MIN_SIZE, window_h)
        rect["x"] = _clamp(rect["x"], 0, max(0.0, window_w - rect["width"]))
        rect["top"] = _clamp(rect["top"], rect["height"], window_h)

        self.layout_px[panel] = rect
        self._normalize(window_w, window_h)

    def end_interaction(self, window_w: float, window_h: float):
        if not self._active:
            return
        self._normalize(window_w, window_h)
        self._save()
        self._active = None

    def refresh_from_window(self, window_w: float, window_h: float) -> Dict[str, PanelRect]:
        """
        Recalculate pixel layout for a new window size (e.g., on resize).
        """
        return self.as_pixels(window_w, window_h)

    def reset_to_defaults(self):
        """Reset layout to hardcoded defaults and persist."""
        self.layout_norm = deepcopy(DEFAULT_LAYOUT)
        self._save()
