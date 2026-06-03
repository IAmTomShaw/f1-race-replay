import os
import time
import arcade
import numpy as np
from scipy.spatial import cKDTree
from src.f1_data import FPS
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
from src.services.stream import TelemetryStreamServer


SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
SCREEN_TITLE = "F1 Race Replay"
PLAYBACK_SPEEDS = [0.1, 0.2, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0, 128.0, 256.0]

class F1RaceReplayWindow(arcade.Window):
    def __init__(self, frames, track_statuses, example_lap, drivers, title,
                 playback_speed=1.0, driver_colors=None, circuit_rotation=0.0,
                 left_ui_margin=340, right_ui_margin=260, total_laps=None, visible_hud=True,
                 session_info=None, session=None, enable_telemetry=False,
                 race_control_messages=None):
        # Set resizable to True so the user can adjust mid-sim
        super().__init__(SCREEN_WIDTH, SCREEN_HEIGHT, title, resizable=True)
        self.maximize()

        self.telemetry_stream = None
        if enable_telemetry:
            try:
                self.telemetry_stream = TelemetryStreamServer()
                self.telemetry_stream.start()
                print("Telemetry stream server started on localhost:9999")
            except OSError as e:
                print(f"Failed to start telemetry server: {e}")
                print("Continuing without telemetry streaming...")
                self.telemetry_stream = None
            except Exception as e:
                print(f"Error starting telemetry server: {e}")
                self.telemetry_stream = None

        self.frames = frames
        self.track_statuses = track_statuses
        self.race_control_messages = race_control_messages or []
        self.n_frames = len(frames)
        self.drivers = list(drivers)
        self.playback_speed = PLAYBACK_SPEEDS[PLAYBACK_SPEEDS.index(playback_speed)] if playback_speed in PLAYBACK_SPEEDS else 1.0
        self.driver_colors = driver_colors or {}
        self.frame_index = 0.0  # use float for fractional-frame accumulation
        self.paused = False
        self.total_laps = total_laps
        self.has_weather = any("weather" in frame for frame in frames) if frames else False
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
                    print("✓ Tyre degradation model initialized successfully")
                    # Link integrator to driver info component
                    self.driver_info_comp.degradation_integrator = self.degradation_integrator
                else:
                    print("✗ Tyre degradation model initialization failed")
                    self.degradation_integrator = None
            except Exception as e:
                print(f"✗ Tyre degradation initialization error: {e}")
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
        self.leaderboard_rects = []  # list of tuples: (code, left, bottom, right, top)
        # store previous leaderboard order for up/down arrows
        self.last_leaderboard_order = None

        # Precompute time-based gaps for the entire race once at startup.
        # This runs after all track geometry is initialised (track_tree,
        # _ref_cumdist, _ref_total_length) and injects gap_to_leader and
        # gap_to_car_ahead into every frame["drivers"][code] dict so the
        # leaderboard can display correct values with zero per-frame cost.
        self._precompute_gaps()

        # Broadcast initial telemetry state
        self._broadcast_telemetry_state()

    def _broadcast_telemetry_state(self):
        """Broadcast current telemetry state to connected clients."""
        if not hasattr(self, 'telemetry_stream') or not self.telemetry_stream:
            return
            
        current_frame = self.frames[min(int(self.frame_index), len(self.frames) - 1)] if self.frames else None
        
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
                x, y = pos.get("x", 0.0), pos.get("y", 0.0)
                lap_raw = pos.get("lap", 1)
                try:
                    lap = int(lap_raw)
                except (ValueError, TypeError):
                    lap = 1
                projected_m = self._project_to_reference(x, y)
                progress_m = float((max(lap, 1) - 1) * self._ref_total_length + projected_m)
                driver_progress[code] = progress_m
                if self._ref_total_length > 0:
                    pos["fraction"] = progress_m / self._ref_total_length
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
                "lap": leader_lap,
                "leader": leader_code,
                "total_laps": self.total_laps
            }
        }

        # Send every ~2s so reconnecting clients receive geometry without special handling
        if hasattr(self, 'plot_x_ref') and int(self.frame_index) % 120 == 0:
            payload["track_geometry"] = {
                "x": self.plot_x_ref.tolist(),
                "y": self.plot_y_ref.tolist(),
                "x_inner": self.x_inner.tolist(),
                "y_inner": self.y_inner.tolist(),
                "x_outer": self.x_outer.tolist(),
                "y_outer": self.y_outer.tolist(),
                "rotation_deg": self.circuit_rotation,
            }

        self.telemetry_stream.broadcast(payload)

    def _interpolate_points(self, xs, ys, interp_points=2000):
        t_old = np.linspace(0, 1, len(xs))
        t_new = np.linspace(0, 1, interp_points)
        xs_i = np.interp(t_new, t_old, xs)
        ys_i = np.interp(t_new, t_old, ys)
        return list(zip(xs_i, ys_i))

    def _project_to_reference(self, x, y):
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

    def _precompute_gaps(self) -> None:
        """Compute true time-based gaps for every driver at every replay frame.

        Injects two new keys into each ``frame["drivers"][code]`` mapping so
        that ``LeaderboardComponent`` can display physically correct gaps
        without performing any calculation at draw time.

        Injected keys
        -------------
        ``gap_to_leader`` : float
            Seconds by which this driver trails the race leader at this
            frame.  0.0 for the leader itself.
        ``gap_to_car_ahead`` : float
            Interval gap in seconds to the car directly ahead (one rank
            better).  0.0 for the race leader.

        Algorithm
        ---------
        1.  Build a shared time vector ``t_array`` from ``frame["t"]``.
        2.  For each driver, extract (x, y, lap) arrays in a two-stage
            list-comprehension to minimise dict-lookup overhead.
        3.  Project all N positions onto the reference polyline with a
            **single batched KD-tree call per driver** — O(D log N) total
            rather than O(DN) individual scalar calls.
        4.  Compute cumulative race progress:
                progress_m = (lap − 1) × ref_total + cumdist_at_nearest
            This bypasses the ``dist`` field, which resets to 0 at the
            start of every lap due to an unfixed bug in the telemetry
            pipeline (``total_dist_so_far`` is initialised but never
            updated in ``_process_single_driver``).
        5.  Apply a start/finish-line wrap-around correction before
            ``np.maximum.accumulate``: any lap-1 sample whose projected
            cumdist exceeds half the track length is physically located
            *before* the start line (cumdist wrapped through
            ref_total → 0).  Subtracting ref_total restores its correct
            sub-zero position so ``accumulate`` does not lock the driver
            at a false one-lap-ahead progress value for the entire first
            lap.  ``np.maximum.accumulate`` is then applied to enforce
            strict monotonicity, absorbing GPS noise, pit-lane
            oscillations, and any remaining rounding artefacts.  This
            satisfies ``np.interp``'s requirement for a non-decreasing
            ``xp`` array.
        6.  Identify the race leader per frame as the driver with the
            maximum ``progress_m``.  Frames are grouped by their leader to
            enable fully vectorised ``np.interp`` calls across all frames
            that share the same leader.
        7.  Invert the leader's progress-vs-time curve with ``np.interp``:
                gap_to_leader = t_now − interp(progress[d], progress[leader], t)
            The interpolation finds the time at which the leader occupied
            driver d's current track position.  Out-of-range inputs are
            clamped to boundary values by np.interp (safe: gives 0.0 gap at
            the start when all cars share the same position history window).
        8.  Sort drivers by progress at every frame.  Derive the interval
            gap as the difference of consecutive leader-gaps:
                gap_to_car_ahead[d@rank p] =
                    gap_to_leader[d@rank p] − gap_to_leader[d@rank p−1]
            This reuses the already-computed leader-gap matrix without a
            second round of interpolation.
        9.  Clamp all values to ≥ 0.0 to absorb floating-point rounding.
        10. Inject both values into the frame dicts.

        Complexity
        ----------
        Time  : O(D × N) for extraction; O(D × log N) for KD-tree batch;
                O(D × N) for accumulate, argmax, argsort, and inject.
        Space : O(D × N) for the progress, gap_leader, gap_interval, and
                sorted_rows matrices.  All freed on method return.
        For a typical 90-min race (D=20, N≈135 000) this completes in
        well under 2 s on modern hardware.

        Notes
        -----
        *  Only ``_ref_cumdist``, ``track_tree``, and ``_ref_total_length``
           are required — no dependency on ``_project_to_reference``'s
           segment-correction step.  Position error from using only the
           nearest KD-tree node is < 1 m on a 4 000-point reference
           polyline, producing < 15 ms of gap error at race pace: below the
           0.1 s display resolution.
        *  ``self.frames`` is mutated in place.  Existing keys are
           unaffected.  Cached ``.pkl`` files are never written to.
        """
        if not self.frames or self._ref_total_length <= 0.0:
            return

        t_wall_start = time.perf_counter()
        n_frames = len(self.frames)

        # ----------------------------------------------------------------
        # 1.  Driver codes — taken from the first frame.  The telemetry
        #     pipeline guarantees all frames contain the same driver set
        #     (missing samples are forward-filled during resampling).
        #     We verify this assumption below during extraction (C3).
        # ----------------------------------------------------------------
        driver_codes = list(self.frames[0]["drivers"].keys())
        n_drivers = len(driver_codes)
        if n_drivers == 0:
            return

        # ----------------------------------------------------------------
        # 2.  Shared time vector and per-driver position / lap arrays.
        #
        #     Two-stage extraction: collect the inner driver dict once per
        #     driver to avoid the double dict-lookup in tight list-comps.
        # ----------------------------------------------------------------
        t_array = np.array([f["t"] for f in self.frames], dtype=np.float64)

        x_arrs   = {}   # code -> float64 [N]
        y_arrs   = {}
        lap_arrs = {}

        # C3: use .get() so a driver absent from any frame does not raise
        # a KeyError.  If a driver is missing from at least one frame the
        # entire driver is excluded from gap computation rather than
        # silently producing a partial (and potentially wrong) result.
        _verified_codes = []
        for code in driver_codes:
            driver_dicts = [f["drivers"].get(code) for f in self.frames]
            if any(d is None for d in driver_dicts):
                print(
                    f"⚠ Gap engine: driver '{code}' absent from "
                    f"{sum(1 for d in driver_dicts if d is None)} frame(s) "
                    f"— excluded from gap computation"
                )
                continue
            x_arrs[code]   = np.array([d["x"]          for d in driver_dicts], dtype=np.float64)
            y_arrs[code]   = np.array([d["y"]          for d in driver_dicts], dtype=np.float64)
            lap_raw        = np.array([d.get("lap", 1) for d in driver_dicts], dtype=np.float64)
            lap_arrs[code] = np.maximum(lap_raw, 1.0)
            _verified_codes.append(code)
        driver_codes = _verified_codes
        n_drivers    = len(driver_codes)
        if n_drivers == 0:
            return

        # ----------------------------------------------------------------
        # 3, 4 & 5.  Batch KD-tree projection → S/F correction → monotone
        #            progress_m.
        # ----------------------------------------------------------------
        progress_m = {}   # code -> float64 [N]
        # S/F wrap-around detection threshold.  Any lap-1 car whose projected
        # cumdist exceeds this fraction of the track length is treated as
        # physically behind the start line (cumdist wrapping through
        # ref_total → 0).  0.75 covers the entire final quarter — enough to
        # encompass any F1 start grid (~300 m) while leaving the back-straight
        # region (≈ 50 % of the track) unaffected.  Using 0.5 was too coarse:
        # KD-tree discretisation can place the 180 ° node slightly above
        # 0.5 × ref_total, which would spuriously shift any lap-1 car on the
        # back straight.
        half_track = 0.75 * self._ref_total_length

        for code in driver_codes:
            xy = np.column_stack([x_arrs[code], y_arrs[code]])   # [N, 2]
            _, nn_idxs = self.track_tree.query(xy)                # [N] int

            # Cumulative track distance at the nearest reference node.
            projected = self._ref_cumdist[nn_idxs]                # [N] metres

            # Total race progress from the start of the formation lap.
            pm = (lap_arrs[code] - 1.0) * self._ref_total_length + projected

            # C1 — Start/finish wrap-around correction.
            #
            # During lap 1 the KD-tree projects cars physically located
            # just *before* the start line to cumdist ≈ ref_total (the
            # track end).  With lap=1 this produces pm ≈ ref_total, making
            # the car appear to be a full lap ahead.  np.maximum.accumulate
            # would then lock that inflated value for the entire first lap
            # (~80 s), producing false leaders and wrong gap_to_leader
            # values for every other driver during that period.
            #
            # Fix: any lap-1 sample whose projected cumdist exceeds half
            # the track length is behind the start line (its cumdist has
            # wrapped through ref_total → 0).  Subtract ref_total to
            # restore it to a small negative progress value, which
            # accumulate then propagates correctly until the car genuinely
            # crosses the line and pm rises through 0.
            sf_wrap = (lap_arrs[code] == 1.0) & (projected > half_track)
            pm[sf_wrap] -= self._ref_total_length

            # Enforce monotonicity: a car cannot move backwards.
            # np.maximum.accumulate produces a non-decreasing sequence
            # which satisfies np.interp's xp requirement exactly.
            progress_m[code] = np.maximum.accumulate(pm)

        # C4 — Release coordinate arrays; they are not needed beyond this
        # point.  Frees ~65 MB during long-race startup.
        del x_arrs, y_arrs, lap_arrs

        # ----------------------------------------------------------------
        # 6.  Leader identification per frame.
        # ----------------------------------------------------------------
        # pm_matrix[d, i] = progress of driver d at frame i  — [D, N]
        pm_matrix  = np.stack([progress_m[c] for c in driver_codes], axis=0)
        leader_row = np.argmax(pm_matrix, axis=0)   # [N]  int row-index

        # ----------------------------------------------------------------
        # 7.  gap_to_leader via np.interp time-inversion.
        #
        #     For driver d at frame i where leader L leads:
        #         gap = t[i] − interp(progress[d][i], progress[L], t)
        #
        #     We group frames by their leader so each driver's full
        #     progress array can be used as interpolation knots in a
        #     single vectorised call per (leader, driver) pair.
        # ----------------------------------------------------------------
        gap_leader  = np.zeros((n_drivers, n_frames), dtype=np.float64)
        frame_range = np.arange(n_frames)

        for ldr_row_id in np.unique(leader_row):
            ldr_code = driver_codes[int(ldr_row_id)]
            ldr_pm   = progress_m[ldr_code]                 # [N] monotone

            mask  = leader_row == ldr_row_id                # [N] bool
            fidxs = frame_range[mask]                       # frame indices
            t_sub = t_array[fidxs]

            for d_idx, code in enumerate(driver_codes):
                if code == ldr_code:
                    # The leader's gap to itself is 0.0 by definition.
                    continue

                # Driver d's progress at frames where ldr_code leads.
                d_pm_sub = progress_m[code][fidxs]

                # Time at which the leader occupied driver d's position.
                # np.interp clamps out-of-range values to boundary values:
                # drivers ahead of the leader's earliest recorded position
                # map to t[0], giving a ~0 gap — correct at race start.
                t_ldr_at_d = np.interp(d_pm_sub, ldr_pm, t_array)

                gap = t_sub - t_ldr_at_d

                # Clamp: small negative values can arise in the opening
                # frames when all cars share the same starting window and
                # GPS quantisation makes one appear briefly ahead.
                np.clip(gap, 0.0, None, out=gap)

                gap_leader[d_idx, fidxs] = gap

        # ----------------------------------------------------------------
        # 8.  Interval gap derived from consecutive leader-gap differences.
        #
        #     Sort drivers by progress at every frame (stable sort preserves
        #     previous-frame order on ties, matching leaderboard ordering).
        #
        #     For the driver at rank p at frame i:
        #         interval = gap_leader[rank p] − gap_leader[rank p−1]
        #
        #     Advanced indexing over N frames simultaneously avoids any
        #     Python loop over the frame axis.
        # ----------------------------------------------------------------
        # sorted_rows[rank, frame] = row index in driver_codes
        sorted_rows  = np.argsort(-pm_matrix, axis=0, kind="stable")  # [D, N]
        gap_interval = np.zeros((n_drivers, n_frames), dtype=np.float64)

        for p in range(1, n_drivers):
            d_rows     = sorted_rows[p,     :]   # [N] row-idxs at rank p
            ahead_rows = sorted_rows[p - 1, :]   # [N] row-idxs at rank p-1

            # Pick the leader-gap for the correct driver at each frame.
            gap_d     = gap_leader[d_rows,     frame_range]   # [N]
            gap_ahead = gap_leader[ahead_rows, frame_range]   # [N]

            interval = gap_d - gap_ahead
            np.clip(interval, 0.0, None, out=interval)

            # Write results back; each (d_idx, frame) cell is written once.
            gap_interval[d_rows, frame_range] = interval

        # ----------------------------------------------------------------
        # 9 & 10.  Inject into frame dicts.
        #
        #     A reverse lookup table avoids repeated list.index() calls.
        # ----------------------------------------------------------------
        code_to_idx = {code: i for i, code in enumerate(driver_codes)}

        for i, frame in enumerate(self.frames):
            for code, pos in frame["drivers"].items():
                d = code_to_idx.get(code)
                if d is None:
                    continue
                pos["gap_to_leader"]    = float(gap_leader  [d, i])
                pos["gap_to_car_ahead"] = float(gap_interval[d, i])

        elapsed = time.perf_counter() - t_wall_start
        print(
            f"✓ Gap engine: {n_drivers} drivers × {n_frames} frames "
            f"→ gaps precomputed in {elapsed:.3f}s"
        )

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
        if degrees is None:
            return "N/A"
        deg_norm = degrees % 360
        dirs = [
            "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
        ]
        idx = int((deg_norm / 22.5) + 0.5) % len(dirs)
        return dirs[idx]

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
            
        if len(self.screen_inner_points) > 1:
            arcade.draw_line_strip(self.screen_inner_points, track_color, 4)
        if len(self.screen_outer_points) > 1:
            arcade.draw_line_strip(self.screen_outer_points, track_color, 4)
        
        # 2.5 Draw DRS Zones (green segments on outer track edge)
        if hasattr(self, 'drs_zones') and self.drs_zones and self.toggle_drs_zones:
            drs_color = (0, 255, 0)  # Bright green for DRS zones
            
            for _, zone in enumerate(self.drs_zones):
                start_idx = zone["start"]["index"]
                end_idx = zone["end"]["index"]
                
                # Extract the outer track points for this DRS zone segment
                drs_outer_points = []
                for i in range(start_idx, min(end_idx + 1, len(self.x_outer))):
                    x = self.x_outer.iloc[i]
                    y = self.y_outer.iloc[i]
                    sx, sy = self.world_to_screen(x, y)
                    drs_outer_points.append((sx, sy))
                
                # Draw the DRS zone segment
                if len(drs_outer_points) > 1:
                    arcade.draw_line_strip(drs_outer_points, drs_color, 6)

        draw_finish_line(self)
        # 3. Draw Cars
        frame = self.frames[idx]
        
        # Get selected drivers list safely
        selected_drivers = getattr(self, "selected_drivers", [])
        if not selected_drivers and getattr(self, "selected_driver", None):
            selected_drivers = [self.selected_driver]

        for i, (code, pos) in enumerate(frame["drivers"].items()):
            sx, sy = self.world_to_screen(pos["x"], pos["y"])
            color = self.driver_colors.get(code, arcade.color.WHITE)
            
            is_selected = code in selected_drivers
            
            if self.show_driver_labels or is_selected:
                # Find closest point index on reference track (Optimized KD-Tree)
                _, idx = self.track_tree.query([pos["x"], pos["y"]])
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

            arcade.draw_circle_filled(sx, sy, 6, color)
        
        # 3b. Draw Safety Car (if active)
        sc_data = frame.get("safety_car")
        if sc_data is not None:
            sc_x = sc_data["x"]
            sc_y = sc_data["y"]
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

            # Project (x,y) to reference and combine with lap count
            projected_m = self._project_to_reference(pos.get("x", 0.0), pos.get("y", 0.0))

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
            self.lap_text.text = lap_str
            self.time_text.text = f"Race Time: {time_str} (x{self.playback_speed})"
            # default no status text
            self.status_text.text = ""
            # update status color and text if required
            if current_track_status == "2":
                self.status_text.text = "YELLOW FLAG"
                self.status_text.color = arcade.color.YELLOW
            elif current_track_status == "5":
                self.status_text.text = "RED FLAG"
                self.status_text.color = arcade.color.RED
            elif current_track_status == "6":
                self.status_text.text = "VIRTUAL SAFETY CAR"
                self.status_text.color = arcade.color.ORANGE
            elif current_track_status == "4":
                self.status_text.text = "SAFETY CAR"
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

        # Draw leaderboard via component
        driver_list = []
        for code, pos in frame["drivers"].items():
            color = self.driver_colors.get(code, arcade.color.WHITE)
            progress_m = driver_progress.get(code, float(pos.get("dist", 0.0)))
            driver_list.append((code, color, pos, progress_m))
        driver_list.sort(key=lambda x: x[3], reverse=True)

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
        elif self.is_forwarding:
            self.frame_index = min(self.n_frames - 1, self.frame_index + delta_time * FPS * seek_speed)
            self.race_controls_comp.flash_button('forward')

        if self.paused:
            return

        self.frame_index += delta_time * FPS * self.playback_speed
        
        if self.frame_index >= self.n_frames:
            self.frame_index = float(self.n_frames - 1)
            
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
            self.progress_bar_comp.toggle_visibility() # toggle progress bar visibility
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
        
    def on_mouse_motion(self, x: float, y: float, dx: float, dy: float):
        """Handle mouse motion for hover effects on progress bar and controls."""
        self.progress_bar_comp.on_mouse_motion(self, x, y, dx, dy)
        self.race_controls_comp.on_mouse_motion(self, x, y, dx, dy)
        
    def close(self):
        """Clean up resources when window closes."""
        if hasattr(self, 'telemetry_stream') and self.telemetry_stream:
            print("Stopping telemetry stream server...")
            self.telemetry_stream.stop()
        super().close()