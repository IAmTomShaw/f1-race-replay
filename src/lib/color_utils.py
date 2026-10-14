"""WCAG relative luminance and display-safe color contrast utilities.

Pure Python color math with zero GUI framework coupling.
"""
from __future__ import annotations

DEFAULT_DARK_BG = "#282828"


def hex_to_rgb01(colour):
    """Parse '#RRGGBB' into a normalized (r, g, b) tuple in [0.0, 1.0]."""
    colour = str(colour or "").strip()
    if not colour.startswith("#") or len(colour) != 7:
        return None
    try:
        return tuple(int(colour[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
    except ValueError:
        return None


def rgb01_to_hex(rgb) -> str:
    """Format a normalized (r, g, b) tuple in [0.0, 1.0] as '#RRGGBB'."""
    return "#{:02X}{:02X}{:02X}".format(
        int(max(0.0, min(1.0, rgb[0])) * 255.0),
        int(max(0.0, min(1.0, rgb[1])) * 255.0),
        int(max(0.0, min(1.0, rgb[2])) * 255.0),
    )


def srgb_to_linear(channel: float) -> float:
    """Convert an sRGB channel in [0.0, 1.0] to linear light."""
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb) -> float:
    """Compute WCAG 2.1 relative luminance for a normalized (r, g, b) tuple."""
    r, g, b = (srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """Compute WCAG 2.1 contrast ratio between two hex colors."""
    fg_rgb = hex_to_rgb01(fg_hex)
    bg_rgb = hex_to_rgb01(bg_hex)
    if fg_rgb is None or bg_rgb is None:
        return 1.0
    fg_l = relative_luminance(fg_rgb)
    bg_l = relative_luminance(bg_rgb)
    lighter = max(fg_l, bg_l)
    darker = min(fg_l, bg_l)
    return (lighter + 0.05) / (darker + 0.05)


def mix_rgb(rgb_a, rgb_b, amount: float):
    """Linearly interpolate between two RGB tuples by `amount` in [0.0, 1.0]."""
    return tuple(
        (1.0 - amount) * a + amount * b
        for a, b in zip(rgb_a, rgb_b)
    )


def display_safe_colour(
    colour: str,
    bg_colour: str = DEFAULT_DARK_BG,
    min_contrast: float = 3.2,
) -> str:
    """Ensure `colour` achieves at least `min_contrast` against `bg_colour`."""
    if contrast_ratio(colour, bg_colour) >= min_contrast:
        return colour

    rgb = hex_to_rgb01(colour)
    if rgb is None:
        return colour

    white = (1.0, 1.0, 1.0)
    lo, hi = 0.0, 1.0
    best = white
    for _ in range(16):
        mid = (lo + hi) / 2.0
        candidate = mix_rgb(rgb, white, mid)
        candidate_hex = rgb01_to_hex(candidate)
        if contrast_ratio(candidate_hex, bg_colour) >= min_contrast:
            best = candidate
            hi = mid
        else:
            lo = mid
    return rgb01_to_hex(best)


_hex_to_rgb01 = hex_to_rgb01
_rgb01_to_hex = rgb01_to_hex
_srgb_to_linear = srgb_to_linear
_relative_luminance = relative_luminance
_contrast_ratio = contrast_ratio
_mix_rgb = mix_rgb
_display_safe_colour = display_safe_colour
