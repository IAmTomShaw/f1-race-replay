"""
Telemetry comparison utilities for F1 Race Replay.

This module provides functions to interpolate, align, and compare telemetry data 
from two different laps (e.g., Driver A vs Driver B, or Lap 1 vs Lap 50).
"""

import numpy as np
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, List


@dataclass
class TelemetryComparison:
    """
    Container for aligned telemetry data from two laps.
    
    Attributes:
        distance: Common distance array (meters) used as the x-axis index
        lap1_speed: Speed trace for lap 1 (km/h)
        lap2_speed: Speed trace for lap 2 (km/h)
        lap1_throttle: Throttle trace for lap 1 (0-100%)
        lap2_throttle: Throttle trace for lap 2 (0-100%)
        lap1_brake: Brake trace for lap 1 (0-100%)
        lap2_brake: Brake trace for lap 2 (0-100%)
        lap1_gear: Gear selection for lap 1
        lap2_gear: Gear selection for lap 2
        lap1_drs: DRS status for lap 1
        lap2_drs: DRS status for lap 2
        delta_time: Cumulative time difference (lap2 - lap1) in seconds
        lap1_label: Label for lap 1 (e.g., "VER Lap 1")
        lap2_label: Label for lap 2 (e.g., "HAM Lap 15")
        lap1_color: Color for lap 1 traces
        lap2_color: Color for lap 2 traces
        lap1_time: Total lap time for lap 1 (seconds)
        lap2_time: Total lap time for lap 2 (seconds)
    """
    distance: np.ndarray
    lap1_speed: np.ndarray
    lap2_speed: np.ndarray
    lap1_throttle: np.ndarray
    lap2_throttle: np.ndarray
    lap1_brake: np.ndarray
    lap2_brake: np.ndarray
    lap1_gear: np.ndarray
    lap2_gear: np.ndarray
    lap1_drs: np.ndarray
    lap2_drs: np.ndarray
    delta_time: np.ndarray
    lap1_label: str
    lap2_label: str
    lap1_color: Tuple[float, float, float] = (0.0, 0.8, 0.4)   # Green
    lap2_color: Tuple[float, float, float] = (0.8, 0.2, 0.2)   # Red
    lap1_time: Optional[float] = None
    lap2_time: Optional[float] = None


def interpolate_telemetry_to_distance(
    telemetry: Dict,
    distance_points: np.ndarray,
) -> Dict[str, np.ndarray]:
    """
    Interpolate telemetry data onto a common distance axis.
    
    The input telemetry dict must contain:
      - 'dist': distance array (meters)
      - 't': time array (seconds)
      - 'speed': speed array (km/h)
      - 'throttle': throttle array (0-100)
      - 'brake': brake array (0-100)
      - 'gear': gear array (int)
      - 'drs': DRS status array
      
    Args:
        telemetry: Dictionary containing telemetry arrays
        distance_points: Target distance array to interpolate onto
        
    Returns:
        Dictionary with interpolated telemetry arrays
    """
    # Extract source data
    src_dist = np.asarray(telemetry['dist'])
    src_time = np.asarray(telemetry['t'])
    src_speed = np.asarray(telemetry['speed'])
    src_throttle = np.asarray(telemetry['throttle'])
    src_brake = np.asarray(telemetry['brake'])
    src_gear = np.asarray(telemetry['gear'])
    src_drs = np.asarray(telemetry.get('drs', np.zeros_like(src_time)))
    
    # Sort by distance (ensure monotonically increasing for interp)
    order = np.argsort(src_dist)
    src_dist = src_dist[order]
    src_time = src_time[order]
    src_speed = src_speed[order]
    src_throttle = src_throttle[order]
    src_brake = src_brake[order]
    src_gear = src_gear[order]
    src_drs = src_drs[order]
    
    # Remove duplicate distance points (keep first occurrence)
    unique_dist, unique_idx = np.unique(src_dist, return_index=True)
    src_dist = unique_dist
    src_time = src_time[unique_idx]
    src_speed = src_speed[unique_idx]
    src_throttle = src_throttle[unique_idx]
    src_brake = src_brake[unique_idx]
    src_gear = src_gear[unique_idx]
    src_drs = src_drs[unique_idx]
    
    # Clip target distance to source range
    dist_min = src_dist.min()
    dist_max = src_dist.max()
    target_dist = np.clip(distance_points, dist_min, dist_max)
    
    # Interpolate continuous values
    interp_time = np.interp(target_dist, src_dist, src_time)
    interp_speed = np.interp(target_dist, src_dist, src_speed)
    interp_throttle = np.interp(target_dist, src_dist, src_throttle)
    interp_brake = np.interp(target_dist, src_dist, src_brake)
    
    # For discrete values (gear, DRS), use nearest-neighbor interpolation
    idx = np.searchsorted(src_dist, target_dist, side='right') - 1
    idx = np.clip(idx, 0, len(src_gear) - 1)
    interp_gear = src_gear[idx]
    interp_drs = src_drs[idx]
    
    return {
        'dist': target_dist,
        't': interp_time,
        'speed': interp_speed,
        'throttle': interp_throttle,
        'brake': interp_brake,
        'gear': interp_gear,
        'drs': interp_drs,
    }


def align_telemetry_by_distance(
    telemetry1: Dict,
    telemetry2: Dict,
    num_points: int = 1000,
) -> Tuple[np.ndarray, Dict[str, np.ndarray], Dict[str, np.ndarray]]:
    """
    Align two telemetry datasets to a common distance axis.
    
    Args:
        telemetry1: First telemetry dataset
        telemetry2: Second telemetry dataset
        num_points: Number of distance points for interpolation
        
    Returns:
        Tuple of (common_distance, interpolated_telemetry1, interpolated_telemetry2)
    """
    # Find common distance range
    dist1 = np.asarray(telemetry1['dist'])
    dist2 = np.asarray(telemetry2['dist'])
    
    dist_min = max(dist1.min(), dist2.min())
    dist_max = min(dist1.max(), dist2.max())
    
    # Create common distance axis
    common_dist = np.linspace(dist_min, dist_max, num_points)
    
    # Interpolate both telemetry sets to the common distance axis
    interp1 = interpolate_telemetry_to_distance(telemetry1, common_dist)
    interp2 = interpolate_telemetry_to_distance(telemetry2, common_dist)
    
    return common_dist, interp1, interp2


def calculate_delta_time(
    distance: np.ndarray,
    time1: np.ndarray,
    time2: np.ndarray,
) -> np.ndarray:
    """
    Calculate cumulative time delta between two laps.
    
    Positive delta means lap2 is slower (behind lap1).
    Negative delta means lap2 is faster (ahead of lap1).
    
    Args:
        distance: Common distance array
        time1: Time array for lap 1 (interpolated to distance)
        time2: Time array for lap 2 (interpolated to distance)
        
    Returns:
        Array of cumulative time deltas (lap2 - lap1) in seconds
    """
    # Delta time at each distance point
    delta = time2 - time1
    return delta


def extract_lap_telemetry_from_frames(frames: List[Dict]) -> Dict:
    """
    Extract telemetry arrays from a list of frame dictionaries.
    
    This is useful for converting qualifying or race telemetry frames 
    into the format expected by the comparison functions.
    
    Args:
        frames: List of frame dictionaries with 't' and 'telemetry' keys
        
    Returns:
        Dictionary with combined telemetry arrays
    """
    t_list = []
    dist_list = []
    speed_list = []
    throttle_list = []
    brake_list = []
    gear_list = []
    drs_list = []
    
    for frame in frames:
        t_list.append(frame['t'])
        tel = frame.get('telemetry', frame)  # Support both nested and flat formats
        dist_list.append(tel.get('dist', 0))
        speed_list.append(tel.get('speed', 0))
        throttle_list.append(tel.get('throttle', 0))
        brake_list.append(tel.get('brake', 0))
        gear_list.append(tel.get('gear', 0))
        drs_list.append(tel.get('drs', 0))
    
    return {
        't': np.array(t_list),
        'dist': np.array(dist_list),
        'speed': np.array(speed_list),
        'throttle': np.array(throttle_list),
        'brake': np.array(brake_list),
        'gear': np.array(gear_list),
        'drs': np.array(drs_list),
    }


def create_telemetry_comparison(
    telemetry1: Dict,
    telemetry2: Dict,
    label1: str = "Lap 1",
    label2: str = "Lap 2",
    color1: Tuple[float, float, float] = (0.0, 0.8, 0.4),
    color2: Tuple[float, float, float] = (0.8, 0.2, 0.2),
    num_points: int = 1000,
    lap_time1: Optional[float] = None,
    lap_time2: Optional[float] = None,
) -> TelemetryComparison:
    """
    Create a complete telemetry comparison object from two telemetry datasets.
    
    Args:
        telemetry1: First telemetry dataset
        telemetry2: Second telemetry dataset
        label1: Label for first lap (e.g., "VER Q3")
        label2: Label for second lap (e.g., "HAM Q3")
        color1: RGB tuple for lap 1 traces
        color2: RGB tuple for lap 2 traces
        num_points: Number of distance points for interpolation
        lap_time1: Total lap time for lap 1 (seconds)
        lap_time2: Total lap time for lap 2 (seconds)
        
    Returns:
        TelemetryComparison object with aligned data
    """
    # Align telemetry to common distance axis
    distance, interp1, interp2 = align_telemetry_by_distance(
        telemetry1, telemetry2, num_points
    )
    
    # Calculate delta time
    delta_time = calculate_delta_time(distance, interp1['t'], interp2['t'])
    
    return TelemetryComparison(
        distance=distance,
        lap1_speed=interp1['speed'],
        lap2_speed=interp2['speed'],
        lap1_throttle=interp1['throttle'],
        lap2_throttle=interp2['throttle'],
        lap1_brake=interp1['brake'],
        lap2_brake=interp2['brake'],
        lap1_gear=interp1['gear'],
        lap2_gear=interp2['gear'],
        lap1_drs=interp1['drs'],
        lap2_drs=interp2['drs'],
        delta_time=delta_time,
        lap1_label=label1,
        lap2_label=label2,
        lap1_color=color1,
        lap2_color=color2,
        lap1_time=lap_time1,
        lap2_time=lap_time2,
    )
