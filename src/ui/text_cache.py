"""Shared Arcade text-mutation guard to prevent Pyglet glyph-atlas leaks.

Extracting this into `src.ui.text_cache` breaks the circular/upward dependency
between `src.ui_components` and `src.interfaces.race_replay`.
"""
from __future__ import annotations

from typing import Dict

TEXT_CACHE: Dict[int, str] = {}


def set_text_if_changed(
    text_obj,
    new_text: str,
    cache: Dict[int, str] = TEXT_CACHE,
) -> None:
    """Assign `text_obj.text = new_text` only when the text string has changed."""
    if text_obj is None:
        return
    key = id(text_obj)
    prev = cache.get(key)
    if prev == new_text:
        return
    text_obj.text = new_text
    cache[key] = new_text


def clear_text_cache(cache: Dict[int, str] = TEXT_CACHE) -> None:
    """Clear the shared per-text-object cache when a window closes."""
    cache.clear()
