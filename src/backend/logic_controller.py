# from .dsa_engine import Boundary, QuadTree
# from .ai_engine import AIEngine
# import numpy as np

# class LogicController:
#     """
#     Phase 4: The Logic Controller. Serves as the main brain that orchestrates
#     the DSAEngine and AIEngine to produce the final 'Smart Data'.
#     """

#     def __init__(self, full_telemetry_data, fastest_lap_telemetry):
#         """
#         Initializes both engines and prepares internal state.
#         """
#         self.full_telemetry = full_telemetry_data
        
#         # 1. Determine bounding box for QuadTree initialization (critical for DSAEngine)
#         all_x = []
#         all_y = []
#         # Handle case where full_telemetry might be constructed differently in replay
#         for car_data in self.full_telemetry.values():
#              # Check if data is list or dict
#              xs = car_data['X'] if 'X' in car_data else []
#              ys = car_data['Y'] if 'Y' in car_data else []
#              all_x.extend(xs)
#              all_y.extend(ys)

#         if not all_x or not all_y:
#             print("[LOGIC CONTROLLER] Warning: Telemetry empty. Using default bounds.")
#             self.track_bounds = (-1000, -1000, 1000, 1000)
#         else:
#             min_x, max_x = np.min(all_x), np.max(all_x)
#             min_y, max_y = np.min(all_y), np.max(all_y)
#             self.track_bounds = (min_x, min_y, max_x, max_y)

#         # Initialize Engines
#         # We create the QuadTree FRESH every frame in get_frame_data, so we just need bounds here.
        
#         # AIEngine needs the fastest lap (Ghost Path)
#         self.ai_engine = AIEngine(fastest_lap_telemetry)
        
#         self.selected_driver = None 

#     def get_frame_data(self, frame_index, current_cars_snapshot):
#         """
#         Orchestrates all engines and returns the 'Smart Data' for the current frame.
#         current_cars_snapshot: List of dicts [{'code': 'VER', 'x': 100, 'y': 200}, ...]
#         """
        
#         # --- DSA ENGINE EXECUTION (QuadTree) ---
#         # 1. Initialize QuadTree for this frame
#         qt = QuadTree(Boundary(self.track_bounds[0], self.track_bounds[1], 
#                                self.track_bounds[2], self.track_bounds[3]))
        
#         # 2. Insert cars
#         for car in current_cars_snapshot:
#             qt.insert(car)
            
#         # 3. Query for battles
#         battling_drivers = set()
#         BATTLE_RADIUS = 50.0 # Proximity threshold
        
#         for car in current_cars_snapshot:
#             search_box = Boundary(car['x']-BATTLE_RADIUS, car['y']-BATTLE_RADIUS,
#                                   car['x']+BATTLE_RADIUS, car['y']+BATTLE_RADIUS)
#             neighbors = []
#             qt.query_range(search_box, neighbors)
            
#             if len(neighbors) > 1: # If neighbors > 1, it means [Self + Enemy] are close
#                 for n in neighbors:
#                     if n['code'] != car['code']:
#                         battling_drivers.add(car['code'])
#                         battling_drivers.add(n['code'])

#         # --- AI ENGINE EXECUTION (Skipped for Grand Prix Replay, used in AI Analyst) ---
#         # (We return empty AI data here because this is the 22-car simulation)
        
#         smart_data = {
#             'battling_drivers': battling_drivers, 
#             'ai_alerts': [] 
#         }
        
#         return smart_data


try:
    from .dsa_engine import Boundary, QuadTree, DisjointSet, IntervalTree
    from .ai_engine import AIEngine
except (ImportError, ValueError):
    from dsa_engine import Boundary, QuadTree, DisjointSet, IntervalTree
    from ai_engine import AIEngine
    
import numpy as np

class LogicController:
    """
    Phase 4: The Logic Controller. Serves as the main brain that orchestrates
    the DSAEngine and AIEngine to produce the final 'Smart Data'.
    """

    def __init__(self, full_telemetry_data, fastest_lap_telemetry):
        """
        Initializes both engines and prepares internal state.
        """
        self.full_telemetry = full_telemetry_data
        self.fastest_lap_telemetry = fastest_lap_telemetry
        
        # 1. Determine bounding box for QuadTree initialization
        all_x = []
        all_y = []
        for car_data in self.full_telemetry.values():
             xs = car_data.get('X', [])
             ys = car_data.get('Y', [])
             all_x.extend(xs)
             all_y.extend(ys)

        if not all_x:
            self.track_bounds = (-1000, -1000, 1000, 1000)
        else:
            min_x, max_x = np.min(all_x), np.max(all_x)
            min_y, max_y = np.min(all_y), np.max(all_y)
            self.track_bounds = (min_x, min_y, max_x, max_y)

        # FIX: Removed argument to match the new AIEngine signature
        self.ai_engine = AIEngine()

    def _generate_driver_sectors(self, driver_code):
        tree = IntervalTree()
        d_data = self.full_telemetry.get(driver_code)
        if not d_data or 'speed' not in d_data or len(d_data['speed']) == 0:
            return tree

        total_points = len(self.fastest_lap_telemetry['Speed'])
        num_sectors = 5 
        sector_size = total_points // num_sectors
        driver_points = len(d_data['speed'])
        scale_factor = driver_points / total_points
        
        for i in range(num_sectors):
            start_idx = i * sector_size
            end_idx = (i + 1) * sector_size
            ref_end = min(end_idx, total_points)
            ref_segment = self.fastest_lap_telemetry['Speed'][start_idx:ref_end]
            ref_speed = np.max(ref_segment) if len(ref_segment) > 0 else 1.0
            
            d_start = int(start_idx * scale_factor)
            d_end = int(end_idx * scale_factor)
            
            if d_start < driver_points:
                segment = d_data['speed'][d_start:min(d_end, driver_points)]
                if len(segment) > 0:
                    driver_speed = np.percentile(segment, 95)
                    ratio = driver_speed / ref_speed if ref_speed > 0 else 0
                    
                    if ratio >= 0.99: col = (180, 0, 255)
                    elif ratio >= 0.97: col = (0, 255, 0)
                    elif ratio >= 0.94: col = (255, 255, 0)
                    else: col = (255, 0, 0)
                    tree.insert(start_idx, end_idx, {'color': col})
        return tree

    def get_frame_data(self, frame_index, current_cars_snapshot, selected_driver=None):
        qt = QuadTree(Boundary(self.track_bounds[0], self.track_bounds[1], 
                               self.track_bounds[2], self.track_bounds[3]))
        for car in current_cars_snapshot:
            qt.insert(car)
            
        battling_drivers = set()
        BATTLE_RADIUS = 50.0 
        
        for car in current_cars_snapshot:
            search_box = Boundary(car['x']-BATTLE_RADIUS, car['y']-BATTLE_RADIUS,
                                  car['x']+BATTLE_RADIUS, car['y']+BATTLE_RADIUS)
            neighbors = []
            qt.query_range(search_box, neighbors)
            if len(neighbors) > 1: 
                for n in neighbors:
                    if n['code'] != car['code']:
                        battling_drivers.add(car['code'])
                        battling_drivers.add(n['code'])

        dsu = DisjointSet([c['code'] for c in current_cars_snapshot])
        DRS_RADIUS = 300.0 
        for car in current_cars_snapshot:
            drs_box = Boundary(car['x']-DRS_RADIUS, car['y']-DRS_RADIUS,
                               car['x']+DRS_RADIUS, car['y']+DRS_RADIUS)
            drs_neighbors = []
            qt.query_range(drs_box, drs_neighbors)
            for n in drs_neighbors:
                if n['code'] != car['code']:
                    dist = ((car['x']-n['x'])**2 + (car['y']-n['y'])**2)**0.5
                    if dist < DRS_RADIUS:
                        dsu.union(car['code'], n['code'])

        raw_groups = dsu.get_groups()
        drs_trains = {k: v for k, v in raw_groups.items() if len(v) > 1}

        sectors = []
        if selected_driver:
            driver_tree = self._generate_driver_sectors(selected_driver)
            sectors = driver_tree.traverse()

        return {
            'battling_drivers': battling_drivers, 
            'drs_trains': drs_trains,
            'sectors': sectors,
            'ai_alerts': [] 
        }