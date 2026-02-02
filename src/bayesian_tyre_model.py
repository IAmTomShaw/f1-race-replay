import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from scipy import stats
from enum import Enum

class TyreCategory(Enum):
    SLICK = "SLICK"
    INTER = "INTER"
    WET = "WET"

class TrackCondition(Enum):
    DRY = "DRY"
    DAMP = "DAMP"
    WET = "WET"

@dataclass
class TyreProfile:
    name: str
    category: TyreCategory
    degradation_rate: float
    reset_pace: float
    warmup_laps: int
    max_analysis_laps: Optional[int]
    max_degradation: float
    
    def __post_init__(self):
        if self.degradation_rate < 0:
            raise ValueError(f"Degradation rate must be non-negative: {self.degradation_rate}")
        if self.warmup_laps < 0:
            raise ValueError(f"Warmup laps must be non-negative: {self.warmup_laps}")

@dataclass
class StateSpaceConfig:    
    sigma_epsilon: float = 0.3
    sigma_eta: float = 0.1
    fuel_effect_prior: float = 0.032
    starting_fuel: float = 110.0
    fuel_burn_rate: float = 1.6
    enable_warmup: bool = True
    enable_track_abrasion: bool = True  
    debug_logging: bool = False
    mismatch_penalties: Dict[Tuple[TyreCategory, TrackCondition], float] = None
    
    def __post_init__(self):
        if self.mismatch_penalties is None:
            self.mismatch_penalties = {
                (TyreCategory.SLICK, TrackCondition.DAMP): 2.0,
                (TyreCategory.SLICK, TrackCondition.WET): 8.0,
                (TyreCategory.INTER, TrackCondition.DRY): 1.5,
                (TyreCategory.INTER, TrackCondition.WET): 0.5,
                (TyreCategory.WET, TrackCondition.DRY): 4.0,
                (TyreCategory.WET, TrackCondition.DAMP): 1.0,
                (TyreCategory.SLICK, TrackCondition.DRY): 0.0,
                (TyreCategory.INTER, TrackCondition.DAMP): 0.0,
                (TyreCategory.WET, TrackCondition.WET): 0.0,
            }

class BayesianTyreDegradationModel:
    def __init__(self, config: Optional[StateSpaceConfig] = None):
        self.config = config or StateSpaceConfig()
        
        self.tyre_profiles: Dict[str, TyreProfile] = {
            'HARD': TyreProfile('HARD', TyreCategory.SLICK, 0.01, 69.5, 3, None, 2.0),
            'MEDIUM': TyreProfile('MEDIUM', TyreCategory.SLICK, 0.03, 69.0, 3, None, 2.0),
            'SOFT': TyreProfile('SOFT', TyreCategory.SLICK, 0.05, 68.5, 1, 10, 2.0),
            'INTERMEDIATE': TyreProfile('INTERMEDIATE', TyreCategory.INTER, 0.04, 75.0, 2, None, 3.0),
            'WET': TyreProfile('WET', TyreCategory.WET, 0.02, 80.0, 2, None, 2.5),
        }
        self.fuel_effect = self.config.fuel_effect_prior
        self.sigma_epsilon = self.config.sigma_epsilon
        self.sigma_eta = self.config.sigma_eta
        self.track_abrasion = 1.0
        self._abrasion_baseline = {'HARD': 0.003, 'MEDIUM': 0.009, 'SOFT': 0.015}
        self._latent_states = {}
        self._latent_uncertainty = {}
        self._fitted = False
        
    def estimate_track_abrasion(self, laps_df: pd.DataFrame) -> float:
        baseline = self._abrasion_baseline
        abrasion_samples = []
        for compound, base_rate in baseline.items():
            slick_laps = laps_df[(laps_df['Compound'] == compound) & (laps_df['TrackCondition'] == 'DRY')]
            if slick_laps.empty: continue
            for driver in slick_laps['Driver'].unique():
                driver_laps = slick_laps[slick_laps['Driver'] == driver]
                for stint in driver_laps['Stint'].unique():
                    stint_laps = driver_laps[driver_laps['Stint'] == stint]
                    if len(stint_laps) < 8: continue
                    stint_laps = stint_laps.copy()
                    stint_laps['LapOnTyre'] = range(1, len(stint_laps) + 1)
                    fuel_corrected = (stint_laps['LapTimeSeconds'] - self.fuel_effect * stint_laps['FuelMass'])
                    delta = fuel_corrected - fuel_corrected.iloc[0]
                    if delta.std() > 0:
                        slope, _, _, _ = stats.theilslopes(delta.values, stint_laps['LapOnTyre'].values)
                        if slope > 0: abrasion_samples.append(slope / base_rate)
        
        if len(abrasion_samples) < 3: return 1.0
        return float(np.clip(np.median(abrasion_samples), 0.7, 1.4))
        
    def fit(self, laps_df: pd.DataFrame, driver: Optional[str] = None):
        if driver: laps_df = laps_df[laps_df['Driver'] == driver]
        laps_clean = self._prepare_data(laps_df)
        if laps_clean.empty: return
        self.track_abrasion = self.estimate_track_abrasion(laps_clean) if self.config.enable_track_abrasion else 1.0
        self._estimate_parameters(laps_clean)
        self._compute_latent_states(laps_clean)
        self._fitted = True
        
    def _prepare_data(self, laps_df: pd.DataFrame) -> pd.DataFrame:
        laps = laps_df.copy()
        if 'TrackCondition' not in laps.columns: laps['TrackCondition'] = 'DRY'
        valid_conditions = {'DRY', 'DAMP', 'WET'}
        laps.loc[~laps['TrackCondition'].isin(valid_conditions), 'TrackCondition'] = 'DRY'
        laps = laps[(laps["LapNumber"] > 1) & laps["LapTime"].notna() & laps["Compound"].notna()]
        laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()
        laps["FuelMass"] = (self.config.starting_fuel - (laps["LapNumber"] - 1) * self.config.fuel_burn_rate).clip(lower=0)
        return laps.sort_values(["Driver", "LapNumber"])
    
    def _estimate_parameters(self, laps_df: pd.DataFrame):
        compound_slopes = {name: [] for name in self.tyre_profiles.keys()}
        for compound_name, tyre in self.tyre_profiles.items():
            compound_laps = laps_df[laps_df['Compound'] == compound_name]
            if len(compound_laps) < 5: continue
            for driver in compound_laps['Driver'].unique():
                driver_laps = compound_laps[compound_laps['Driver'] == driver]
                for stint in driver_laps['Stint'].unique():
                    stint_laps = driver_laps[driver_laps['Stint'] == stint]
                    if len(stint_laps) < 5: continue
                    valid_laps = stint_laps.copy()
                    valid_laps['LapOnTyre'] = range(1, len(valid_laps) + 1)
                    fuel_corrected = (valid_laps['LapTimeSeconds'] - self.fuel_effect * valid_laps['FuelMass'])
                    valid_laps['DeltaFromFirst'] = fuel_corrected - fuel_corrected.iloc[0]
                    analysis_laps = valid_laps
                    if len(analysis_laps) > 2:
                        x = analysis_laps['LapOnTyre'].values
                        y = analysis_laps['DeltaFromFirst'].values
                        if len(x) > 0 and np.std(y) > 0:
                            slope, _, _, _ = stats.theilslopes(y, x)
                            if slope > 0: compound_slopes[compound_name].append(max(0, slope))
        
        for compound_name, tyre in self.tyre_profiles.items():
            if len(compound_slopes[compound_name]) > 0:
                median_slope = np.median(compound_slopes[compound_name])
                prior_weight = 0.3
                tyre.degradation_rate = (prior_weight * tyre.degradation_rate + (1 - prior_weight) * median_slope)
    
    def _compute_mismatch_penalty(self, compound: str, track_condition: str) -> float:
        if compound not in self.tyre_profiles: return 0.0
        tyre_category = self.tyre_profiles[compound].category
        condition_map = {'DRY': TrackCondition.DRY, 'DAMP': TrackCondition.DAMP, 'WET': TrackCondition.WET}
        return self.config.mismatch_penalties.get((tyre_category, condition_map.get(track_condition, TrackCondition.DRY)), 0.0)
    
    def _compute_latent_states(self, laps_df: pd.DataFrame):
        self._latent_states = {}
        self._latent_uncertainty = {}
        obs_var = self.sigma_epsilon ** 2
        proc_var = self.sigma_eta ** 2
        
        for driver in laps_df["Driver"].unique():
            driver_laps = laps_df[laps_df["Driver"] == driver].sort_values("LapNumber")
            mu_alpha = None
            var_alpha = None
            states = []
            variances = []
            prev_stint = None
            
            for _, lap in driver_laps.iterrows():
                compound = lap["Compound"]
                stint = lap["Stint"]
                if compound not in self.tyre_profiles: continue
                tyre = self.tyre_profiles[compound]
                
                if mu_alpha is None or stint != prev_stint:
                    mu_alpha = tyre.reset_pace
                    var_alpha = proc_var
                    prev_stint = stint
                else:
                    nu = tyre.degradation_rate * self.track_abrasion
                    mu_pred = mu_alpha + nu
                    var_pred = var_alpha + proc_var
                    expected_lap = mu_pred + self.fuel_effect * lap["FuelMass"]
                    innovation = lap["LapTimeSeconds"] - expected_lap
                    kalman_gain = var_pred / (var_pred + obs_var)
                    mu_alpha = mu_pred + kalman_gain * innovation
                    var_alpha = (1.0 - kalman_gain) * var_pred
                states.append(mu_alpha)
                variances.append(var_alpha)
            self._latent_states[driver] = states
            self._latent_uncertainty[driver] = variances
    
    def predict_next_lap(self, driver: str, current_lap: int, laps_df: pd.DataFrame, track_condition: Optional[str] = None) -> Tuple[float, float, Dict]:
        if not self._fitted: raise RuntimeError("Model must be fitted before prediction")
        driver_laps = laps_df[(laps_df['Driver'] == driver) & (laps_df['LapNumber'] <= current_lap)].sort_values('LapNumber')
        if driver_laps.empty: return None, None, {}
        
        last_lap = driver_laps.iloc[-1]
        compound = last_lap['Compound']
        if compound not in self.tyre_profiles: return None, None, {}
        
        tyre = self.tyre_profiles[compound]
        stint_laps = driver_laps[driver_laps['Stint'] == last_lap['Stint']]
        laps_on_tyre = len(stint_laps)
        
        abrasion_factor = self.track_abrasion
        effective_degradation = tyre.degradation_rate * abrasion_factor
        alpha_t = tyre.reset_pace + (laps_on_tyre - 1) * effective_degradation
        
        track_condition = track_condition or last_lap.get('TrackCondition', 'DRY')
        mismatch_penalty = self._compute_mismatch_penalty(compound, track_condition)
        
        max_laps = tyre.max_degradation / max(effective_degradation, 0.001)
        effective_laps = laps_on_tyre * (1.0 + mismatch_penalty / 5.0)
        health = max(0, min(100, 100 * (1 - effective_laps / max_laps)))
        
        info = {
            'health': int(health),
            'laps_on_tyre': laps_on_tyre,
            'compound': compound,
            'effective_degradation': effective_degradation,
            'mismatch_penalty': mismatch_penalty,
            'track_condition': track_condition,
            'std_dev': 0.0, 'latent_pace': 0.0, 'category': tyre.category.value, 'track_abrasion': self.track_abrasion
        }
        return 0.0, 0.0, info