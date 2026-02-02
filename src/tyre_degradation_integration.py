import pandas as pd
from typing import Optional, Dict
from src.bayesian_tyre_model import BayesianTyreDegradationModel

class TyreDegradationIntegrator:
    def __init__(self, session=None, laps_df: Optional[pd.DataFrame] = None):
        self.session = session
        self._laps_df = laps_df
        self._model = BayesianTyreDegradationModel()
        self._initialized = False
        self._cache = {}
    
    def initialize_from_session(self) -> bool:
        try:
            if self._laps_df is None:
                if self.session is None:
                    print("BayesianModel: No session or laps data provided")
                    return False
                self._laps_df = self.session.laps
            
            if self._laps_df is None or self._laps_df.empty:
                print("BayesianModel: Empty laps dataframe")
                return False
            
            print(f"BayesianModel: Fitting state-space model on {len(self._laps_df)} laps...")
            self._model.fit(self._laps_df)
            self._initialized = True
            
            print("BayesianModel: Degradation rates (seconds/lap):")
            for compound_name, tyre in self._model.tyre_profiles.items():
                print(f"  {compound_name}: {tyre.degradation_rate:.4f}")
            return True
        except Exception as e:
            print(f"BayesianModel initialization error: {e}")
            return False
    
    def get_health_for_frame(self, driver_code: str, frame_data: Dict) -> Optional[Dict]:
        if not self._initialized or not frame_data or "drivers" not in frame_data: return None
        driver_pos = frame_data["drivers"].get(driver_code)
        if not driver_pos: return None
        
        try:
            lap_num = int(driver_pos.get("lap"))
        except (ValueError, TypeError): return None
        
        cache_key = f"{driver_code}_{lap_num}"
        if cache_key in self._cache: return self._cache[cache_key]
        
        try:
            _, _, info = self._model.predict_next_lap(driver_code, lap_num, self._laps_df)
            if info: self._cache[cache_key] = info
            return info
        except Exception:
            return None
    
    def clear_cache(self):
        self._cache.clear()

def format_tyre_health_bar(health: int, width: int = 100, height: int = 12) -> Dict:
    health = max(0, min(100, health))
    fill_width = (health / 100.0) * width
    if health >= 75: color = (0, 220, 0)
    elif health >= 50: color = (200, 220, 0)
    elif health >= 25: color = (220, 180, 0)
    else: color = (220, 50, 0)
    return {"width": width, "height": height, "fill_width": fill_width, "color": color, "health": health}

def format_degradation_text(health_data: Dict) -> str:
    if not health_data: return "N/A"
    return f"{health_data.get('compound', '?')} (L{health_data.get('laps_on_tyre', 0)}): {health_data.get('health', 0)}%"