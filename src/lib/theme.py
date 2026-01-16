import json
import os
from typing import Dict, List, Tuple

Color = Tuple[int, int, int]


def _parse_color(value, default: Color = (255, 255, 255)) -> Color:
    """
    Normalize a color entry to an RGB tuple.
    Supports hex strings ("#RRGGBB") or 3-length sequences of ints.
    """
    if isinstance(value, str):
        hex_str = value.lstrip("#")
        if len(hex_str) == 6:
            try:
                return tuple(int(hex_str[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
            except ValueError:
                return default
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        try:
            return (int(value[0]), int(value[1]), int(value[2]))
        except (TypeError, ValueError):
            return default
    return default


class Theme:
    def __init__(self, name: str, payload: Dict):
        self.name = name
        self.payload = payload or {}
        self.colors = {k: _parse_color(v) for k, v in (self.payload.get("colors") or {}).items()}
        self.track_status = {k.upper(): _parse_color(v) for k, v in (self.payload.get("track_status") or {}).items()}
        palette = self.payload.get("driver_palette") or []
        self.driver_palette: List[Color] = [_parse_color(c, (220, 220, 220)) for c in palette]

    def color(self, key: str, default: Color) -> Color:
        return self.colors.get(key, default)

    def status_color(self, key: str, default: Color) -> Color:
        return self.track_status.get(key.upper(), default)

    def remap_driver_colors(self, drivers: Dict[str, Color]) -> Dict[str, Color]:
        """
        Return driver colors mapped onto a palette (used for color-blind safe themes).
        Mapping is stable and deterministic so it does not flicker between runs.
        """
        if not self.driver_palette:
            return drivers
        remapped = {}
        palette_len = len(self.driver_palette)
        for idx, code in enumerate(sorted(drivers.keys())):
            remapped[code] = self.driver_palette[idx % palette_len]
        return remapped


DEFAULT_THEMES = {
    "dark": {
        "colors": {
            "background": "#0c0c0f",
            "panel": "#1a1d22",
            "panel_border": "#2d323c",
            "text_primary": "#f5f7fa",
            "text_muted": "#b7c0cc",
            "highlight": "#7dd3fc",
            "pin": "#f59e0b",
        },
        "track_status": {
            "GREEN": "#7a7f89",
            "YELLOW": "#f2c94c",
            "RED": "#ef4444",
            "SC": "#f97316",
            "VSC": "#f59e0b",
        },
    },
    "high_contrast": {
        "colors": {
            "background": "#000000",
            "panel": "#0f172a",
            "panel_border": "#e5e7eb",
            "text_primary": "#ffffff",
            "text_muted": "#e5e7eb",
            "highlight": "#22d3ee",
            "pin": "#fbbf24",
        },
        "track_status": {
            "GREEN": "#d1d5db",
            "YELLOW": "#fde047",
            "RED": "#ef4444",
            "SC": "#fb923c",
            "VSC": "#fbbf24",
        },
        "driver_palette": [
            "#0ea5e9", "#22c55e", "#f97316", "#a855f7", "#f43f5e",
            "#84cc16", "#eab308", "#14b8a6", "#c084fc", "#ef4444",
            "#10b981", "#3b82f6", "#d946ef", "#f59e0b", "#8b5cf6",
            "#22c55e", "#facc15", "#6366f1", "#ef4444", "#14b8a6",
        ],
    },
    "deuteranopia": {
        "colors": {
            "background": "#0d1117",
            "panel": "#161b22",
            "panel_border": "#2f343f",
            "text_primary": "#f0f6fc",
            "text_muted": "#c9d1d9",
            "highlight": "#38bdf8",
            "pin": "#eab308",
        },
        "track_status": {
            "GREEN": "#94a3b8",
            "YELLOW": "#fcd34d",
            "RED": "#ef4444",
            "SC": "#f59e0b",
            "VSC": "#fbbf24",
        },
        # High-distinction Okabe-Ito palette (color-blind safe)
        "driver_palette": [
            "#E69F00", "#56B4E9", "#009E73", "#F0E442", "#0072B2",
            "#D55E00", "#CC79A7", "#999999", "#2E8B57", "#8A2BE2",
            "#87CEFA", "#B22222", "#20B2AA", "#708090", "#DDA0DD",
            "#FF8C00", "#6A5ACD", "#3CB371", "#CD5C5C", "#4682B4",
        ],
    },
}


class ThemeManager:
    def __init__(self, path: str | None = None):
        self.path = path
        self.themes: Dict[str, Theme] = {}
        self._load()

    def _load(self):
        payload = {}
        if self.path and os.path.exists(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception:
                payload = {}
        # Merge defaults with any custom payload
        merged = {**DEFAULT_THEMES, **(payload or {})}
        self.themes = {name: Theme(name, data) for name, data in merged.items()}

    def get(self, name: str | None) -> Theme:
        if name and name in self.themes:
            return self.themes[name]
        # Default ordering preference
        for candidate in ("dark", "high_contrast", "deuteranopia"):
            if candidate in self.themes:
                return self.themes[candidate]
        return next(iter(self.themes.values()))

    def cycle(self, current_name: str | None) -> Theme:
        names = list(self.themes.keys())
        if not names:
            return Theme("default", DEFAULT_THEMES["dark"])
        if current_name not in names:
            return self.themes[names[0]]
        idx = names.index(current_name)
        return self.themes[(idx + 1) % len(names)]
