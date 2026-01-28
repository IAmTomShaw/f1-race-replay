from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple
import numpy as np

class SyncMode(Enum):
    LAP = "lap"
    TIME = "time"
    DISTANCE = "distance"

class ViewMode(Enum):
    SPLIT = "split"
    OVERLAY = "overlay"
    DIFFERENCE = "difference"

@dataclass
class RaceData:
    """Wrapper for race telemetry data from get_race_telemetry"""
    frames: List[dict]
    driver_colors: Dict[str, Tuple[int, int, int]]
    track_statuses: List[dict]
    total_laps: int
    year: int
    round_number: int
    event_name: str
    session_type: str  # 'R' or 'S'

class RaceComparison:
    def __init__(self, race_a: RaceData, race_b: RaceData, 
                 sync_mode: SyncMode = SyncMode.LAP):
        self.race_a = race_a
        self.race_b = race_b
        self.sync_mode = sync_mode
        self.current_view = ViewMode.SPLIT
        
        # Precompute synchronized frame indices
        self._sync_map = self._build_sync_map()
        
    def _build_sync_map(self) -> List[Tuple[int, int]]:
        """Build mapping between frame indices of both races"""
        if self.sync_mode == SyncMode.LAP:
            return self._sync_by_lap()
        elif self.sync_mode == SyncMode.TIME:
            return self._sync_by_time()
        else:
            return self._sync_by_distance()
    
    def _sync_by_lap(self) -> List[Tuple[int, int]]:
        """Synchronize races lap-by-lap"""
        sync_map = []
        
        # Get lap arrays for both races (using first driver as reference)
        frames_a = self.race_a.frames
        frames_b = self.race_b.frames
        
        max_common_laps = min(self.race_a.total_laps, self.race_b.total_laps)
        
        for lap in range(1, max_common_laps + 1):
            # Find frame ranges for this lap in both races
            frames_a_lap = [i for i, f in enumerate(frames_a) if f['lap'] == lap]
            frames_b_lap = [i for i, f in enumerate(frames_b) if f['lap'] == lap]
            
            if not frames_a_lap or not frames_b_lap:
                continue
            
            # Align by interpolating to match frame counts
            len_a = len(frames_a_lap)
            len_b = len(frames_b_lap)
            
            if len_a >= len_b:
                # More frames in A, sample A to match B
                for i, idx_b in enumerate(frames_b_lap):
                    idx_a = frames_a_lap[int(i * len_a / len_b)]
                    sync_map.append((idx_a, idx_b))
            else:
                # More frames in B, sample B to match A
                for i, idx_a in enumerate(frames_a_lap):
                    idx_b = frames_b_lap[int(i * len_b / len_a)]
                    sync_map.append((idx_a, idx_b))
        
        return sync_map
    
    def _sync_by_time(self) -> List[Tuple[int, int]]:
        """Synchronize by race time (00:00 vs 00:00)"""
        sync_map = []
        
        frames_a = self.race_a.frames
        frames_b = self.race_b.frames
        
        # Get time arrays
        times_a = np.array([f['t'] for f in frames_a])
        times_b = np.array([f['t'] for f in frames_b])
        
        # Match by closest time value
        max_time = min(times_a[-1], times_b[-1])
        
        for i, time_a in enumerate(times_a):
            if time_a > max_time:
                break
            
            # Find closest time in race B
            idx_b = np.argmin(np.abs(times_b - time_a))
            sync_map.append((i, idx_b))
        
        return sync_map
    
    def _sync_by_distance(self) -> List[Tuple[int, int]]:
        """Synchronize by relative track position (0-100%)"""
        sync_map = []
        
        frames_a = self.race_a.frames
        frames_b = self.race_b.frames
        
        # Use leader distance as reference for each race
        for i, frame_a in enumerate(frames_a):
            # Get leader from race A
            leader_a = max(frame_a['drivers'].values(), key=lambda d: d['dist'])
            rel_dist_a = leader_a.get('rel_dist', 0)
            
            # Find closest relative distance in race B
            best_match = 0
            min_diff = float('inf')
            
            for j, frame_b in enumerate(frames_b):
                leader_b = max(frame_b['drivers'].values(), key=lambda d: d['dist'])
                rel_dist_b = leader_b.get('rel_dist', 0)
                
                diff = abs(rel_dist_a - rel_dist_b)
                if diff < min_diff:
                    min_diff = diff
                    best_match = j
            
            sync_map.append((i, best_match))
        
        return sync_map
    
    def get_synchronized_frames(self, playback_frame: int) -> Tuple[dict, dict]:
        """Get corresponding frames from both races for current playback position"""
        if playback_frame >= len(self._sync_map):
            playback_frame = len(self._sync_map) - 1
        
        idx_a, idx_b = self._sync_map[playback_frame]
        return self.race_a.frames[idx_a], self.race_b.frames[idx_b]
    
    def calculate_position_delta(self, frame_a: dict, frame_b: dict) -> Dict[str, int]:
        """Calculate position differences between races for each driver"""
        deltas = {}
        
        drivers_a = frame_a['drivers']
        drivers_b = frame_b['drivers']
        
        # Find common drivers
        common_drivers = set(drivers_a.keys()) & set(drivers_b.keys())
        
        for driver in common_drivers:
            pos_a = drivers_a[driver]['position']
            pos_b = drivers_b[driver]['position']
            deltas[driver] = pos_b - pos_a  # Positive = better in race A
        
        return deltas
    
    def calculate_time_delta(self, frame_a: dict, frame_b: dict, driver: str) -> Optional[float]:
        """Calculate time delta for specific driver between races"""
        if driver not in frame_a['drivers'] or driver not in frame_b['drivers']:
            return None
        
        # Use race distance to estimate time difference
        # This is approximate - real implementation needs lap time data
        dist_a = frame_a['drivers'][driver]['dist']
        dist_b = frame_b['drivers'][driver]['dist']
        
        # Rough estimate: assume average speed
        time_a = frame_a['t']
        time_b = frame_b['t']
        
        return time_b - time_a
    
    def get_comparison_metrics(self, playback_frame: int) -> dict:
        """Return comprehensive comparison data for UI display"""
        frame_a, frame_b = self.get_synchronized_frames(playback_frame)
        
        return {
            'lap_a': frame_a['lap'],
            'lap_b': frame_b['lap'],
            'time_a': frame_a['t'],
            'time_b': frame_b['t'],
            'position_deltas': self.calculate_position_delta(frame_a, frame_b),
            'leader_a': max(frame_a['drivers'].values(), key=lambda d: d['dist'])['position'],
            'leader_b': max(frame_b['drivers'].values(), key=lambda d: d['dist'])['position'],
        }
    
    def get_total_frames(self) -> int:
        """Total number of synchronized frames"""
        return len(self._sync_map)
    
    def change_sync_mode(self, new_mode: SyncMode):
        """Switch synchronization mode and rebuild mapping"""
        self.sync_mode = new_mode
        self._sync_map = self._build_sync_map()
    
    def toggle_view_mode(self):
        """Cycle through view modes"""
        modes = list(ViewMode)
        current_idx = modes.index(self.current_view)
        self.current_view = modes[(current_idx + 1) % len(modes)]