import pandas as pd
from typing import Optional, Dict
from src.bayesian_tyre_model import BayesianTyreDegradationModel
# TASK 2: explicit availability contract. The Bayesian model
# has a placeholder path that returns ``{'actual_delta': 0.0,
# 'overdriving': False}`` when no fit is available. We
# translate that placeholder into a real ``available=False``
# ``TyreModelResult`` at the integrator boundary so the UI
# renders "not available" rather than treating 0 / False as
# a real analytics value.
from src.analytics.tyre_model_availability import (
    TyreModelResult,
    is_placeholder,
    not_available,
    available_result,
)


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

        # TASK 2: at the consumer boundary, translate the
        # legacy placeholder into an explicit "not available"
        # result. ``wrap_legacy`` preserves the public dict
        # shape (``actual_delta`` / ``overdriving`` are set to
        # ``None`` and ``available`` is added) so existing UI
        # code that reads the dict keeps working.
        health = self.get_tyre_health(driver_code, lap_num,
                                       track_condition)
        return _wrap_with_availability(health)
    
    def clear_cache(self):
        """Clear cache."""
        self._cache.clear()


def _wrap_with_availability(health: Optional[Dict]) -> Optional[Dict]:
    """TASK 2: at the integrator boundary, replace the legacy
    placeholder ``(actual_delta=0.0, overdriving=False)`` with
    an explicit ``available=False`` result. Real values pass
    through with an added ``available=True`` flag.
    """
    if not health:
        return health
    actual_delta = health.get("actual_delta", 0.0)
    overdriving = health.get("overdriving", False)
    if is_placeholder(actual_delta, overdriving):
        result = not_available("Bayesian tyre model returned a "
                                 "placeholder (no fit available)")
    else:
        result = available_result(
            baseline_pace=float(health.get("baseline_pace", 0.0))
                         or 0.0,
            expected_pace=float(health.get("expected_pace", 0.0))
                         or float(health.get("expected_delta", 0.0)) * -1
                         or 0.0,
            actual_delta=float(actual_delta),
            credible_low=float(health.get("credible_low",
                                            actual_delta)),
            credible_high=float(health.get("credible_high",
                                             actual_delta)),
            overdriving=bool(overdriving),
            tyre_age_laps=int(health.get("laps_on_tyre", 0) or 0),
            compound=str(health.get("compound", "?")),
        )
    # Merge strategy:
    # 1. Start from the legacy health dict (it carries
    #    compound / laps_on_tyre / health / expected_delta, which
    #    ``format_degradation_text`` reads).
    # 2. Overlay the availability contract. Keys that the
    #    contract sets to ``None`` (e.g. actual_delta,
    #    overdriving, credible_low / high when unavailable)
    #    OVERWRITE the legacy values, because those are exactly
    #    the placeholders the contract says must be cleared.
    # 3. Add contract-only keys (``available``,
    #    ``not_available_reason``) that the legacy dict lacks.
    public = result.to_public_dict()
    merged: Dict = dict(health)
    for k, v in public.items():
        # None from the public dict wins for these specific
        # keys (the contract says "clear the placeholder").
        if k in {"actual_delta", "overdriving", "credible_low",
                 "credible_high", "baseline_pace", "expected_pace",
                 "tyre_age_laps"}:
            merged[k] = v
        elif k in merged and merged[k] is None:
            # public has a value but legacy's was None; prefer
            # the public one.
            merged[k] = v
        elif k not in merged:
            merged[k] = v
        # else: legacy has a non-None value and the public
        # didn't change it; keep the legacy value.
    return merged


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
    """Format degradation info as text.

    TASK 2: if the integrator flagged the result as unavailable,
    render ``"N/A (tyre model: not available)"`` rather than
    presenting placeholder values as real analytics.
    """
    if not health_data:
        return "N/A"

    if health_data.get("available") is False:
        return "N/A (tyre model: not available)"

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