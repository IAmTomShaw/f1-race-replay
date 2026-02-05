"""
Telemetry Processor for F1 Race Data

Handles the processing of raw FastF1 telemetry data into a format
suitable for the web application replay system.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

# Constants
FPS = 25  # Frames per second for replay
DT = 1 / FPS  # Time delta between frames


class TelemetryProcessor:
    """Processes raw telemetry data into replay-ready format"""
    
    def __init__(self, session):
        """
        Initialize processor with a FastF1 session
        
        Args:
            session: FastF1 session object
        """
        self.session = session
        self.drivers = session.drivers
        self.driver_codes = {
            num: session.get_driver(num)["Abbreviation"]
            for num in self.drivers
        }
    
    def process_race_telemetry(self, session_type: str = 'R') -> Dict[str, Any]:
        """
        Process race telemetry into frame-by-frame data
        
        Args:
            session_type: Session type ('R' for Race, 'S' for Sprint)
        
        Returns:
            Dictionary containing frames, track statuses, and metadata
        """
        logger.info(f"Processing {session_type} telemetry...")
        
        # Collect driver telemetry data
        driver_data = self._collect_driver_data()
        
        if not driver_data:
            raise ValueError("No valid telemetry data found for any driver")
        
        # Get time bounds
        global_t_min, global_t_max = self._get_time_bounds(driver_data)
        max_lap_number = max(d["max_lap"] for d in driver_data.values())
        
        # Create timeline
        timeline = np.arange(global_t_min, global_t_max, DT) - global_t_min
        
        # Resample all driver data onto common timeline
        resampled_data = self._resample_driver_data(driver_data, timeline, global_t_min)
        
        # Process track status
        track_statuses = self._process_track_status(global_t_min)
        
        # Process weather data
        weather_resampled = self._process_weather_data(timeline, global_t_min)
        
        # Build frames
        frames = self._build_frames(
            timeline=timeline,
            resampled_data=resampled_data,
            weather_resampled=weather_resampled
        )
        
        logger.info(f"Processed {len(frames)} frames")
        
        return {
            "frames": frames,
            "track_statuses": track_statuses,
            "total_laps": int(max_lap_number),
        }
    
    def _collect_driver_data(self) -> Dict[str, Dict[str, Any]]:
        """
        Collect telemetry data for all drivers
        
        Returns:
            Dictionary mapping driver codes to their telemetry data
        """
        driver_data = {}
        
        for driver_no in self.drivers:
            driver_code = self.driver_codes[driver_no]
            logger.debug(f"Processing driver: {driver_code}")
            
            try:
                data = self._process_single_driver(driver_no, driver_code)
                if data:
                    driver_data[driver_code] = data
            except Exception as e:
                logger.warning(f"Failed to process driver {driver_code}: {e}")
                continue
        
        return driver_data
    
    def _process_single_driver(self, driver_no: int, driver_code: str) -> Optional[Dict[str, Any]]:
        """
        Process telemetry for a single driver
        
        Args:
            driver_no: Driver number
            driver_code: Driver abbreviation code
        
        Returns:
            Dictionary with driver telemetry arrays or None if no data
        """
        laps_driver = self.session.laps.pick_drivers(driver_no)
        
        if laps_driver.empty:
            return None
        
        driver_max_lap = laps_driver.LapNumber.max() if not laps_driver.empty else 0
        
        # Initialize arrays
        t_all = []
        x_all = []
        y_all = []
        race_dist_all = []
        rel_dist_all = []
        lap_numbers = []
        tyre_compounds = []
        speed_all = []
        gear_all = []
        drs_all = []
        throttle_all = []
        brake_all = []
        
        total_dist_so_far = 0.0
        
        # Iterate through laps
        for _, lap in laps_driver.iterlaps():
            lap_tel = lap.get_telemetry()
            lap_number = lap.LapNumber
            
            # Get tyre compound
            from core.tyres import get_tyre_compound_int
            tyre_compound_as_int = get_tyre_compound_int(str(lap.Compound))
            
            if lap_tel.empty:
                continue
            
            # Extract telemetry arrays
            t_lap = lap_tel["SessionTime"].dt.total_seconds().to_numpy()
            x_lap = lap_tel["X"].to_numpy()
            y_lap = lap_tel["Y"].to_numpy()
            d_lap = lap_tel["Distance"].to_numpy()
            rd_lap = lap_tel["RelativeDistance"].to_numpy()
            speed_kph_lap = lap_tel["Speed"].to_numpy()
            gear_lap = lap_tel["nGear"].to_numpy()
            drs_lap = lap_tel["DRS"].to_numpy()
            throttle_lap = lap_tel["Throttle"].to_numpy()
            brake_lap = lap_tel["Brake"].to_numpy().astype(float)
            
            # Calculate race distance
            race_d_lap = total_dist_so_far + d_lap
            
            # Append to collections
            t_all.append(t_lap)
            x_all.append(x_lap)
            y_all.append(y_lap)
            race_dist_all.append(race_d_lap)
            rel_dist_all.append(rd_lap)
            lap_numbers.append(np.full_like(t_lap, lap_number))
            tyre_compounds.append(np.full_like(t_lap, tyre_compound_as_int))
            speed_all.append(speed_kph_lap)
            gear_all.append(gear_lap)
            drs_all.append(drs_lap)
            throttle_all.append(throttle_lap)
            brake_all.append(brake_lap)
            
            # Update total distance for next lap
            if len(d_lap) > 0:
                total_dist_so_far += d_lap[-1]
        
        if not t_all:
            return None
        
        # Concatenate all arrays
        t_all = np.concatenate(t_all)
        x_all = np.concatenate(x_all)
        y_all = np.concatenate(y_all)
        race_dist_all = np.concatenate(race_dist_all)
        rel_dist_all = np.concatenate(rel_dist_all)
        lap_numbers = np.concatenate(lap_numbers)
        tyre_compounds = np.concatenate(tyre_compounds)
        speed_all = np.concatenate(speed_all)
        gear_all = np.concatenate(gear_all)
        drs_all = np.concatenate(drs_all)
        throttle_all = np.concatenate(throttle_all)
        brake_all = np.concatenate(brake_all)
        
        # Sort by time
        order = np.argsort(t_all)
        
        return {
            "code": driver_code,
            "data": {
                "t": t_all[order],
                "x": x_all[order],
                "y": y_all[order],
                "dist": race_dist_all[order],
                "rel_dist": rel_dist_all[order],
                "lap": lap_numbers[order],
                "tyre": tyre_compounds[order],
                "speed": speed_all[order],
                "gear": gear_all[order],
                "drs": drs_all[order],
                "throttle": throttle_all[order],
                "brake": brake_all[order],
            },
            "t_min": t_all.min(),
            "t_max": t_all.max(),
            "max_lap": driver_max_lap
        }
    
    def _get_time_bounds(self, driver_data: Dict[str, Dict[str, Any]]) -> Tuple[float, float]:
        """
        Get global time bounds across all drivers
        
        Args:
            driver_data: Dictionary of driver telemetry data
        
        Returns:
            Tuple of (min_time, max_time)
        """
        t_mins = [d["t_min"] for d in driver_data.values()]
        t_maxs = [d["t_max"] for d in driver_data.values()]
        
        return min(t_mins), max(t_maxs)
    
    def _resample_driver_data(
        self,
        driver_data: Dict[str, Dict[str, Any]],
        timeline: np.ndarray,
        global_t_min: float
    ) -> Dict[str, Dict[str, np.ndarray]]:
        """
        Resample all driver data onto common timeline
        
        Args:
            driver_data: Raw driver data
            timeline: Common timeline array
            global_t_min: Global minimum time
        
        Returns:
            Dictionary of resampled driver data
        """
        resampled_data = {}
        
        for code, data in driver_data.items():
            t = data["data"]["t"] - global_t_min  # Shift to zero
            
            # Sort by time
            order = np.argsort(t)
            t_sorted = t[order]
            
            # Resample continuous variables with interpolation
            arrays_to_resample = [
                data["data"]["x"][order],
                data["data"]["y"][order],
                data["data"]["dist"][order],
                data["data"]["rel_dist"][order],
                data["data"]["lap"][order],
                data["data"]["tyre"][order],
                data["data"]["speed"][order],
                data["data"]["gear"][order],
                data["data"]["drs"][order],
                data["data"]["throttle"][order],
                data["data"]["brake"][order],
            ]
            
            resampled = [np.interp(timeline, t_sorted, arr) for arr in arrays_to_resample]
            
            x_r, y_r, dist_r, rel_dist_r, lap_r, tyre_r, speed_r, gear_r, drs_r, throttle_r, brake_r = resampled
            
            resampled_data[code] = {
                "t": timeline,
                "x": x_r,
                "y": y_r,
                "dist": dist_r,
                "rel_dist": rel_dist_r,
                "lap": lap_r,
                "tyre": tyre_r,
                "speed": speed_r,
                "gear": gear_r,
                "drs": drs_r,
                "throttle": throttle_r,
                "brake": brake_r,
            }
        
        return resampled_data
    
    def _process_track_status(self, global_t_min: float) -> List[Dict[str, Any]]:
        """
        Process track status data (flags, safety car, etc.)
        
        Args:
            global_t_min: Global minimum time for offset
        
        Returns:
            List of track status events
        """
        track_status = self.session.track_status
        formatted_track_statuses = []
        
        for status in track_status.to_dict('records'):
            seconds = timedelta.total_seconds(status['Time'])
            start_time = seconds - global_t_min
            
            # Set end time of previous status
            if formatted_track_statuses:
                formatted_track_statuses[-1]['end_time'] = start_time
            
            formatted_track_statuses.append({
                'status': status['Status'],
                'start_time': start_time,
                'end_time': None,
            })
        
        return formatted_track_statuses
    
    def _process_weather_data(
        self,
        timeline: np.ndarray,
        global_t_min: float
    ) -> Optional[Dict[str, np.ndarray]]:
        """
        Process and resample weather data
        
        Args:
            timeline: Common timeline array
            global_t_min: Global minimum time for offset
        
        Returns:
            Dictionary of resampled weather data or None
        """
        weather_df = getattr(self.session, "weather_data", None)
        
        if weather_df is None or weather_df.empty:
            return None
        
        try:
            weather_times = weather_df["Time"].dt.total_seconds().to_numpy() - global_t_min
            
            if len(weather_times) == 0:
                return None
            
            # Sort by time
            order = np.argsort(weather_times)
            weather_times = weather_times[order]
            
            def _maybe_get(name):
                return weather_df[name].to_numpy()[order] if name in weather_df else None
            
            def _resample(series):
                if series is None:
                    return None
                return np.interp(timeline, weather_times, series)
            
            track_temp = _resample(_maybe_get("TrackTemp"))
            air_temp = _resample(_maybe_get("AirTemp"))
            humidity = _resample(_maybe_get("Humidity"))
            wind_speed = _resample(_maybe_get("WindSpeed"))
            wind_direction = _resample(_maybe_get("WindDirection"))
            rainfall_raw = _maybe_get("Rainfall")
            rainfall = _resample(rainfall_raw.astype(float)) if rainfall_raw is not None else None
            
            return {
                "track_temp": track_temp,
                "air_temp": air_temp,
                "humidity": humidity,
                "wind_speed": wind_speed,
                "wind_direction": wind_direction,
                "rainfall": rainfall,
            }
        
        except Exception as e:
            logger.warning(f"Weather data could not be processed: {e}")
            return None
    
    def _build_frames(
        self,
        timeline: np.ndarray,
        resampled_data: Dict[str, Dict[str, np.ndarray]],
        weather_resampled: Optional[Dict[str, np.ndarray]]
    ) -> List[Dict[str, Any]]:
        """
        Build frame-by-frame data for replay
        
        Args:
            timeline: Common timeline array
            resampled_data: Resampled driver data
            weather_resampled: Resampled weather data
        
        Returns:
            List of frame dictionaries
        """
        frames = []
        num_frames = len(timeline)
        
        driver_codes = list(resampled_data.keys())
        
        for i in range(num_frames):
            t = timeline[i]
            
            # Build driver snapshot
            driver_snapshot = {}
            for code in driver_codes:
                d = resampled_data[code]
                driver_snapshot[code] = {
                    "x": float(d["x"][i]),
                    "y": float(d["y"][i]),
                    "dist": float(d["dist"][i]),
                    "lap": int(round(d["lap"][i])),
                    "rel_dist": round(float(d["rel_dist"][i]), 4),
                    "tyre": float(d["tyre"][i]),
                    "position": 0,  # Will be calculated based on sorting
                    "speed": float(d["speed"][i]),
                    "gear": int(d["gear"][i]),
                    "drs": int(d["drs"][i]),
                    "throttle": float(d["throttle"][i]),
                    "brake": float(d["brake"][i]),
                }
            
            # Sort by race distance to get positions
            snapshot_list = list(driver_snapshot.items())
            snapshot_list.sort(key=lambda x: (x[1]["lap"], x[1]["dist"]), reverse=True)
            
            # Assign positions
            for pos, (code, data) in enumerate(snapshot_list, start=1):
                driver_snapshot[code]["position"] = pos
            
            # Get leader lap
            leader_lap = snapshot_list[0][1]["lap"] if snapshot_list else 1
            
            # Build frame payload
            frame_payload = {
                "t": round(t, 3),
                "lap": leader_lap,
                "drivers": driver_snapshot,
            }
            
            # Add weather if available
            if weather_resampled:
                try:
                    wt = weather_resampled
                    rain_val = wt["rainfall"][i] if wt.get("rainfall") is not None else 0.0
                    frame_payload["weather"] = {
                        "track_temp": float(wt["track_temp"][i]) if wt.get("track_temp") is not None else None,
                        "air_temp": float(wt["air_temp"][i]) if wt.get("air_temp") is not None else None,
                        "humidity": float(wt["humidity"][i]) if wt.get("humidity") is not None else None,
                        "wind_speed": float(wt["wind_speed"][i]) if wt.get("wind_speed") is not None else None,
                        "wind_direction": float(wt["wind_direction"][i]) if wt.get("wind_direction") is not None else None,
                        "rain_state": "RAINING" if rain_val and rain_val >= 0.5 else "DRY",
                    }
                except Exception as e:
                    logger.debug(f"Failed to attach weather to frame {i}: {e}")
            
            frames.append(frame_payload)
        
        return frames


def process_race_telemetry(session, session_type: str = 'R') -> Dict[str, Any]:
    """
    Convenience function to process race telemetry
    
    Args:
        session: FastF1 session object
        session_type: Session type ('R' or 'S')
    
    Returns:
        Processed telemetry data
    """
    processor = TelemetryProcessor(session)
    return processor.process_race_telemetry(session_type)
