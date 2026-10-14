"""Shared UI helper package for Arcade text and texture caching."""
from src.ui.text_cache import TEXT_CACHE, clear_text_cache, set_text_if_changed

__all__ = [
    "TEXT_CACHE",
    "clear_text_cache",
    "set_text_if_changed",
]
