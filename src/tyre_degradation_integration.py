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
            
            print("BayesianModel: Degradation rates (seconds/lap) (If a set of tyres were not used in the race, the deg value denoted is the prior assumed in the model):")
            for compound_name, tyre in self._model.tyre_profiles.items():
                print(f"  {compound_name} ({tyre.category.value}): {tyre.degradation_rate:.4f}")
            
            return True
            
        except Exception as e:
            print(f"BayesianModel initialization error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def is_initialized(self) -> bool:
        
        return self._initialized
    
    def get_tyre_health(
        self,
        driver_code: str,
        current_lap: int,
        track_condition: Optional[str] = None,
        force_refresh: bool = False
    ) -> Optional[Dict]:
        
        if not self._initialized:
            return None
        
        cache_key = f"{driver_code}_{current_lap}_{track_condition}"
        if not force_refresh and cache_key in self._cache:
            return self._cache[cache_key]
        
        try:
            health_data = self._model.get_health(
                driver_code,
                current_lap,
                self._laps_df,
                track_condition
            )
            
            if health_data:
                self._cache[cache_key] = health_data
            
            return health_data
            
        except Exception as e:
            print(f"BayesianModel query error for {driver_code} lap {current_lap}: {e}")
            return None
    
    def get_health_for_frame(
        self,
        driver_code: str,
        frame_data: Dict,
        frame_index: Optional[int] = None
    ) -> Optional[Dict]:
        """Get health from frame - compatible with existing UI."""
        if not frame_data or "drivers" not in frame_data:
            return None
        
        driver_pos = frame_data["drivers"].get(driver_code)
        if not driver_pos:
            return None
        
        lap = driver_pos.get("lap")
        if lap is None:
            return None
        
        try:
            lap_num = int(lap)
        except (ValueError, TypeError):
            return None
        
        
        track_condition = frame_data.get("track_condition")
        
        return self.get_tyre_health(driver_code, lap_num, track_condition)
    
    def get_model_outputs(self, driver_code: str, current_lap: int) -> Optional[Dict]:
        """
        Tyre-model outputs for one driver, as plain JSON-friendly values.

        Used to share the model with other windows over the telemetry stream
        (e.g. the Car Detail insight). Cached per driver and lap.

        Keys:
            compound, laps_on_tyre, health (0-100), wear_s_per_lap,
            time_lost_s, laps_left (until the model's wear limit),
            uncertainty_s (1 sd), next_lap_s / next_lap_low_s / next_lap_high_s
            (None until the driver has a clean lap on this set of tyres).
        """
        if not self._initialized:
            return None

        key = ("outputs", driver_code, int(current_lap))
        if key in self._cache:
            return self._cache[key]

        try:
            _, std_dev, info = self._model.predict_next_lap(driver_code, current_lap, self._laps_df)
        except Exception:
            info = None
        if not info:
            self._cache[key] = None
            return None

        wear = float(info["effective_degradation"])
        laps_on_tyre = int(info["laps_on_tyre"])
        health = int(info["health"])

        laps_left = None
        profile = self._model.tyre_profiles.get(info["compound"])
        if profile is not None and wear > 0:
            # health = 100 * (1 - laps / max_laps), so what's left is health% of max_laps
            laps_left = round(profile.max_degradation / wear * health / 100.0, 1)

        # Next lap: the driver's last clean lap on this set of tyres, plus one
        # more lap of wear, minus the time gained from burning a lap of fuel.
        next_lap = low = high = None
        last_lap = self._last_clean_lap_s(driver_code, current_lap)
        if last_lap is not None:
            fuel_gain = self._model.fuel_effect * self._model.config.fuel_burn_rate
            next_lap = last_lap + wear - fuel_gain
            low, high = next_lap - 1.96 * float(std_dev), next_lap + 1.96 * float(std_dev)

        outputs = {
            "compound": info["compound"],
            "laps_on_tyre": laps_on_tyre,
            "health": health,
            "wear_s_per_lap": round(wear, 4),
            "time_lost_s": round(wear * laps_on_tyre, 3),
            "laps_left": laps_left,
            "uncertainty_s": round(float(std_dev), 3),
            "next_lap_s": None if next_lap is None else round(next_lap, 3),
            "next_lap_low_s": None if low is None else round(low, 3),
            "next_lap_high_s": None if high is None else round(high, 3),
        }
        self._cache[key] = outputs
        return outputs

    def _last_clean_lap_s(self, driver_code: str, current_lap: int) -> Optional[float]:
        """Last completed lap before ``current_lap`` on the same tyres, skipping pit laps."""
        laps = self._laps_df
        if laps is None or laps.empty:
            return None
        mine = laps[laps["Driver"] == driver_code]
        current = mine[mine["LapNumber"] == current_lap]
        done = mine[(mine["LapNumber"] < current_lap) & mine["LapTime"].notna()]
        if not current.empty and "Stint" in mine.columns and pd.notna(current.iloc[0]["Stint"]):
            done = done[done["Stint"] == current.iloc[0]["Stint"]]
        for column in ("PitInTime", "PitOutTime"):
            if column in done.columns:
                done = done[done[column].isna()]
        if done.empty:
            return None
        return float(done.sort_values("LapNumber").iloc[-1]["LapTime"].total_seconds())

    def clear_cache(self):
        """Clear cache."""
        self._cache.clear()


def format_tyre_health_bar(health: int, width: int = 100, height: int = 12) -> Dict:
    """Format health bar visualization data."""
    health = max(0, min(100, health))
    fill_width = (health / 100.0) * width
    
    if health >= 75:
        color = (0, 220, 0)
    elif health >= 50:
        ratio = (health - 50) / 25.0
        color = (int(220 * (1 - ratio)), 220, 0)
    elif health >= 25:
        ratio = (health - 25) / 25.0
        color = (220, int(220 * ratio), 0)
    else:
        ratio = health / 25.0
        color = (220, int(110 * ratio), 0)
    
    return {
        "width": width,
        "height": height,
        "fill_width": fill_width,
        "color": color,
        "health": health
    }

def format_degradation_text(health_data: Dict) -> str:
    """Format degradation info as text."""
    if not health_data:
        return "N/A"
    
    compound = health_data.get("compound", "?")
    laps = health_data.get("laps_on_tyre", 0)
    health = health_data.get("health", 0)
    expected = health_data.get("expected_delta", 0.0)
    
    base = f"{compound} (L{laps}): {health}%"
    
    if expected > 0:
        base += f" • +{expected:.1f}s"
    
    if health_data.get("overdriving", False):
        base += " ⚠"
    
    if "uncertainty" in health_data:
        base += f" (±{health_data['uncertainty']:.2f}s)"
    
    return base