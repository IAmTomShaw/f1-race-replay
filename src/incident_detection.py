"""
Incident Detection Module

Analyzes race telemetry to detect and classify significant race events:
- Overtakes (position changes between drivers)
- Near-misses (drivers close together at high speed)
- Collisions (sudden distance reduction)
- Pit stops
- DRS usage patterns
"""

from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
import pandas as pd


@dataclass
class Incident:
    """Represents a single race incident"""
    frame_number: int
    time_seconds: float
    lap_number: int
    incident_type: str  # 'overtake', 'near_miss', 'collision', 'pit_stop'
    primary_driver: str
    secondary_driver: str = None
    description: str = ""
    severity: int = 1  # 1-5 scale
    
    def __str__(self):
        if self.secondary_driver:
            return f"[Lap {int(self.lap_number)}] {self.incident_type.title()}: {self.primary_driver} vs {self.secondary_driver} - {self.description}"
        else:
            return f"[Lap {int(self.lap_number)}] {self.incident_type.title()}: {self.primary_driver} - {self.description}"


class IncidentDetector:
    """Detects and classifies race incidents from telemetry data"""
    
    def __init__(self, frames: List[dict], drivers: pd.DataFrame, track_length: float = 5000):
        """
        Initialize incident detector
        
        Args:
            frames: List of frame dictionaries from race telemetry
            drivers: DataFrame of driver information
            track_length: Approximate track length in meters
        """
        self.frames = frames
        self.drivers = drivers
        self.track_length = track_length
        self.incidents = []
        self._driver_positions_history = {}  # Track position changes over time
        
    def detect_all_incidents(self) -> List[Incident]:
        """Run all incident detection methods and return sorted incidents"""
        self.incidents = []
        
        self._detect_overtakes()
        self._detect_near_misses()
        self._detect_pit_stops()
        
        # Sort by frame number
        self.incidents.sort(key=lambda x: x.frame_number)
        return self.incidents
    
    def _detect_overtakes(self):
        """Detect position changes (overtakes and being overtaken)"""
        if not self.frames or len(self.frames) < 2:
            return
        
        # Build position history
        position_history = {}  # frame_idx -> {driver_code: position}
        
        for frame_idx, frame in enumerate(self.frames):
            if 'driver_positions' not in frame:
                continue
            
            positions = {}
            # Build list of (driver_code, progress_score) for ranking
            driver_progress_list = []
            for driver_code, (x, y, lap, gap) in frame['driver_positions'].items():
                # Calculate progress metric: lap * 1000 + (1 - normalized_gap) gives priority to lap count
                progress_score = lap * 1000.0 + (1.0 - min(gap, 1.0))
                driver_progress_list.append((driver_code, progress_score))
            
            # Sort by progress score (descending) and assign integer positions
            driver_progress_list.sort(key=lambda item: item[1], reverse=True)
            for position, (driver_code, _) in enumerate(driver_progress_list, start=1):
                positions[driver_code] = position
            
            position_history[frame_idx] = positions
        
        # Detect position changes
        frame_indices = sorted(position_history.keys())
        check_interval = max(1, len(frame_indices) // 100)  # Sample roughly 100 checks across the entire sequence
        
        for i in range(check_interval, len(frame_indices), check_interval):
            prev_frame_idx = frame_indices[i - check_interval]
            curr_frame_idx = frame_indices[i]
            
            prev_positions = position_history.get(prev_frame_idx, {})
            curr_positions = position_history.get(curr_frame_idx, {})
            
            # Find drivers in both frames
            common_drivers = set(prev_positions.keys()) & set(curr_positions.keys())
            
            # Build position rankings
            prev_ranking = sorted(common_drivers, 
                                 key=lambda d: prev_positions[d], 
                                 reverse=True)
            curr_ranking = sorted(common_drivers, 
                                 key=lambda d: curr_positions[d], 
                                 reverse=True)
            
            # Find position changes
            for driver in common_drivers:
                prev_pos = prev_ranking.index(driver) if driver in prev_ranking else -1
                curr_pos = curr_ranking.index(driver) if driver in curr_ranking else -1
                
                if prev_pos >= 0 and curr_pos >= 0 and prev_pos > curr_pos:
                    # Driver moved up in position
                    frame = self.frames[curr_frame_idx]
                    driver_positions = frame.get('driver_positions', {})
                    
                    if driver in driver_positions:
                        _, _, lap, _ = driver_positions[driver]
                        
                        # Find who was overtaken: identify drivers whose position worsened
                        overtaken = None
                        for other_driver in common_drivers:
                            other_prev_pos = prev_ranking.index(other_driver) if other_driver in prev_ranking else -1
                            other_curr_pos = curr_ranking.index(other_driver) if other_driver in curr_ranking else -1
                            # Driver's position worsened if their rank decreased (lower index = worse in worst-first ranking)
                            if other_prev_pos >= 0 and other_curr_pos >= 0 and other_curr_pos < other_prev_pos:
                                # Check if this worsening is due to our driver passing
                                # Our driver passed if other was ahead (higher index) and now is not (lower or equal index)
                                if other_prev_pos > prev_pos and other_curr_pos <= curr_pos:
                                    overtaken = other_driver
                                    break
                        
                        # Only record if we found who was overtaken (actual overtake)
                        if overtaken and overtaken in driver_positions:
                            incident = Incident(
                                frame_number=frame.get('frame_number', curr_frame_idx),
                                time_seconds=frame.get('time_seconds', 0),
                                lap_number=lap,
                                incident_type='overtake',
                                primary_driver=driver,
                                secondary_driver=overtaken,
                                description=f"Position gain on track",
                                severity=3
                            )
                            self.incidents.append(incident)
    
    def _detect_near_misses(self):
        """Detect drivers in close proximity at high speed"""
        if not self.frames:
            return
        
        for frame_idx, frame in enumerate(self.frames):
            driver_positions = frame.get('driver_positions', {})
            
            if len(driver_positions) < 2:
                continue
            
            # Get all driver positions as list
            drivers_list = list(driver_positions.items())
            
            # Check all pairs
            for i in range(len(drivers_list)):
                for j in range(i + 1, len(drivers_list)):
                    driver1, (x1, y1, lap1, gap1) = drivers_list[i]
                    driver2, (x2, y2, lap2, gap2) = drivers_list[j]
                    
                    # Skip if on different laps
                    if abs(lap1 - lap2) > 0.5:
                        continue
                    
                    # Calculate distance between drivers
                    distance = np.sqrt((x2 - x1)**2 + (y2 - y1)**2)
                    
                    # Near miss threshold (200 meters)
                    if distance < 200 and distance > 0:
                        speed1 = frame.get('driver_speeds', {}).get(driver1, 0)
                        speed2 = frame.get('driver_speeds', {}).get(driver2, 0)
                        
                        # Only flag if both at decent speed (not in pits)
                        if speed1 > 50 and speed2 > 50:
                            incident = Incident(
                                frame_number=frame.get('frame_number', frame_idx),
                                time_seconds=frame.get('time_seconds', 0),
                                lap_number=lap1,
                                incident_type='near_miss',
                                primary_driver=driver1,
                                secondary_driver=driver2,
                                description=f"Close proximity (~{int(distance)}m)",
                                severity=2
                            )
                            # Only add if we haven't already recorded this incident
                            if not self._incident_exists(incident):
                                self.incidents.append(incident)
    
    def _detect_pit_stops(self):
        """Detect pit stop events"""
        if not self.frames or len(self.frames) < 10:
            return
        
        # Track speed drops to identify pit stops
        window_size = 10
        
        for frame_idx in range(window_size, len(self.frames)):
            frame = self.frames[frame_idx]
            driver_speeds = frame.get('driver_speeds', {})
            
            for driver, speed in driver_speeds.items():
                # Check if speed drops significantly
                prev_speeds = []
                for i in range(1, window_size + 1):
                    prev_frame = self.frames[frame_idx - i]
                    prev_speeds.append(prev_frame.get('driver_speeds', {}).get(driver, speed))
                
                avg_prev_speed = np.mean(prev_speeds) if prev_speeds else speed
                
                # Significant speed drop = pit stop
                if avg_prev_speed > 100 and speed < 40 and avg_prev_speed - speed > 50:
                    driver_positions = frame.get('driver_positions', {})
                    if driver in driver_positions:
                        _, _, lap, _ = driver_positions[driver]
                        
                        incident = Incident(
                            frame_number=frame.get('frame_number', frame_idx),
                            time_seconds=frame.get('time_seconds', 0),
                            lap_number=lap,
                            incident_type='pit_stop',
                            primary_driver=driver,
                            description="Pit stop",
                            severity=1
                        )
                        if not self._incident_exists(incident):
                            self.incidents.append(incident)
    
    def _incident_exists(self, incident: Incident, time_tolerance: float = 5.0) -> bool:
        """Check if similar incident already exists"""
        for existing in self.incidents:
            if (existing.incident_type == incident.incident_type and
                existing.primary_driver == incident.primary_driver and
                existing.secondary_driver == incident.secondary_driver and
                abs(existing.time_seconds - incident.time_seconds) < time_tolerance):
                return True
        return False
    
    def get_incidents_for_driver(self, driver_code: str) -> List[Incident]:
        """Get all incidents involving a specific driver"""
        return [i for i in self.incidents 
                if i.primary_driver == driver_code or i.secondary_driver == driver_code]
    
    def get_incidents_by_type(self, incident_type: str) -> List[Incident]:
        """Get all incidents of a specific type"""
        return [i for i in self.incidents if i.incident_type == incident_type]
