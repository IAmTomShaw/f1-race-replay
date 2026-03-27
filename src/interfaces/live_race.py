"""
Live race visualization window.

Extends F1RaceReplayWindow to consume frames from a LiveDataFeed instead of
a pre-computed replay.  The window always shows the most recent frame when
un-paused; pressing SPACE freezes the view (DVR-style) and pressing SPACE
again jumps back to live.
"""

import math
import time

import arcade

from src.interfaces.race_replay import F1RaceReplayWindow
from src.live_f1_data import LiveDataFeed
from src.ui_components import extract_race_events


class LiveRaceWindow(F1RaceReplayWindow):
    """
    Live F1 race viewer.

    Differences from the replay window:
    - Frames are supplied by a LiveDataFeed that grows over time.
    - The frame index always advances to the latest frame (unless paused).
    - Track statuses are synced from the feed on every update.
    - Playback speed / seek controls are hidden and disabled.
    - A pulsing "LIVE" badge is drawn in the top-right corner.
    - Pressing SPACE freezes the view; pressing again jumps back to live.
    """

    def __init__(self, live_feed: LiveDataFeed, **kwargs):
        # Feed provides the shared frames list (grows as data arrives)
        self._live_feed = live_feed

        # Pass the live frames list to the parent so self.frames is the same
        # object — appends from the background thread are immediately visible.
        kwargs.setdefault("frames", live_feed.frames)
        kwargs.setdefault("track_statuses", [])
        kwargs.setdefault("total_laps", None)
        # No tyre degradation for live (no historical session data)
        kwargs["session"] = kwargs.get("session", None)

        super().__init__(**kwargs)

        # After parent init, jump to the latest frame
        self.frame_index = float(max(0, self.n_frames - 1))

        # Hide replay-specific UI elements that don't apply to live viewing
        self.race_controls_comp.visible = False
        # progress_bar_comp has no visible flag — monkeypatch its draw methods
        self.progress_bar_comp.draw = lambda _: None
        self.progress_bar_comp.draw_overlays = lambda _: None

        # Whether the user has manually paused to review an older moment
        self._user_paused = False

        # Timestamp tracking for the live badge pulse
        self._live_badge_phase = 0.0

    # ------------------------------------------------------------------
    # Core overrides
    # ------------------------------------------------------------------

    def on_update(self, delta_time: float):
        self._live_badge_phase += delta_time

        # Sync track statuses from the feed
        new_statuses = self._live_feed.get_track_statuses()
        if new_statuses is not self.track_statuses:
            self.track_statuses = new_statuses

        # Sync the frame count — the frames list grows in the background
        new_count = len(self.frames)
        if new_count > self.n_frames:
            self.n_frames = new_count

        if self._user_paused or self.n_frames == 0:
            return

        # Jump to the latest frame so we always show live data
        self.frame_index = float(self.n_frames - 1)

        # Broadcast telemetry for any connected insights windows
        self._broadcast_telemetry_state()

    def on_draw(self):
        # Show a loading screen until the first frame arrives
        if self.n_frames == 0 or not self.frames:
            self._draw_loading_screen()
            return

        # Ensure frame_index is within bounds after a sync
        self.frame_index = min(self.frame_index, float(self.n_frames - 1))

        # Parent handles all track / driver / UI drawing
        super().on_draw()

        # Draw the LIVE badge on top of everything
        self._draw_live_badge()

        # If the user has paused, show a hint
        if self._user_paused:
            self._draw_paused_hint()

    # ------------------------------------------------------------------
    # Key handling — disable replay-only controls
    # ------------------------------------------------------------------

    def on_key_press(self, symbol: int, modifiers: int):
        # ESC: close
        if symbol == arcade.key.ESCAPE:
            arcade.close_window()
            return

        # SPACE: DVR-style pause/resume
        if symbol == arcade.key.SPACE:
            self._user_paused = not self._user_paused
            self.paused = self._user_paused
            return

        # Visual-only controls: pass through to parent
        if symbol in (
            arcade.key.D,   # DRS zone toggle
            arcade.key.B,   # progress bar toggle (hidden, harmless)
            arcade.key.L,   # driver label toggle
            arcade.key.H,   # help popup
        ):
            super().on_key_press(symbol, modifiers)
            return

        # LEFT arrow: when paused, step back through buffered frames
        if symbol == arcade.key.LEFT and self._user_paused:
            step = max(1, int(self.n_frames * 0.01))  # ~1% of buffer
            self.frame_index = max(0.0, self.frame_index - step)
            return

        # All other replay controls (speed, restart, seek) are not applicable

    def on_key_release(self, symbol: int, modifiers: int):
        # No hold-to-seek behaviour needed in live mode
        pass

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_loading_screen(self):
        self.clear()
        cx, cy = self.width // 2, self.height // 2
        arcade.draw_text(
            "Connecting to live timing\u2026",
            cx, cy + 20,
            arcade.color.WHITE, 26,
            anchor_x="center", anchor_y="center", bold=True,
        )
        arcade.draw_text(
            "Fetching data from OpenF1 \u2014 this may take a few seconds",
            cx, cy - 20,
            (160, 160, 160), 15,
            anchor_x="center", anchor_y="center",
        )
        # Animated dots
        dots = "." * (int(self._live_badge_phase * 2) % 4)
        arcade.draw_text(
            dots,
            cx, cy - 55,
            (200, 200, 200), 22,
            anchor_x="center", anchor_y="center",
        )

    def _draw_live_badge(self):
        """Pulsing red dot + 'LIVE' label in the top-right corner."""
        # Pulse between 60 % and 100 % brightness at ~1 Hz
        pulse = 0.5 + 0.5 * math.sin(self._live_badge_phase * math.pi * 2)
        r = int(200 + 55 * pulse)
        badge_x = self.width - 16
        badge_y = self.height - 16

        # Red circle
        arcade.draw_circle_filled(badge_x, badge_y, 7, (r, 40, 40))
        arcade.draw_circle_outline(badge_x, badge_y, 7, (255, 80, 80), 1)

        # "LIVE" text to the left of the dot
        arcade.draw_text(
            "LIVE",
            badge_x - 12, badge_y,
            (r, 40, 40), 13,
            bold=True,
            anchor_x="right", anchor_y="center",
        )

    def _draw_paused_hint(self):
        """Small banner reminding the user they're in DVR review mode."""
        msg = "PAUSED (reviewing buffer)  \u2190 step back   SPACE to go live"
        arcade.draw_text(
            msg,
            self.width // 2, 62,
            (240, 180, 0), 13,
            anchor_x="center", anchor_y="center", bold=True,
        )
