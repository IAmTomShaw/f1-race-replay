import os
import sys
import time
import threading
import logging
import math
import arcade
import numpy as np
from scipy.spatial import cKDTree
from typing import Dict
from src.f1_data import FPS
from src.lib.arcade_compat import ensure_arcade_compat
# TASK 4: streaming is now served by the new
# ``src.streaming.transport.TelemetryStreamServer`` which owns
# its own broker and dispatch thread. The server enforces
# SO_REUSEADDR, a state machine, bounded per-subscriber queues
# (drop-oldest), and non-blocking delivers. The on-the-wire
# payload is the protocol envelope (consumed by
# ``TelemetryStreamClientV2``); a wrapper preserves the
# legacy ``{"raw": ...}`` field for any V1 client still in
# the loop. The render loop enqueues into the broker via
# ``publish()`` and returns immediately; a slow client never
# stalls the render.
from src.streaming.broker import StreamingBroker
from src.streaming.protocol import MessageType
from src.streaming.transport import TelemetryStreamServer
from src.ui_components import (
    LeaderboardComponent,
    WeatherComponent,
    LegendComponent,
    DriverInfoComponent,
    RaceProgressBarComponent,
    RaceControlsComponent,
    ControlsPopupComponent,
    SessionInfoComponent,
    extract_race_events,
    build_track_from_example_lap,
    draw_finish_line
)
from src.tyre_degradation_integration import TyreDegradationIntegrator
# PHASE C: canonical replay clock. The legacy float
# ``self.frame_index`` accumulator in on_update is now
# delegated to a ReplayClock instance; the legacy attribute
# is preserved (and updated from the clock) so every existing
# reader keeps working unchanged.
from src.replay.clock import ReplayClock, Direction

# Enable DPI awareness on Windows for crisp rendering on high-DPI displays
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

ensure_arcade_compat(arcade)

SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
SCREEN_TITLE = "F1 Race Replay"
PLAYBACK_SPEEDS = [0.1, 0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0]


from src.lib.geometry import (
    _is_finite_coord,
    is_finite_coord,
    format_wind_direction as _geom_format_wind_direction,
    interpolate_points as _geom_interpolate_points,
)
from src.analytics.lap_time_analyzer import (
    compute_lap_times as _compute_lap_times_impl,
    estimate_official_replay_time_offset as _estimate_official_replay_time_offset_impl,
    attach_replay_aligned_lap_times as _attach_replay_aligned_lap_times_impl,
    fill_missing_official_tyre_life as _fill_missing_official_tyre_life_impl,
    compute_fallback_lap_times_raw as _compute_fallback_lap_times_raw_impl,
    classify_lap_entries as _classify_lap_entries_impl,
    compute_status_laps as _compute_status_laps_impl,
)
from src.ui.text_cache import TEXT_CACHE, set_text_if_changed as _shared_set_text_if_changed


class F1RaceReplayWindow(arcade.Window):
    def __init__(self, frames, track_statuses, example_lap, drivers, title,
                 playback_speed=1.0, driver_colors=None, circuit_rotation=0.0,
                 left_ui_margin=340, right_ui_margin=260, total_laps=None, visible_hud=True,
                 session_info=None, session=None, enable_telemetry=False,
                 race_control_messages=None):
        # Set resizable to True so the user can adjust mid-sim
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, title, resizable=True, antialiasing=True, samples=4)
        if hasattr(self, "maximize"):
            try:
                self.maximize()
            except Exception:
                pass

        # TASK 4: live streaming uses the new transport. The
        # server owns its own broker and dispatch thread; a
        # slow client can never stall the render loop because
        # the server's bounded per-subscriber queue
        # (drop-oldest) absorbs backpressure. The render path
        # enqueues into ``self._broker`` and returns
        # immediately.
        self.telemetry_stream = None
        self._broker = None
        self._telemetry_server = None
        if enable_telemetry:
            session_id = (f"race-{getattr(session, 'name', 'session')}"
                          if session is not None else "race")
            self._broker = StreamingBroker(session_id=session_id,
                                           queue_capacity=64)
            try:
                self._telemetry_server = TelemetryStreamServer(
                    self._broker, host="localhost", port=9999,
                )
                self._telemetry_server.start()
                # Public attribute kept for back-compat with any
                # consumer that introspects the stream. The new
                # server exposes ``.bound_port`` and a clean
                # state machine rather than the legacy
                # ``.broadcast`` API.
                self.telemetry_stream = self._telemetry_server
                print(f"Telemetry stream server started on "
                      f"localhost:{self._telemetry_server.bound_port}")
            except OSError as e:
                print(f"Failed to start telemetry server: {e}")
                print("Continuing without telemetry streaming...")
                self.telemetry_stream = None
                self._telemetry_server = None
            except Exception as e:
                print(f"Error starting telemetry server: {e}")
                self.telemetry_stream = None
                self._telemetry_server = None

        # Structured logger (lazy import so the legacy logger-free
        # path still works).
        import logging
        self._broker_logger = logging.getLogger("f1_replay.streaming.broker")

        self.frames = frames
        self.track_statuses = track_statuses
        self.race_control_messages = race_control_messages or []
        self.n_frames = len(frames)
        self.drivers = list(drivers)
        self.playback_speed = PLAYBACK_SPEEDS[PLAYBACK_SPEEDS.index(playback_speed)] if playback_speed in PLAYBACK_SPEEDS else 1.0
        self.driver_colors = driver_colors or {}
        # PHASE C: canonical replay clock owns the time source.
        # The total_seconds is the resampled frames' last t; for
        # robustness we use n_frames / FPS. Legacy
        # ``self.frame_index`` / ``self.paused`` are kept as
        # attributes and updated from the clock each tick so
        # every other reader of those attributes keeps working.
        _total_replay_s = float(self.n_frames) / float(FPS) if FPS else 0.0
        self._clock = ReplayClock(total_seconds=_total_replay_s,
                                    fps=FPS,
                                    initial_speed=self.playback_speed)
        self._frame_index = 0.0  # mirror of clock.frame_index (legacy)
        self.paused = False
        self.total_laps = total_laps
        self.has_weather = any("weather" in frame for frame in frames) if frames else False

        # Pre-compute per-driver lap times from the full frame data.
        # This avoids playback-speed-dependent sampling errors when insight
        # windows try to derive lap times from the streamed frames.
        self._precomputed_lap_times = self._compute_lap_times(frames, session)
        self._precomputed_status_laps = self._compute_status_laps(frames, track_statuses)
        self.visible_hud = visible_hud # If it displays HUD or not (leaderboard, controls, weather, etc)

        # Rotation (degrees) to apply to the whole circuit around its centre
        self.circuit_rotation = circuit_rotation
        self._rot_rad = float(np.deg2rad(self.circuit_rotation)) if self.circuit_rotation else 0.0
        self._cos_rot = float(np.cos(self._rot_rad))
        self._sin_rot = float(np.sin(self._rot_rad))
        self.finished_drivers = []
        self.left_ui_margin = left_ui_margin
        self.right_ui_margin = right_ui_margin
        self.toggle_drs_zones = True 
        self.show_driver_labels = False
        # UI components
        leaderboard_x = max(20, self.width - self.right_ui_margin + 12)
        self.leaderboard_comp = LeaderboardComponent(x=leaderboard_x, width=240, visible=visible_hud)
        self.weather_comp = WeatherComponent(left=20, top_offset=170, visible=visible_hud)
        self.legend_comp = LegendComponent(x=max(12, self.left_ui_margin - 320), visible=visible_hud)
        self.driver_info_comp = DriverInfoComponent(left=20, width=300)
        self.controls_popup_comp = ControlsPopupComponent()

        self.controls_popup_comp.set_size(340, 250) # width/height of the popup box
        self.controls_popup_comp.set_font_sizes(header_font_size=16, body_font_size=13) # adjust font sizes
        self.degradation_integrator = None
        if session is not None:
            try:
                print("Initializing tyre degradation model...")
                self.degradation_integrator = TyreDegradationIntegrator(session=session)
                
                # This computes curves once at startup (1-2 seconds)
                init_success = self.degradation_integrator.initialize_from_session()
                
                if init_success:
                    print("[OK] Tyre degradation model initialized successfully")
                    # Link integrator to driver info component
                    self.driver_info_comp.degradation_integrator = self.degradation_integrator
                else:
                    print("[ERROR] Tyre degradation model initialization failed")
                    self.degradation_integrator = None
            except Exception as e:
                print(f"[ERROR] Tyre degradation initialization error: {e}")
                self.degradation_integrator = None
        else:
            print("Note: Session not provided, tyre degradation disabled")


        # Progress bar component with race event markers
        self.progress_bar_comp = RaceProgressBarComponent(
            left_margin=left_ui_margin,
            right_margin=right_ui_margin,
            bottom=30,
            height=24,
            marker_height=16
        )

        # Race control buttons component
        self.race_controls_comp = RaceControlsComponent(
            center_x=self.width // 2,
            center_y=100,
            visible = visible_hud
        )
        
        # Session info banner component
        self.session_info_comp = SessionInfoComponent(visible=visible_hud)
        self.circuit_length_m = session_info.get('circuit_length_m') if session_info else None
        if session_info:
            self.session_info_comp.set_info(
                event_name=session_info.get('event_name', ''),
                circuit_name=session_info.get('circuit_name', ''),
                country=session_info.get('country', ''),
                year=session_info.get('year'),
                round_num=session_info.get('round'),
                date=session_info.get('date', ''),
                total_laps=total_laps
            )

        self.is_rewinding = False
        self.is_forwarding = False
        self.was_paused_before_hold = False
        
        # Extract race events for the progress bar
        race_events = extract_race_events(frames, track_statuses, total_laps or 0)
        self.progress_bar_comp.set_race_data(
            total_frames=len(frames),
            total_laps=total_laps or 0,
            events=race_events
        )

        # Enrich example_lap with all race DRS activations so DRS zones are never empty
        try:
            from src.f1_data import enrich_example_lap_drs_from_frames
            example_lap = enrich_example_lap_drs_from_frames(example_lap, frames)
        except Exception:
            pass

        # Build track geometry (Raw World Coordinates)
        (self.plot_x_ref, self.plot_y_ref,
         self.x_inner, self.y_inner,
         self.x_outer, self.y_outer,
         self.x_min, self.x_max,
         self.y_min, self.y_max, self.drs_zones) = build_track_from_example_lap(example_lap)

        # Build a dense reference polyline (used for projecting car (x,y) -> along-track distance)
        ref_points = self._interpolate_points(self.plot_x_ref, self.plot_y_ref, interp_points=4000)
        # store as numpy arrays for vectorized ops
        self._ref_xs = np.array([p[0] for p in ref_points])
        self._ref_ys = np.array([p[1] for p in ref_points])

        # Calculate normals for the reference line
        dx = np.gradient(self._ref_xs)
        dy = np.gradient(self._ref_ys)
        norm = np.sqrt(dx**2 + dy**2)
        norm[norm == 0] = 1.0
        self._ref_nx = -dy / norm
        self._ref_ny = dx / norm

        # Build KD-Tree for fast closest-point lookup
        self.track_tree = cKDTree(np.column_stack((self._ref_xs, self._ref_ys)))

        # Determine track winding using the shoelace formula to ensure normals point outwards.
        # A positive area indicates counter-clockwise winding (normals point Left=Inside, so we flip).
        # A negative area indicates clockwise winding (normals point Left=Outside, so we keep).
        signed_area = np.sum(self._ref_xs[:-1] * self._ref_ys[1:] - self._ref_xs[1:] * self._ref_ys[:-1])
        signed_area += (self._ref_xs[-1] * self._ref_ys[0] - self._ref_xs[0] * self._ref_ys[-1])
        if signed_area > 0:
            self._ref_nx = -self._ref_nx
            self._ref_ny = -self._ref_ny

        # cumulative distances along the reference polyline (metres)
        diffs = np.sqrt(np.diff(self._ref_xs)**2 + np.diff(self._ref_ys)**2)
        self._ref_seg_len = diffs
        self._ref_cumdist = np.concatenate(([0.0], np.cumsum(diffs)))
        self._ref_total_length = float(self._ref_cumdist[-1]) if len(self._ref_cumdist) > 0 else 0.0

        # Pre-calculate interpolated world points ONCE (optimization)
        self.world_inner_points = self._interpolate_points(self.x_inner, self.y_inner)
        self.world_outer_points = self._interpolate_points(self.x_outer, self.y_outer)

        # These will hold the actual screen coordinates to draw
        self.screen_inner_points = []
        self.screen_outer_points = []
        # Cache for static track line shapes: track_color -> (inner_shape, outer_shape)
        self._track_shapes = {}
        
        # Scaling parameters (initialized to 0, calculated in update_scaling)
        self.world_scale = 1.0
        self.tx = 0
        self.ty = 0

        # Load Background
        bg_path = os.path.join("resources", "background.png")
        self.bg_texture = arcade.load_texture(bg_path) if os.path.exists(bg_path) else None

        arcade.set_background_color(arcade.color.BLACK)

        # Persistent UI Text objects (avoid per-frame allocations)
        self.lap_text = arcade.Text("", 20, self.height - 40, arcade.color.WHITE, 24, anchor_y="top")
        self.time_text = arcade.Text("", 20, self.height - 80, arcade.color.WHITE, 20, anchor_y="top")
        self.status_text = arcade.Text("", 20, self.height - 120, arcade.color.WHITE, 24, bold=True, anchor_y="top")

        # Trigger initial scaling calculation
        self.update_scaling(self.width, self.height)

        # Selection & hit-testing state for leaderboard
        self.selected_driver = None
        self.selected_drivers = []
        self.leaderboard_rects = []  # list of tuples: (code, left, bottom, right, top)
        # store previous leaderboard order for up/down arrows
        self.last_leaderboard_order = None
        
        # Broadcast initial telemetry state
        self._broadcast_telemetry_state()

    @property
    def frame_index(self) -> float:
        return getattr(self, "_frame_index", 0.0)

    @frame_index.setter
    def frame_index(self, value: float):
        self._frame_index = float(value)
        if hasattr(self, "_clock") and self._clock is not None:
            max_idx = max(0, getattr(self, "n_frames", 1) - 1)
            clamped_f = max(0.0, min(float(value), float(max_idx)))
            self._clock.seek(clamped_f * self._clock.dt)

    def _broadcast_telemetry_state(self):
        """Broadcast current telemetry state to connected clients.

        TASK 4: enqueues onto the bounded broker. The new
        transport's dispatch thread does the network I/O so
        a slow client cannot stall the render loop.
        """
        if getattr(self, "_broker", None) is None:
            return

        current_frame = (self.frames[min(int(self.frame_index),
                                          len(self.frames) - 1)]
                          if self.frames else None)

        # Get current track status
        current_track_status = "GREEN"
        if current_frame:
            current_time = current_frame["t"]
            for status in self.track_statuses:
                if (current_time >= status["start_time"] and
                    (status["end_time"] is None or current_time <= status["end_time"])):
                    current_track_status = status["status"]

        # Calculate leader info
        leader_code = ""
        leader_lap = 1
        if current_frame and "drivers" in current_frame:
            driver_progress = {}
            for code, pos in current_frame["drivers"].items():
                x, y = pos.get("x"), pos.get("y")
                lap_raw = pos.get("lap", 1)
                try:
                    lap = int(lap_raw)
                except (ValueError, TypeError):
                    lap = 1
                if _is_finite_coord(x, y):
                    projected_m = self._project_to_reference(x, y)
                    if projected_m is not None:
                        progress_m = float((max(lap, 1) - 1) * self._ref_total_length + projected_m)
                        driver_progress[code] = progress_m
                        if self._ref_total_length > 0:
                            pos["fraction"] = (projected_m / self._ref_total_length) % 1.0
                        else:
                            pos["fraction"] = 0.0

            if driver_progress:
                leader_code = max(driver_progress.keys(), key=lambda c: driver_progress[c])
                leader_lap = current_frame["drivers"][leader_code].get("lap", 1)

        # Format time
        t = current_frame["t"] if current_frame else 0
        hours = int(t // 3600)
        minutes = int((t % 3600) // 60)
        seconds = int(t % 60)
        time_str = f"{hours:02}:{minutes:02}:{seconds:02}"

        # Gather all race control events up to the current frame time.
        # Sends the full history every broadcast so newly opened windows
        # receive all past events immediately.  The list is small (30-80
        # messages per race) and the window de-duplicates on its end.
        rc_events = []
        if current_frame and self.race_control_messages:
            frame_time = current_frame["t"]
            for msg in self.race_control_messages:
                if msg["time"] <= frame_time:
                    rc_events.append(msg)
                else:
                    break  # list is sorted, nothing further will match

        hex_driver_colors = {
            code: "#{:02X}{:02X}{:02X}".format(*rgb)
            for code, rgb in self.driver_colors.items()
        }
        payload = {
            "frame_index": int(self.frame_index),
            "frame": current_frame,
            "track_status": current_track_status,
            "playback_speed": self.playback_speed,
            "is_paused": self.paused,
            "total_frames": self.n_frames,
            "circuit_length_m": self.circuit_length_m,
            "driver_colors": hex_driver_colors,
            "has_rc_data": bool(self.race_control_messages),
            "race_control_events": rc_events,
            "session_data": {
                "time": time_str,
                "time_s": float(t),
                "lap": leader_lap,
                "leader": leader_code,
                "total_laps": self.total_laps
            }
        }

        # Send every ~2s so reconnecting clients receive geometry without special handling
        if hasattr(self, 'plot_x_ref') and int(self.frame_index) % 60 == 0:
            payload["track_geometry"] = {
                "x": self.plot_x_ref.tolist(),
                "y": self.plot_y_ref.tolist(),
                "x_inner": self.x_inner.tolist(),
                "y_inner": self.y_inner.tolist(),
                "x_outer": self.x_outer.tolist(),
                "y_outer": self.y_outer.tolist(),
                "rotation_deg": self.circuit_rotation,
                "drs_zones": getattr(self, "drs_zones", []),
            }

        # Send pre-computed data continuously. It's just a Python dictionary reference
        # (O(1) memory overhead in local publish/subscribe) and ensures windows
        # opened after the race has finished still receive the data.
        payload["lap_times"] = self._precomputed_lap_times
        payload["status_laps"] = self._precomputed_status_laps

        # TASK 4: publish through the broker. The render thread
        # returns immediately; the new transport's own dispatch
        # thread does the network I/O so a slow client cannot
        # stall the render. The on-the-wire payload is the
        # protocol envelope (consumed by ``TelemetryStreamClientV2``).
        if self._broker is None:
            return
        self._broker.publish(MessageType.FRAME_UPDATE, payload)

    @staticmethod
    def _compute_lap_times(frames, session=None):
        return _compute_lap_times_impl(frames, session=session)

    @staticmethod
    def _estimate_official_replay_time_offset(official_result, fallback_result):
        return _estimate_official_replay_time_offset_impl(official_result, fallback_result)

    @staticmethod
    def _attach_replay_aligned_lap_times(result, replay_time_offset_s, fallback_result=None):
        return _attach_replay_aligned_lap_times_impl(result, replay_time_offset_s, fallback_result=fallback_result)

    @staticmethod
    def _fill_missing_official_tyre_life(result):
        return _fill_missing_official_tyre_life_impl(result)

    @staticmethod
    def _compute_fallback_lap_times_raw(frames, min_lap_time_s=30.0, max_lap_time_s=7200.0):
        return _compute_fallback_lap_times_raw_impl(
            frames, min_lap_time_s=min_lap_time_s, max_lap_time_s=max_lap_time_s
        )

    @staticmethod
    def _classify_lap_entries(result, official_data=False):
        return _classify_lap_entries_impl(result, official_data=official_data)

    @staticmethod
    def _compute_status_laps(frames, track_statuses):
        return _compute_status_laps_impl(frames, track_statuses)

    def _interpolate_points(self, xs, ys, interp_points=2000):
        return _geom_interpolate_points(xs, ys, interp_points=interp_points)

    def _project_to_reference(self, x, y):
        if not _is_finite_coord(x, y):
            return None

        if self._ref_total_length == 0.0:
            return 0.0

        # Vectorized nearest-point lookup using KD-Tree (O(log N))
        _, idx = self.track_tree.query([x, y])
        idx = int(idx)

        # For a slightly better estimate, optionally project onto the adjacent segment
        if idx < len(self._ref_xs) - 1:

            x1, y1 = self._ref_xs[idx], self._ref_ys[idx]
            x2, y2 = self._ref_xs[idx+1], self._ref_ys[idx+1]
            vx, vy = x2 - x1, y2 - y1
            seg_len2 = vx*vx + vy*vy
            if seg_len2 > 0:
                t = ((x - x1) * vx + (y - y1) * vy) / seg_len2
                t_clamped = max(0.0, min(1.0, t))
                proj_x = x1 + t_clamped * vx
                proj_y = y1 + t_clamped * vy
                # distance along segment from x1,y1
                seg_dist = np.sqrt((proj_x - x1)**2 + (proj_y - y1)**2)
                return float(self._ref_cumdist[idx] + seg_dist)

        # Fallback: return the cumulative distance at the closest dense sample
        return float(self._ref_cumdist[idx])

    def update_scaling(self, screen_w, screen_h):
        """
        Recalculates the scale and translation to fit the track 
        perfectly within the new screen dimensions while maintaining aspect ratio.
        """
        padding = 0.05
        # If a rotation is applied, we must compute the rotated bounds
        world_cx = (self.x_min + self.x_max) / 2
        world_cy = (self.y_min + self.y_max) / 2

        def _rotate_about_center(x, y):
            # Translate to centre, rotate, translate back
            tx = x - world_cx
            ty = y - world_cy
            rx = tx * self._cos_rot - ty * self._sin_rot
            ry = tx * self._sin_rot + ty * self._cos_rot
            return rx + world_cx, ry + world_cy

        # Build rotated extents from inner/outer world points
        rotated_points = []
        for x, y in self.world_inner_points:
            rotated_points.append(_rotate_about_center(x, y))
        for x, y in self.world_outer_points:
            rotated_points.append(_rotate_about_center(x, y))

        xs = [p[0] for p in rotated_points]
        ys = [p[1] for p in rotated_points]
        world_x_min = min(xs) if xs else self.x_min
        world_x_max = max(xs) if xs else self.x_max
        world_y_min = min(ys) if ys else self.y_min
        world_y_max = max(ys) if ys else self.y_max

        world_w = max(1.0, world_x_max - world_x_min)
        world_h = max(1.0, world_y_max - world_y_min)
        
        # Reserve left/right UI margins before applying padding so the track
        # never overlaps side UI elements (leaderboard, telemetry, legends).
        inner_w = max(1.0, screen_w - self.left_ui_margin - self.right_ui_margin)
        usable_w = inner_w * (1 - 2 * padding)
        usable_h = screen_h * (1 - 2 * padding)

        # Calculate scale to fit whichever dimension is the limiting factor
        scale_x = usable_w / world_w
        scale_y = usable_h / world_h
        self.world_scale = min(scale_x, scale_y)

        # Center the world in the screen (rotation done about original centre)
        # world_cx/world_cy are unchanged by rotation about centre
        # Center within the available inner area (left_ui_margin .. screen_w - right_ui_margin)
        screen_cx = self.left_ui_margin + inner_w / 2
        screen_cy = screen_h / 2

        self.tx = screen_cx - self.world_scale * world_cx
        self.ty = screen_cy - self.world_scale * world_cy

        # Update the polyline screen coordinates based on new scale
        self.screen_inner_points = [self.world_to_screen(x, y) for x, y in self.world_inner_points]
        self.screen_outer_points = [self.world_to_screen(x, y) for x, y in self.world_outer_points]
        if hasattr(self, '_track_shapes') and self._track_shapes:
            self._track_shapes.clear()

    def _get_track_shapes(self, track_color):
        """Return cached pre-buffered Shape objects for inner and outer track lines."""
        if not hasattr(self, '_track_shapes'):
            self._track_shapes = {}
        shapes = self._track_shapes.get(track_color)
        if shapes is None and len(self.screen_inner_points) > 1 and len(self.screen_outer_points) > 1:
            try:
                inner_shape = arcade.create_line_strip(self.screen_inner_points, track_color, 5)
                outer_shape = arcade.create_line_strip(self.screen_outer_points, track_color, 5)
                shapes = (inner_shape, outer_shape)
                self._track_shapes[track_color] = shapes
            except Exception:
                shapes = None
        return shapes

    def on_resize(self, width, height):
        """Called automatically by Arcade when window is resized."""
        super().on_resize(width, height)
        self.update_scaling(width, height)
        # notify components
        self.leaderboard_comp.x = max(20, self.width - self.right_ui_margin + 12)
        for c in (self.leaderboard_comp, self.weather_comp, self.legend_comp, self.driver_info_comp, self.progress_bar_comp, self.race_controls_comp):
            c.on_resize(self)
        
        # update persistent text positions
        self.lap_text.x = 20
        self.lap_text.y = self.height - 40
        self.time_text.x = 20
        self.time_text.y = self.height - 80
        self.status_text.x = 20
        self.status_text.y = self.height - 120

    def world_to_screen(self, x, y):
        if not _is_finite_coord(x, y):
            return None, None

        # Rotate around the track centre (if rotation is set), then scale+translate
        world_cx = (self.x_min + self.x_max) / 2
        world_cy = (self.y_min + self.y_max) / 2

        if self._rot_rad:
            tx = x - world_cx
            ty = y - world_cy
            rx = tx * self._cos_rot - ty * self._sin_rot
            ry = tx * self._sin_rot + ty * self._cos_rot
            x, y = rx + world_cx, ry + world_cy

        sx = self.world_scale * x + self.tx
        sy = self.world_scale * y + self.ty
        return sx, sy

    def _format_wind_direction(self, degrees):
        return _geom_format_wind_direction(degrees)

    _text_cache: Dict[int, str] = TEXT_CACHE

    @staticmethod
    def _set_text_if_changed(text_obj, new_text: str) -> None:
        _shared_set_text_if_changed(text_obj, new_text, F1RaceReplayWindow._text_cache)

    def on_draw(self):
        self.clear()

        # 1. Draw Background (stretched to fit new window size)
        if self.bg_texture:
            arcade.draw_lrbt_rectangle_textured(
                left=0, right=self.width,
                bottom=0, top=self.height,
                texture=self.bg_texture
            )

        # 2. Draw Track (using pre-calculated screen points)
        idx = min(int(self.frame_index), self.n_frames - 1)
        frame = self.frames[idx]
        current_time = frame["t"]
        current_track_status = "GREEN"
        for status in self.track_statuses:
            if status['start_time'] <= current_time and (status['end_time'] is None or current_time < status['end_time']):
                current_track_status = status['status']
                break

        # Map track status -> colour (R,G,B)
        STATUS_COLORS = {
            "GREEN": (150, 150, 150),    # normal grey
            "YELLOW": (220, 180,   0),   # caution
            "RED": (200,  30,  30),      # red-flag
            "VSC": (200, 130,  50),      # virtual safety car / amber-brown
            "SC": (180, 100,  30),       # safety car (darker brown)
        }
        track_color = STATUS_COLORS.get("GREEN", (150, 150, 150))

        if current_track_status == "2":
            track_color = STATUS_COLORS.get("YELLOW")
        elif current_track_status == "4":
            track_color = STATUS_COLORS.get("SC")
        elif current_track_status == "5":
            track_color = STATUS_COLORS.get("RED")
        elif current_track_status == "6" or current_track_status == "7":
            track_color = STATUS_COLORS.get("VSC")
            
        track_shapes = self._get_track_shapes(track_color)
        if track_shapes is not None:
            track_shapes[0].draw()
            track_shapes[1].draw()
        else:
            if len(self.screen_inner_points) > 1:
                arcade.draw_line_strip(self.screen_inner_points, track_color, 5)
            if len(self.screen_outer_points) > 1:
                arcade.draw_line_strip(self.screen_outer_points, track_color, 5)
        
        # 2.5 Draw DRS Zones (green segments on outer track edge)
        if hasattr(self, 'drs_zones') and self.drs_zones and self.toggle_drs_zones:
            drs_color = (0, 255, 80)  # High-visibility bright green for DRS zones
            orig_len = len(self.x_outer) if hasattr(self, "x_outer") and self.x_outer is not None else 0
            interp_len = len(self.screen_outer_points) if hasattr(self, "screen_outer_points") and self.screen_outer_points else 0

            for _, zone in enumerate(self.drs_zones):
                start_idx = zone["start"]["index"]
                end_idx = zone["end"]["index"]
                if start_idx is None or end_idx is None:
                    continue

                drs_outer_points = []
                if orig_len > 1 and interp_len > 1:
                    i_start = max(0, min(int((start_idx / max(1, orig_len - 1)) * (interp_len - 1)), interp_len - 1))
                    i_end = max(0, min(int((end_idx / max(1, orig_len - 1)) * (interp_len - 1)), interp_len - 1))
                    if i_end >= i_start:
                        drs_outer_points = [
                            pt for pt in self.screen_outer_points[i_start:i_end + 1]
                            if pt is not None and pt[0] is not None and pt[1] is not None
                        ]
                if len(drs_outer_points) <= 1 and orig_len > 0:
                    for i in range(max(0, start_idx), min(end_idx + 1, orig_len)):
                        x = self.x_outer.iloc[i] if hasattr(self.x_outer, "iloc") else self.x_outer[i]
                        y = self.y_outer.iloc[i] if hasattr(self.y_outer, "iloc") else self.y_outer[i]
                        sx, sy = self.world_to_screen(x, y)
                        if sx is not None and sy is not None:
                            drs_outer_points.append((sx, sy))

                # Draw the DRS zone segment
                if len(drs_outer_points) > 1:
                    arcade.draw_line_strip(drs_outer_points, drs_color, 7)

        draw_finish_line(self)
        # 3. Draw Cars
        frame = self.frames[idx]
        
        # Get selected drivers list safely
        selected_drivers = getattr(self, "selected_drivers", [])
        if not selected_drivers and getattr(self, "selected_driver", None):
            selected_drivers = [self.selected_driver]

        for i, (code, pos) in enumerate(frame["drivers"].items()):
            x = pos.get("x")
            y = pos.get("y")
            if not _is_finite_coord(x, y):
                continue

            sx, sy = self.world_to_screen(x, y)
            color = self.driver_colors.get(code, arcade.color.WHITE)
            
            is_selected = code in selected_drivers
            
            if self.show_driver_labels or is_selected:
                # Find closest point index on reference track (Optimized KD-Tree)
                _, idx = self.track_tree.query([x, y])
                idx = int(idx)
                
                # Get normal vector in world space
                nx = self._ref_nx[idx]

                ny = self._ref_ny[idx]
                
                # Rotate normal to screen space
                if self._rot_rad:
                    snx = nx * self._cos_rot - ny * self._sin_rot
                    sny = nx * self._sin_rot + ny * self._cos_rot
                else:
                    snx, sny = nx, ny
                
                offset_dist = 45 if i % 2 == 0 else 75
                
                lx = sx + snx * offset_dist
                ly = sy + sny * offset_dist
                
                arcade.draw_line(sx, sy, lx, ly, color, 1)
                
                anchor_x = "left" if snx >= 0 else "right"
                text_padding = 3 if snx >= 0 else -3
                arcade.draw_text(code, lx + text_padding, ly, color, 10, anchor_x=anchor_x, anchor_y="center", bold=True)

            arcade.draw_circle_filled(sx, sy, 8, color)
        
        # 3b. Draw Safety Car (if active)
        sc_data = frame.get("safety_car")
        # The safety_car payload is produced by ``attach_sc`` in
        # ``src/replay/safety_car.py`` with one of three shapes:
        #   1. ``{"source": "none"}`` — no SC period active.
        #   2. ``{"source": "real", ...}`` — SC active but no
        #      leader found; no positional keys present.
        #   3. ``{"source": "simulated", "x": <val>, "y": <val>,
        #      ...}`` — SC active with a usable position; ``x`` /
        #      ``y`` may be None when the renderer is expected to
        #      derive them from the track polyline.
        # The legacy qualifying path also writes ``None`` for the
        # no-SC case. We accept both contracts by requiring a
        # non-``none`` source AND valid finite (x, y) before
        # rendering; otherwise we skip the SC overlay for this
        # frame and retain the rest of the replay.
        sc_x = sc_data.get("x") if isinstance(sc_data, dict) else None
        sc_y = sc_data.get("y") if isinstance(sc_data, dict) else None
        sc_source = sc_data.get("source") if isinstance(sc_data, dict) else None
        if (isinstance(sc_data, dict)
                and sc_source not in (None, "none")
                and (sc_x is None or sc_y is None)
                and getattr(self, "_ref_total_length", 0.0) > 0
                and len(getattr(self, "_ref_cumdist", [])) > 1):
            target_m = None
            sc_leader = sc_data.get("leader_code")
            offset_m = float(sc_data.get("offset_m", 150.0) or 150.0)
            if sc_leader and sc_leader in frame.get("drivers", {}):
                l_pos = frame["drivers"][sc_leader]
                lx, ly = l_pos.get("x"), l_pos.get("y")
                if _is_finite_coord(lx, ly):
                    l_proj = self._project_to_reference(lx, ly)
                    if l_proj is not None:
                        target_m = (l_proj + offset_m) % self._ref_total_length
            if target_m is None and sc_data.get("dist") is not None:
                try:
                    target_m = float(sc_data["dist"]) % self._ref_total_length
                except (TypeError, ValueError):
                    target_m = None
            if target_m is not None and math.isfinite(target_m):
                sc_x = float(np.interp(target_m, self._ref_cumdist, self._ref_xs))
                sc_y = float(np.interp(target_m, self._ref_cumdist, self._ref_ys))
        if (sc_data is not None
                and sc_source != "none"
                and sc_x is not None and sc_y is not None
                and math.isfinite(sc_x) and math.isfinite(sc_y)):
            sc_phase = sc_data.get("phase", "on_track")
            sc_alpha = sc_data.get("alpha", 1.0)
            
            sc_sx, sc_sy = self.world_to_screen(sc_x, sc_y)
            
            # Safety car color: bright orange/amber
            sc_base_color = (255, 165, 0)  # Orange
            
            # Calculate alpha for the car body
            body_alpha = int(255 * max(0.1, sc_alpha))
            sc_color_with_alpha = (*sc_base_color, body_alpha)
            
            # Pulsing glow effect during deploying/returning phases
            if sc_phase in ("deploying", "returning"):
                pulse = 0.5 + 0.5 * np.sin(time.time() * 8.0)  # Fast pulse
                glow_radius = 16 + pulse * 6
                glow_alpha = int(80 * sc_alpha * pulse)
                
                # Outer glow ring
                arcade.draw_circle_filled(sc_sx, sc_sy, glow_radius, (255, 200, 0, glow_alpha))
                arcade.draw_circle_outline(sc_sx, sc_sy, glow_radius + 2, (255, 100, 0, int(glow_alpha * 0.6)), 2)
                
                # Draw dashed trail line from pit to track position
                trail_alpha = int(120 * sc_alpha)
                trail_color = (255, 165, 0, trail_alpha)
                arcade.draw_circle_outline(sc_sx, sc_sy, 12, trail_color, 2)
            else:
                # Steady glow when on track
                arcade.draw_circle_filled(sc_sx, sc_sy, 14, (255, 165, 0, 40))
            
            # Draw SC body (larger than regular cars)
            arcade.draw_circle_filled(sc_sx, sc_sy, 8, sc_color_with_alpha)
            
            # Orange outline ring
            outline_alpha = int(255 * sc_alpha)
            arcade.draw_circle_outline(sc_sx, sc_sy, 9, (255, 100, 0, outline_alpha), 2)
            
            # "SC" label - always visible
            label_alpha = int(255 * max(0.3, sc_alpha))
            label_color = (255, 255, 255, label_alpha)
            arcade.draw_text(
                "SC", sc_sx + 14, sc_sy + 2, label_color, 11,
                anchor_x="left", anchor_y="center", bold=True
            )
            
            # Phase indicator text during transitions
            if sc_phase == "deploying":
                phase_text = "SC DEPLOYING"
                phase_color = (255, 200, 0, int(200 * sc_alpha))
                arcade.draw_text(
                    phase_text, sc_sx, sc_sy - 18, phase_color, 8,
                    anchor_x="center", anchor_y="top", bold=True
                )
            elif sc_phase == "returning":
                phase_text = "SC IN"
                phase_color = (255, 200, 0, int(200 * sc_alpha))
                arcade.draw_text(
                    phase_text, sc_sx, sc_sy - 18, phase_color, 8,
                    anchor_x="center", anchor_y="top", bold=True
                )

        
        # --- UI ELEMENTS (Dynamic Positioning) ---
        
        # Determine Leader info using projected along-track distance (more robust than dist)
        # Use the progress metric in metres for each driver and use that to order the leaderboard.
        driver_progress = {}
        for code, pos in frame["drivers"].items():
            # parse lap defensively
            lap_raw = pos.get("lap", 1)
            try:
                lap = int(lap_raw)
            except Exception:
                lap = 1

            x = pos.get("x")
            y = pos.get("y")
            if _is_finite_coord(x, y):
                # Project (x,y) to reference and combine with lap count
                projected_m = self._project_to_reference(x, y)
                if projected_m is not None:
                    # progress in metres since race start: (lap-1) * lap_length + projected_m
                    progress_m = float((max(lap, 1) - 1) * self._ref_total_length + projected_m)
                    driver_progress[code] = progress_m

        # Leader is the one with greatest progress_m
        if driver_progress:
            leader_code = max(driver_progress, key=lambda c: driver_progress[c])
            leader_lap = frame["drivers"][leader_code].get("lap", 1)
        else:
            leader_code = None
            leader_lap = 1

        # Time Calculation
        t = frame["t"]
        hours = int(t // 3600)
        minutes = int((t % 3600) // 60)
        seconds = int(t % 60)
        time_str = f"{hours:02}:{minutes:02}:{seconds:02}"

        # Format Lap String 
        lap_str = f"Lap: {leader_lap}"
        if self.total_laps is not None:
            lap_str += f"/{self.total_laps}"

        # Draw HUD - Top Left
        if self.visible_hud:
            # lap_text changes only when the leader completes a lap
            # (low frequency); no guard needed.
            self.lap_text.text = lap_str
            # time_text and status_text are checked via the per-object
            # cache so identical assignments do not trigger a
            # pyglet text-layout rebuild and font-glyph cache growth.
            F1RaceReplayWindow._set_text_if_changed(
                self.time_text,
                f"Race Time: {time_str} (x{self.playback_speed})",
            )
            F1RaceReplayWindow._set_text_if_changed(
                self.status_text, "",
            )
            # update status color and text if required
            if current_track_status == "2":
                F1RaceReplayWindow._set_text_if_changed(
                    self.status_text, "YELLOW FLAG",
                )
                self.status_text.color = arcade.color.YELLOW
            elif current_track_status == "5":
                F1RaceReplayWindow._set_text_if_changed(
                    self.status_text, "RED FLAG",
                )
                self.status_text.color = arcade.color.RED
            elif current_track_status == "6":
                F1RaceReplayWindow._set_text_if_changed(
                    self.status_text, "VIRTUAL SAFETY CAR",
                )
                self.status_text.color = arcade.color.ORANGE
            elif current_track_status == "4":
                F1RaceReplayWindow._set_text_if_changed(
                    self.status_text, "SAFETY CAR",
                )
                self.status_text.color = arcade.color.BROWN

            self.lap_text.draw()
            self.time_text.draw()
            if self.status_text.text:
                self.status_text.draw()

        # Weather component (set info then draw)
        weather_info = frame.get("weather") if frame else None
        self.weather_comp.set_info(weather_info)
        self.weather_comp.draw(self)
        # optionally expose weather_bottom for driver info layout
        self.weather_bottom = self.height - 170 - 130 if (weather_info or self.has_weather) else None

        # Draw leaderboard via component (preserve last known progress across brief telemetry gaps)
        if not hasattr(self, "_last_driver_progress"):
            self._last_driver_progress = {}
        driver_list = []
        for code, pos in frame["drivers"].items():
            color = self.driver_colors.get(code, arcade.color.WHITE)
            if code in driver_progress:
                progress_m = driver_progress[code]
                self._last_driver_progress[code] = progress_m
            else:
                raw_dist = pos.get("dist")
                if raw_dist is not None and isinstance(raw_dist, (int, float)) and math.isfinite(raw_dist):
                    progress_m = float(raw_dist)
                    self._last_driver_progress[code] = progress_m
                else:
                    progress_m = self._last_driver_progress.get(code, 0.0)
            driver_list.append((code, color, pos, progress_m))
        def _lb_sort_key(item):
            _code, _col, _pos, _prog = item
            val_state = _pos.get("validity")
            is_retired = (
                val_state in ("dnf", "post", "dns")
                or (val_state is None and _pos.get("active") is False)
                or _pos.get("rel_dist") == 1
            )
            in_pit = bool(_pos.get("in_pit", False))
            safe_prog = _prog if (isinstance(_prog, (int, float)) and math.isfinite(_prog)) else 0.0
            return (1 if is_retired else 0, 1 if in_pit else 0, -safe_prog, _code)
        driver_list.sort(key=_lb_sort_key)

        self.last_leaderboard_order = [c for c, _, _, _ in driver_list]
        self.leaderboard_comp.set_entries(driver_list)
        self.leaderboard_comp.draw(self)
        # expose rects for existing hit test compatibility if needed
        self.leaderboard_rects = self.leaderboard_comp.rects

        # Controls Legend - Bottom Left (keeps small offset from left UI edge)
        self.legend_comp.draw(self)
        
        # Selected driver info component
        self.driver_info_comp.draw(self)
        
        # Race Progress Bar with event markers (DNF, flags, leader changes)
        self.progress_bar_comp.draw(self)
        
        # Race playback control buttons
        self.race_controls_comp.draw(self)
        
        # Session info banner (top of screen)
        self.session_info_comp.draw(self)

        # Draw Controls popup box
        self.controls_popup_comp.draw(self)
        
        # Draw tooltips and overlays on top of everything
        self.progress_bar_comp.draw_overlays(self)
                    
    def on_update(self, delta_time: float):
        self.race_controls_comp.on_update(delta_time)

        seek_speed = 3.0 * max(1.0, self.playback_speed) # Multiplier for seeking speed, scales with current playback speed
        if self.is_rewinding:
            self.frame_index = max(0.0, self.frame_index - delta_time * FPS * seek_speed)
            self.race_controls_comp.flash_button('rewind')
            self._broadcast_telemetry_state()
        elif self.is_forwarding:
            self.frame_index = min(self.n_frames - 1, self.frame_index + delta_time * FPS * seek_speed)
            self.race_controls_comp.flash_button('forward')
            self._broadcast_telemetry_state()

        if self.paused:
            return

        # PHASE C: delegate the per-frame time advance to the
        # canonical ReplayClock. The clock is the single source
        # of truth for replay time; legacy self.frame_index is
        # mirrored from it for back-compat with the rest of the
        # render code (UI components, broadcast payload, etc.).
        self._clock.set_speed(self.playback_speed)
        self._clock.tick(delta_time)
        # Clamp to the last valid frame and mirror.
        if self._clock.frame_index >= self.n_frames - 1 or self._clock.at_end:
            self._clock.seek_frame(max(0, self.n_frames - 1))
            self.paused = True
        self._frame_index = float(self._clock.frame_index)

        # Broadcast telemetry state during playback
        self._broadcast_telemetry_state()

    def on_key_press(self, symbol: int, modifiers: int):
        # Allow ESC to close window at any time
        if symbol == arcade.key.ESCAPE:
            arcade.close_window()
            return
        if symbol == arcade.key.SPACE:
            self.paused = not self.paused
            self._broadcast_telemetry_state()
            self.race_controls_comp.flash_button('play_pause')
        elif symbol == arcade.key.RIGHT:
            self.was_paused_before_hold = self.paused
            self.is_forwarding = True
            self.paused = True
        elif symbol == arcade.key.LEFT:
            self.was_paused_before_hold = self.paused
            self.is_rewinding = True
            self.paused = True
        elif symbol == arcade.key.UP:
            if self.playback_speed < PLAYBACK_SPEEDS[-1]:
                # Increase to next higher speed
                for spd in PLAYBACK_SPEEDS:
                    if spd > self.playback_speed:
                        self.playback_speed = spd
                        self._broadcast_telemetry_state()
                        break
            self.race_controls_comp.flash_button('speed_increase')
        elif symbol == arcade.key.DOWN:
            if self.playback_speed > PLAYBACK_SPEEDS[0]:
                # Decrease to next lower speed
                for spd in reversed(PLAYBACK_SPEEDS):
                    if spd < self.playback_speed:
                        self.playback_speed = spd
                        self._broadcast_telemetry_state()
                        break
            self.race_controls_comp.flash_button('speed_decrease')
        elif symbol == arcade.key.KEY_1:
            self.playback_speed = 0.5
            self._broadcast_telemetry_state()
            self.race_controls_comp.flash_button('speed_decrease')
        elif symbol == arcade.key.KEY_2:
            self.playback_speed = 1.0
            self._broadcast_telemetry_state()
            self.race_controls_comp.flash_button('speed_decrease')
        elif symbol == arcade.key.KEY_3:
            self.playback_speed = 2.0
            self._broadcast_telemetry_state()
            self.race_controls_comp.flash_button('speed_increase')
        elif symbol == arcade.key.KEY_4:
            self.playback_speed = 4.0
            self._broadcast_telemetry_state()
            self.race_controls_comp.flash_button('speed_increase')
        elif symbol == arcade.key.R:
            if hasattr(self, "_clock") and self._clock is not None:
                self._clock.restart()
                self._clock.set_speed(1.0)
            self.frame_index = 0.0
            self.playback_speed = 1.0
            self._broadcast_telemetry_state()
            # Clear degradation cache on restart
            if self.degradation_integrator:
                self.degradation_integrator.clear_cache()
            self.race_controls_comp.flash_button('rewind')
        elif symbol == arcade.key.D:
            self.toggle_drs_zones = not self.toggle_drs_zones
        elif symbol == arcade.key.L:
            self.show_driver_labels = not self.show_driver_labels
        elif symbol == arcade.key.H:
            # Toggle Controls popup with 'H' key — show anchored to bottom-left with 20px margin
            margin_x = 20
            margin_y = 20
            left_pos = float(margin_x)
            top_pos = float(margin_y + self.controls_popup_comp.height)
            if self.controls_popup_comp.visible:
                self.controls_popup_comp.hide()
            else:
                self.controls_popup_comp.show_over(left_pos, top_pos)
        elif symbol == arcade.key.B:
            is_vis = self.progress_bar_comp.toggle_visibility() # toggle progress bar visibility
            if is_vis and not self.toggle_drs_zones:
                self.toggle_drs_zones = True
        elif symbol == arcade.key.I:
            self.session_info_comp.toggle_visibility() # toggle session info banner

    def on_key_release(self, symbol: int, modifiers: int):
        if symbol == arcade.key.RIGHT:
            self.is_forwarding = False
            self.paused = self.was_paused_before_hold
        elif symbol == arcade.key.LEFT:
            self.is_rewinding = False
            self.paused = self.was_paused_before_hold

    def on_mouse_release(self, x: float, y: float, button: int, modifiers: int):
        if self.is_forwarding or self.is_rewinding:
            self.is_forwarding = False
            self.is_rewinding = False
            self.paused = self.was_paused_before_hold

    def on_mouse_press(self, x: float, y: float, button: int, modifiers: int):
        # forward to components; stop at first that handled it
        if self.controls_popup_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.race_controls_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.progress_bar_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.leaderboard_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        if self.legend_comp.on_mouse_press(self, x, y, button, modifiers):
            return
        # default: clear selection if clicked elsewhere
        self.selected_driver = None
        self.selected_drivers = []
        
    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        """Handle mouse motion for hover effects on progress bar and controls."""
        self.progress_bar_comp.on_mouse_motion(self, x, y, dx, dy)
        self.race_controls_comp.on_mouse_motion(self, x, y, dx, dy)
        
    def close(self):
        """Clean up resources when window closes."""
        # Clear the per-text-object cache so a future window
        # instance starts with a clean state.
        F1RaceReplayWindow._text_cache.clear()
        # TASK 4: stop the new transport (which also stops its
        # internal broker dispatch thread).
        if getattr(self, "_telemetry_server", None) is not None:
            try:
                self._telemetry_server.stop()
            except Exception:
                pass
            self._telemetry_server = None
        elif hasattr(self, 'telemetry_stream') and self.telemetry_stream:
            # Defensive fallback: legacy server if a subclass
            # constructed one directly.
            try:
                self.telemetry_stream.stop()
            except Exception:
                pass
        self.telemetry_stream = None
        super().close()
