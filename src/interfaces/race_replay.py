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

        # Send pre-computed data continuously. It's just a Python dictionary reference 
        # (O(1) memory overhead in local publish/subscribe) and ensures windows 
        # opened after the race has finished still receive the data.
        payload["lap_times"] = self._precomputed_lap_times
        payload["status_laps"] = self._precomputed_status_laps

        self.telemetry_stream.broadcast(payload)

    @staticmethod
    def _compute_lap_times(frames, session=None):
        """
        Scan the full frame array once to build deterministic lap times
        for every driver.  Returns {code: [{lap, time_s, end_time_s, tyre}, ...]}.
        """
        fallback_result = F1RaceReplayWindow._compute_fallback_lap_times_raw(frames)
        classified_fallback = F1RaceReplayWindow._classify_lap_entries(
            fallback_result,
            official_data=False,
        )

        if session is not None and hasattr(session, 'laps'):
            try:
                import pandas as pd
                import fastf1._api as ffapi
                import fastf1.utils as ffutils
                from src.lib.tyres import get_tyre_compound_int
                result = {}
                for _, row in session.laps.iterrows():
                    code = row.get("Driver")
                    lap_num = row.get("LapNumber")
                    lap_time_td = row.get("LapTime")
                    tyre_str = row.get("Compound")
                    tyre_life = row.get("TyreLife")
                    
                    if pd.isna(lap_num):
                        continue
                        
                    lap = int(lap_num)
                    time_s = lap_time_td.total_seconds() if pd.notna(lap_time_td) else -1.0
                    lap_end_td = row.get("Time")
                    end_time_s = lap_end_td.total_seconds() if pd.notna(lap_end_td) else None
                    line_end_td = row.get("Sector3SessionTime")
                    line_end_s = line_end_td.total_seconds() if pd.notna(line_end_td) else end_time_s
                    
                    tyre_int = -1
                    if pd.notna(tyre_str):
                        tyre_int = get_tyre_compound_int(tyre_str)
                        
                    t_life = 0
                    if pd.notna(tyre_life):
                        t_life = int(tyre_life)
                        
                    is_pit = False
                    if "PitInTime" in session.laps.columns and pd.notna(row.get("PitInTime")):
                        is_pit = True
                        
                    result.setdefault(code, []).append({
                        "lap": int(lap_num),
                        "time_s": float(time_s),
                        "end_time_s": float(end_time_s) if end_time_s is not None else None,
                        "line_time_s": float(line_end_s) if line_end_s is not None else None,
                        "tyre": tyre_int,
                        "tyre_life": t_life,
                        "is_pit": is_pit,
                    })
                if result:
                    fallback_by_code = {
                        code: {entry["lap"]: entry for entry in entries}
                        for code, entries in classified_fallback.items()
                    }
                    for code, entries in result.items():
                        fallback_entries = fallback_by_code.get(code, {})
                        for entry in entries:
                            fb_entry = fallback_entries.get(entry["lap"])
                            if fb_entry is None:
                                continue
                            if entry.get("time_s", -1.0) <= 0 and fb_entry.get("time_s", -1.0) > 0:
                                entry["time_s"] = fb_entry["time_s"]
                                entry["time_source"] = "frame_backfill"
                                entry["source"] = "derived"
                                if entry.get("end_time_s") is None and fb_entry.get("end_time_s") is not None:
                                    entry["end_time_s"] = fb_entry["end_time_s"]
                                if entry.get("line_time_s") is None and fb_entry.get("end_time_s") is not None:
                                    entry["line_time_s"] = fb_entry["end_time_s"]
                                if fb_entry.get("start_time_s") is not None:
                                    entry["start_time_s"] = fb_entry["start_time_s"]
                            if fb_entry.get("is_pit") and not entry.get("is_pit"):
                                entry["is_pit"] = True
                                entry["pit_confidence"] = fb_entry.get("pit_confidence", "medium")
                            if fb_entry.get("is_out_lap"):
                                entry["is_out_lap"] = True
                            if fb_entry.get("is_outlier"):
                                entry["is_outlier"] = True
                            if fb_entry.get("pace_baseline_s") is not None and entry.get("pace_baseline_s") is None:
                                entry["pace_baseline_s"] = fb_entry["pace_baseline_s"]
                    try:
                        _, stream_data, _ = ffapi._extended_timing_data(session.api_path)
                        number_to_code = {}
                        code_to_number = {}
                        if (
                            hasattr(session, "results")
                            and session.results is not None
                            and not session.results.empty
                            and "DriverNumber" in session.results.columns
                            and "Abbreviation" in session.results.columns
                        ):
                            for _, res_row in session.results.iterrows():
                                drv_num = res_row.get("DriverNumber")
                                code = res_row.get("Abbreviation")
                                if pd.notna(drv_num) and pd.notna(code):
                                    drv_num = str(drv_num)
                                    code = str(code)
                                    number_to_code[drv_num] = code
                                    code_to_number[code] = drv_num
                        if (
                            "DriverNumber" in session.laps.columns
                            and "Driver" in session.laps.columns
                        ):
                            for _, lap_row in (
                                session.laps[["DriverNumber", "Driver"]]
                                .dropna()
                                .drop_duplicates()
                                .iterrows()
                            ):
                                drv_num = str(lap_row["DriverNumber"])
                                code = str(lap_row["Driver"])
                                number_to_code.setdefault(drv_num, code)
                                code_to_number.setdefault(code, drv_num)

                        official_pos_lookup = {}
                        if (
                            "Driver" in session.laps.columns
                            and "LapNumber" in session.laps.columns
                            and "Position" in session.laps.columns
                        ):
                            for _, sess_lap_row in session.laps[["Driver", "LapNumber", "Position"]].dropna(subset=["Driver", "LapNumber"]).iterrows():
                                try:
                                    pos_val = sess_lap_row.get("Position")
                                    pos_int = int(pos_val) if pd.notna(pos_val) else None
                                    official_pos_lookup[(str(sess_lap_row["Driver"]), int(sess_lap_row["LapNumber"]))] = pos_int
                                except Exception:
                                    continue

                        def _parse_gap_to_leader(raw_value, row_position):
                            if pd.isna(raw_value):
                                return 0.0 if str(row_position or "") == "1" else None
                            gap_text = str(raw_value).strip()
                            if not gap_text:
                                return 0.0 if str(row_position or "") == "1" else None
                            upper_text = gap_text.upper()
                            if upper_text.startswith("LAP") or upper_text.endswith(" L") or upper_text.endswith("L"):
                                return 0.0 if str(row_position or "") == "1" else None
                            gap_td = ffutils.to_timedelta(gap_text)
                            if gap_td is not None:
                                return float(gap_td.total_seconds())
                            return None

                        def _parse_interval_to_ahead(raw_value):
                            if pd.isna(raw_value):
                                return None
                            gap_text = str(raw_value).strip()
                            if not gap_text:
                                return None
                            upper_text = gap_text.upper()
                            if upper_text.startswith("LAP") or upper_text.endswith(" L") or upper_text.endswith("L"):
                                return None
                            gap_td = ffutils.to_timedelta(gap_text)
                            if gap_td is not None:
                                return float(gap_td.total_seconds())
                            return None

                        lap_match_data = {}
                        for code, entries in result.items():
                            drv_num = code_to_number.get(code)
                            if not drv_num:
                                continue
                            drv_stream_rows = stream_data[stream_data["Driver"].astype(str) == drv_num]
                            if drv_stream_rows.empty:
                                continue
                            for lap_entry in entries:
                                lap_no = lap_entry.get("lap")
                                gap_s = None
                                target_time_s = lap_entry.get("line_time_s")
                                if target_time_s is None:
                                    target_time_s = lap_entry.get("end_time_s")
                                if target_time_s is None:
                                    continue
                                first_time = pd.to_timedelta(float(target_time_s), unit="s")
                                official_pos = official_pos_lookup.get((code, lap_no))
                                time_delta = (drv_stream_rows["Time"] - first_time).abs()
                                local_window = drv_stream_rows[time_delta <= pd.to_timedelta(20, unit="s")]
                                matched_stream_row = None
                                if official_pos is not None and not local_window.empty:
                                    pos_rows = local_window[local_window["Position"] == official_pos]
                                    if not pos_rows.empty:
                                        ref_idx = (pos_rows["Time"] - first_time).abs().idxmin()
                                        matched_stream_row = pos_rows.loc[ref_idx]
                                if matched_stream_row is None and not local_window.empty:
                                    ref_idx = (local_window["Time"] - first_time).abs().idxmin()
                                    matched_stream_row = local_window.loc[ref_idx]
                                if matched_stream_row is None:
                                    candidate_rows = drv_stream_rows[drv_stream_rows["Time"] <= first_time]
                                    if official_pos is not None and not candidate_rows.empty:
                                        pos_rows = candidate_rows[candidate_rows["Position"] == official_pos]
                                        if not pos_rows.empty:
                                            ref_idx = (pos_rows["Time"] - first_time).abs().idxmin()
                                            matched_stream_row = pos_rows.loc[ref_idx]
                                    if matched_stream_row is None and not candidate_rows.empty:
                                        matched_stream_row = candidate_rows.sort_values("Time").iloc[-1]
                                if matched_stream_row is None:
                                    ref_idx = (drv_stream_rows["Time"] - first_time).abs().idxmin()
                                    matched_stream_row = drv_stream_rows.loc[ref_idx]
                                matched_position = matched_stream_row.get("Position")

                                interval_chain_reliable = False
                                interval_quality_rows = local_window
                                target_position = official_pos
                                if target_position is None and pd.notna(matched_position):
                                    try:
                                        target_position = int(matched_position)
                                    except Exception:
                                        target_position = None
                                if target_position is not None and not interval_quality_rows.empty:
                                    interval_quality_rows = interval_quality_rows[
                                        interval_quality_rows["Position"] == target_position
                                    ]
                                if not interval_quality_rows.empty:
                                    scored_intervals = []
                                    for _, cand_row in interval_quality_rows.iterrows():
                                        cand_interval_s = _parse_interval_to_ahead(
                                            cand_row.get("IntervalToPositionAhead")
                                        )
                                        if cand_interval_s is None:
                                            continue
                                        cand_dt_s = abs(
                                            float((cand_row["Time"] - first_time).total_seconds())
                                        )
                                        scored_intervals.append((cand_dt_s, float(cand_interval_s)))
                                    if scored_intervals:
                                        scored_intervals.sort(key=lambda item: item[0])
                                        close_intervals = [
                                            val for dt_s, val in scored_intervals[:4] if dt_s <= 6.0
                                        ]
                                        if len(close_intervals) >= 2:
                                            interval_chain_reliable = (
                                                max(close_intervals) - min(close_intervals) <= 1.0
                                            )
                                gap_s = _parse_gap_to_leader(
                                    matched_stream_row.get("GapToLeader"), matched_position
                                )
                                interval_s = _parse_interval_to_ahead(
                                    matched_stream_row.get("IntervalToPositionAhead")
                                )
                                if gap_s is None and interval_s is None:
                                    continue

                                if matched_stream_row.get("Time") is not None and pd.notna(matched_stream_row.get("Time")):
                                    lap_entry["official_stream_time_s"] = float(
                                        matched_stream_row["Time"].total_seconds()
                                    )
                                if pd.notna(matched_position):
                                    try:
                                        lap_entry["official_stream_position"] = int(matched_position)
                                    except Exception:
                                        pass
                                if interval_s is not None:
                                    lap_entry["official_interval_to_ahead_s"] = float(interval_s)

                                lap_match_data.setdefault(int(lap_no), []).append(
                                    {
                                        "code": code,
                                        "entry": lap_entry,
                                        "official_pos": official_pos,
                                        "matched_pos": (
                                            int(matched_position)
                                            if pd.notna(matched_position)
                                            else None
                                        ),
                                        "gap_s": gap_s,
                                        "interval_s": interval_s,
                                        "interval_chain_reliable": interval_chain_reliable,
                                    }
                                )

                        # Reconstruct a coherent per-lap official gap ladder. Direct GapToLeader
                        # remains authoritative when present. IntervalToPositionAhead is only used
                        # to fill gaps where GapToLeader is absent/non-numeric.
                        for _, lap_items in lap_match_data.items():
                            ordered_items = sorted(
                                lap_items,
                                key=lambda item: (
                                    item["official_pos"] is None,
                                    item["official_pos"]
                                    if item["official_pos"] is not None
                                    else (
                                        item["matched_pos"]
                                        if item["matched_pos"] is not None
                                        else 999
                                    ),
                                    item["code"],
                                ),
                            )
                            assigned_by_pos = {}
                            for item in ordered_items:
                                pos = item["official_pos"]
                                if pos is None:
                                    pos = item["matched_pos"]
                                if pos is None:
                                    continue

                                direct_gap_s = item["gap_s"]
                                if pos == 1:
                                    assigned_gap_s = 0.0
                                    source = "direct"
                                else:
                                    prev_gap_s = assigned_by_pos.get(pos - 1)
                                    predicted_gap_s = None
                                    if (
                                        prev_gap_s is not None
                                        and item["interval_s"] is not None
                                        and item.get("interval_chain_reliable")
                                    ):
                                        predicted_gap_s = float(prev_gap_s) + float(item["interval_s"])

                                    assigned_gap_s = None
                                    source = None
                                    if direct_gap_s is not None:
                                        assigned_gap_s = float(direct_gap_s)
                                        source = "direct"
                                    elif predicted_gap_s is not None:
                                        assigned_gap_s = float(predicted_gap_s)
                                        source = "interval_chain"

                                if assigned_gap_s is None:
                                    continue
                                assigned_by_pos[pos] = assigned_gap_s
                                item["entry"]["official_gap_to_leader_s"] = float(assigned_gap_s)
                                item["entry"]["official_gap_source"] = source
                    except Exception:
                        pass
                    try:
                        import pandas as pd
                        results_df = session.results
                        if results_df is not None and not results_df.empty:
                            winner_rows = results_df[results_df["ClassifiedPosition"] == "1"]
                            if not winner_rows.empty:
                                winner_row = winner_rows.iloc[0]
                                winner_code = winner_row.get("Abbreviation")
                                winner_laps = int(winner_row.get("Laps", 0) or 0)
                                if winner_code in result and winner_laps > 0:
                                    winner_entries = {e["lap"]: e for e in result[winner_code]}
                                    winner_entry = winner_entries.get(winner_laps)
                                    if winner_entry is not None:
                                        winner_entry["official_finish_gap_s"] = 0.0

                                for _, res_row in results_df.iterrows():
                                    code = res_row.get("Abbreviation")
                                    if code not in result:
                                        continue
                                    if str(res_row.get("Status", "")) != "Finished":
                                        continue
                                    laps_done = int(res_row.get("Laps", 0) or 0)
                                    if winner_laps <= 0 or laps_done != winner_laps:
                                        continue
                                    gap_td = res_row.get("Time")
                                    if code == winner_code:
                                        gap_s = 0.0
                                    elif pd.isna(gap_td):
                                        continue
                                    else:
                                        gap_s = float(gap_td.total_seconds())
                                    lap_entry = next((e for e in result[code] if e["lap"] == winner_laps), None)
                                    if lap_entry is not None:
                                        lap_entry["official_finish_gap_s"] = gap_s

                            for _, res_row in results_df.iterrows():
                                code = str(res_row.get("Abbreviation", "")).strip()
                                if not code:
                                    continue
                                laps_completed = res_row.get("Laps")
                                if pd.isna(laps_completed):
                                    continue
                                try:
                                    terminal_lap = int(laps_completed)
                                except (TypeError, ValueError):
                                    continue

                                status_text = str(res_row.get("Status", "")).strip()
                                classified_pos = str(res_row.get("ClassifiedPosition", "")).strip()
                                is_terminal_retirement = (
                                    classified_pos == "R"
                                    or (
                                        status_text
                                        and status_text not in {"Finished", "Lapped"}
                                        and not status_text.startswith("+")
                                    )
                                )
                                if not is_terminal_retirement:
                                    continue

                                code_entries = result.setdefault(code, [])
                                terminal_entry = next(
                                    (e for e in code_entries if e.get("lap") == terminal_lap),
                                    None,
                                )
                                if terminal_entry is None:
                                    terminal_entry = {
                                        "lap": terminal_lap,
                                        "time_s": -1.0,
                                        "end_time_s": None,
                                        "line_time_s": None,
                                        "tyre": -1,
                                        "tyre_life": 0,
                                        "is_pit": False,
                                        "source": "official",
                                    }
                                    code_entries.append(terminal_entry)

                                terminal_entry["is_terminal_lap"] = True
                                terminal_entry["result_status"] = status_text or "Retired"
                    except Exception:
                        pass
                    return F1RaceReplayWindow._classify_lap_entries(result, official_data=True)
            except Exception as e:
                print(f"Error parsing official lap times: {e}")

        return classified_fallback

    @staticmethod
    def _compute_fallback_lap_times_raw(frames, min_lap_time_s=30.0, max_lap_time_s=7200.0):
        lap_start_t = {}    # code -> session time when current lap began
        current_lap = {}    # code -> last seen lap number
        result = {}         # code -> list of lap time entries

        for frame in frames:
            t = frame.get("t", 0)
            drivers = frame.get("drivers", {})
            for code, drv in drivers.items():
                lap = drv.get("lap")
                if lap is None:
                    continue

                prev_lap = current_lap.get(code)
                if prev_lap is None:
                    current_lap[code] = lap
                    lap_start_t[code] = t
                    result.setdefault(code, [])
                    continue

                if lap > prev_lap:
                    lap_time = t - lap_start_t.get(code, t)
                    tyre = int(round(drv.get("tyre", 0)))
                    tyre_life = int(round(drv.get("tyre_life", 0)))

                    if min_lap_time_s < lap_time < max_lap_time_s and prev_lap >= 2:
                        result.setdefault(code, []).append({
                            "lap": prev_lap,
                            "time_s": float(lap_time),
                            "end_time_s": float(t),
                            "tyre": tyre,
                            "tyre_life": tyre_life,
                            "start_time_s": float(lap_start_t.get(code, t)),
                        })

                    current_lap[code] = lap
                    lap_start_t[code] = t

        return result

    @staticmethod
    def _classify_lap_entries(result, official_data=False):
        """
        Enrich lap entries with derived metadata so insight windows can
        distinguish pit laps, out laps, and generic slow-lap outliers even
        when official pit timing fields are unavailable.
        """
        for entries in result.values():
            entries.sort(key=lambda e: e["lap"])
            clean_history = []
            gap_clock_s = 0.0

            for i, entry in enumerate(entries):
                next_entry = entries[i + 1] if i + 1 < len(entries) else None
                entry.setdefault("source", "official" if official_data else "derived")
                entry.setdefault("is_pit", False)
                entry.setdefault("is_out_lap", False)
                entry.setdefault("is_outlier", False)
                entry.setdefault(
                    "pit_confidence",
                    "official" if entry.get("is_pit") and entry.get("source") == "official" else "none",
                )

                baseline_pool = clean_history[-5:]
                baseline = None
                if baseline_pool:
                    baseline = sorted(baseline_pool)[len(baseline_pool) // 2]
                    entry["pace_baseline_s"] = round(float(baseline), 3)

                time_s = entry.get("time_s", -1.0)
                if time_s > 0:
                    gap_clock_s += float(time_s)
                    entry["gap_clock_s"] = gap_clock_s
                else:
                    entry["gap_clock_s"] = None
                if (
                    entry.get("source") != "official"
                    and not entry.get("is_pit")
                    and baseline is not None
                    and time_s > 0
                    and entry["lap"] > 1
                ):
                    tyre = entry.get("tyre", -1)
                    tyre_life = entry.get("tyre_life", -1)
                    next_tyre = next_entry.get("tyre", -1) if next_entry else -1
                    next_tyre_life = next_entry.get("tyre_life", -1) if next_entry else -1

                    compound_change = (
                        next_entry is not None
                        and tyre != -1
                        and next_tyre != -1
                        and next_tyre != tyre
                    )
                    age_reset = (
                        next_entry is not None
                        and tyre_life >= 0
                        and next_tyre_life >= 0
                        and next_tyre_life <= 2
                        and next_tyre_life + 1 < tyre_life
                    )
                    severe_delta = (time_s - baseline) >= max(12.0, baseline * 0.12)
                    moderate_delta = (time_s - baseline) >= max(7.0, baseline * 0.08)

                    if severe_delta and (compound_change or age_reset):
                        entry["is_pit"] = True
                        entry["pit_confidence"] = "high"
                    elif moderate_delta and age_reset:
                        entry["is_pit"] = True
                        entry["pit_confidence"] = "medium"
                    elif severe_delta:
                        entry["is_outlier"] = True

                if entry.get("is_pit") and next_entry and next_entry["lap"] == entry["lap"] + 1:
                    next_entry["is_out_lap"] = True

                if (
                    time_s > 0
                    and not entry.get("is_pit")
                    and not entry.get("is_out_lap")
                    and not entry.get("is_outlier")
                ):
                    clean_history.append(time_s)

        return result

    @staticmethod
    def _compute_status_laps(frames, track_statuses):
        """
        Map track status periods to leader lap numbers.
        Returns a list of {"status": str, "start_lap": int, "end_lap": int}.

        Status codes: "4" = Safety Car, "6" = VSC, "7" = VSC Ending,
                      "5" = Red Flag.
        """
        if not track_statuses or not frames:
            return []

        # Build a time → leader lap lookup from frames
        # (sample every 25th frame for speed; 1 sample per second is plenty)
        time_to_lap = []
        for i in range(0, len(frames), 25):
            f = frames[i]
            t = f.get("t", 0)
            lap = f.get("lap", 1)
            time_to_lap.append((t, int(lap)))

        def _lap_at_time(target_t):
            """Binary-ish lookup for leader lap at a given session time."""
            best_lap = 1
            for t, lap in time_to_lap:
                if t <= target_t:
                    best_lap = lap
                else:
                    break
            return best_lap

        result = []
        for status in track_statuses:
            code = str(status.get("status", ""))
            if code not in ("4", "5", "6", "7"):
                continue
            start_t = status.get("start_time", 0)
            end_t = status.get("end_time")
            start_lap = _lap_at_time(start_t)
            end_lap = _lap_at_time(end_t) if end_t else start_lap
            # Merge consecutive entries with same status
            if result and result[-1]["status"] == code and result[-1]["end_lap"] >= start_lap - 1:
                result[-1]["end_lap"] = max(result[-1]["end_lap"], end_lap)
            else:
                result.append({
                    "status": code,
                    "start_lap": start_lap,
                    "end_lap": end_lap,
                })
        return result

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
