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
    """
    Universal Bayesian state-space model for all tyre compounds with track abrasion.
    
    State equation:
        α_{t+1} = (1 - I_pit) * (α_t + ν * A_track) + I_pit * α_reset + η_t
        
    Observation equation:
        y_t = α_t + γ * fuel_t + δ_mismatch + ε_t
        
    Where:
        α_t = latent tire pace (true lap time capability)
        ν = degradation rate (compound-specific, seconds per lap)
        A_track = track abrasion factor (track-specific, dimensionless)
        γ = fuel effect (seconds per kg)
        δ_mismatch = condition-tyre mismatch penalty
        I_pit = indicator for pit stop
        α_reset = pace reset after pit stop
    """
    
    def __init__(self, config: Optional[StateSpaceConfig] = None):
        self.config = config or StateSpaceConfig()
        
        self.tyre_profiles: Dict[str, TyreProfile] = {
            'HARD': TyreProfile(
                name='HARD',
                category=TyreCategory.SLICK,
                degradation_rate=0.01,
                reset_pace=69.5,
                warmup_laps=3,
                max_analysis_laps=None,
                max_degradation=2.0
            ),
            'MEDIUM': TyreProfile(
                name='MEDIUM',
                category=TyreCategory.SLICK,
                degradation_rate=0.03,
                reset_pace=69.0,
                warmup_laps=3,
                max_analysis_laps=None,
                max_degradation=2.0
            ),
            'SOFT': TyreProfile(
                name='SOFT',
                category=TyreCategory.SLICK,
                degradation_rate=0.05,
                reset_pace=68.5,
                warmup_laps=1,
                max_analysis_laps=10,
                max_degradation=2.0
            ),
            'INTERMEDIATE': TyreProfile(
                name='INTERMEDIATE',
                category=TyreCategory.INTER,
                degradation_rate=0.04,
                reset_pace=75.0,
                warmup_laps=2,
                max_analysis_laps=None,
                max_degradation=3.0
            ),
            'WET': TyreProfile(
                name='WET',
                category=TyreCategory.WET,
                degradation_rate=0.02,
                reset_pace=80.0,
                warmup_laps=2,
                max_analysis_laps=None,
                max_degradation=2.5
            ),
        }
        
        self.fuel_effect = self.config.fuel_effect_prior
        self.sigma_epsilon = self.config.sigma_epsilon
        self.sigma_eta = self.config.sigma_eta
        
        self.track_abrasion = 1.0
        
        self._abrasion_baseline = {
            'HARD': 0.003,
            'MEDIUM': 0.009,
            'SOFT': 0.015
        }
        
        self._latent_states = {}
        self._latent_uncertainty = {}
        self._fitted = False
        
    def estimate_track_abrasion(self, laps_df: pd.DataFrame) -> float:
        baseline = self._abrasion_baseline
        
        abrasion_samples = []
        
        for compound, base_rate in baseline.items():
            slick_laps = laps_df[
                (laps_df['Compound'] == compound) &
                (laps_df['TrackCondition'] == 'DRY')
            ]
            
            if slick_laps.empty:
                continue
            
            for driver in slick_laps['Driver'].unique():
                driver_laps = slick_laps[slick_laps['Driver'] == driver]
                
                for stint in driver_laps['Stint'].unique():
                    stint_laps = driver_laps[driver_laps['Stint'] == stint]
                    
                    if len(stint_laps) < 8:
                        continue
                    
                    stint_laps = stint_laps.copy()
                    stint_laps['LapOnTyre'] = range(1, len(stint_laps) + 1)
                    
                    fuel_corrected = (
                        stint_laps['LapTimeSeconds'] -
                        self.fuel_effect * stint_laps['FuelMass']
                    )
                    
                    delta = fuel_corrected - fuel_corrected.iloc[0]
                    
                    if delta.std() > 0:
                        slope, _, _, _ = stats.theilslopes(
                            delta.values, 
                            stint_laps['LapOnTyre'].values
                        )
                        
                        if slope > 0:
                            abrasion_samples.append(slope / base_rate)
        
        if len(abrasion_samples) < 3:
            if self.config.debug_logging:
                print("  Track abrasion: 1.000 (insufficient data, using neutral)")
            return 1.0  # Fallback to neutral
        
        abrasion = float(np.clip(np.median(abrasion_samples), 0.7, 1.4))
        
        if self.config.debug_logging:
            track_type = "abrasive" if abrasion > 1.05 else "smooth" if abrasion < 0.95 else "neutral"
            print(f"  Track abrasion: {abrasion:.3f} ({track_type}, from {len(abrasion_samples)} stints)")
        
        return abrasion
        
    def fit(self, laps_df: pd.DataFrame, driver: Optional[str] = None):
        """Fit model to lap data."""
        if driver:
            laps_df = laps_df[laps_df['Driver'] == driver]
        
        laps_clean = self._prepare_data(laps_df)
        
        if laps_clean.empty:
            print("Warning: No valid laps after data preparation")
            return
        
        if self.config.enable_track_abrasion:
            self.track_abrasion = self.estimate_track_abrasion(laps_clean)
        else:
            self.track_abrasion = 1.0
        
        self._estimate_parameters(laps_clean)
        self._compute_latent_states(laps_clean)
        
        self._fitted = True
        
    def _prepare_data(self, laps_df: pd.DataFrame) -> pd.DataFrame:
        """Clean and validate lap data."""
        laps = laps_df.copy()
        
        if 'TrackCondition' not in laps.columns:
            print("Warning: TrackCondition column missing, assuming DRY conditions")
            laps['TrackCondition'] = 'DRY'
        
        valid_conditions = {'DRY', 'DAMP', 'WET'}
        invalid_conditions = set(laps['TrackCondition'].unique()) - valid_conditions
        if invalid_conditions:
            print(f"Warning: Invalid track conditions found: {invalid_conditions}, setting to DRY")
            laps.loc[~laps['TrackCondition'].isin(valid_conditions), 'TrackCondition'] = 'DRY'
        
        is_pit_out = laps["PitOutTime"].notna()
        is_pit_in = laps["PitInTime"].notna()
        
        laps = laps[
            (laps["LapNumber"] > 1) &
            ~is_pit_in &
            ~is_pit_out &
            laps["LapTime"].notna() &
            laps["Compound"].notna()
        ]
        
        laps["LapTimeSeconds"] = laps["LapTime"].dt.total_seconds()
        
        laps["FuelMass"] = (
            self.config.starting_fuel -
            (laps["LapNumber"] - 1) * self.config.fuel_burn_rate
        ).clip(lower=0)
        
        laps = laps.sort_values(["Driver", "LapNumber"])
        
        return laps
    
    def _get_tyre_category(self, compound: str) -> TyreCategory:
        if compound not in self.tyre_profiles:
            print(f"Warning: Unknown compound '{compound}', assuming MEDIUM slick")
            return TyreCategory.SLICK
        return self.tyre_profiles[compound].category
    
    def _should_use_lap_for_fitting(
        self,
        compound: str,
        track_condition: str
    ) -> bool:
        tyre_category = self._get_tyre_category(compound)
        
        condition_map = {
            'DRY': TrackCondition.DRY,
            'DAMP': TrackCondition.DAMP,
            'WET': TrackCondition.WET
        }
        condition = condition_map.get(track_condition, TrackCondition.DRY)
        
        matching_conditions = {
            TyreCategory.SLICK: [TrackCondition.DRY],
            TyreCategory.INTER: [TrackCondition.DAMP, TrackCondition.WET, TrackCondition.DRY],
            TyreCategory.WET: [TrackCondition.WET]
        }
        
        return condition in matching_conditions.get(tyre_category, [])
    
    def _estimate_parameters(self, laps_df: pd.DataFrame):
        compound_slopes = {name: [] for name in self.tyre_profiles.keys()}
        
        for compound_name, tyre in self.tyre_profiles.items():
            compound_laps = laps_df[laps_df['Compound'] == compound_name]
            
            if len(compound_laps) < 5:
                continue
            
            for driver in compound_laps['Driver'].unique():
                driver_laps = compound_laps[compound_laps['Driver'] == driver]
                
                for stint in driver_laps['Stint'].unique():
                    stint_laps = driver_laps[driver_laps['Stint'] == stint]
                    
                    if len(stint_laps) < 5:
                        continue
                    valid_laps = stint_laps[
                        stint_laps.apply(
                            lambda row: self._should_use_lap_for_fitting(
                                row['Compound'],
                                row['TrackCondition']
                            ),
                            axis=1
                        )
                    ]
                    
                    if len(valid_laps) < 3:
                        continue
                    
                    valid_laps = valid_laps.copy()
                    valid_laps['LapOnTyre'] = range(1, len(valid_laps) + 1)
                    
                    fuel_corrected = (
                        valid_laps['LapTimeSeconds'] -
                        self.fuel_effect * valid_laps['FuelMass']
                    )
                    
                    first_fc = fuel_corrected.iloc[0]
                    valid_laps['DeltaFromFirst'] = fuel_corrected - first_fc
                    
                    if self.config.enable_warmup:
                        analysis_laps = valid_laps[
                            valid_laps['LapOnTyre'] > tyre.warmup_laps
                        ]
                    else:
                        analysis_laps = valid_laps
                    
                    if tyre.max_analysis_laps is not None:
                        analysis_laps = analysis_laps[
                            analysis_laps['LapOnTyre'] <= tyre.max_analysis_laps
                        ]
                    
                    if len(analysis_laps) > 2:
                        x = analysis_laps['LapOnTyre'].values
                        y = analysis_laps['DeltaFromFirst'].values
                        
                        if len(x) > 0 and np.std(y) > 0:
                            slope, _, _, _ = stats.theilslopes(y, x)
                            slope = max(0, slope)
                            
                            if self.config.enable_track_abrasion and self.track_abrasion > 0:
                                slope = slope / self.track_abrasion
                            
                            if tyre.category == TyreCategory.INTER:
                                dry_fraction = (valid_laps['TrackCondition'] == 'DRY').sum() / len(valid_laps)
                                if dry_fraction > 0.3:
                                    slope = min(slope, 0.08)
                            
                            compound_slopes[compound_name].append(slope)
        
        for compound_name, tyre in self.tyre_profiles.items():
            if len(compound_slopes[compound_name]) > 0:
                median_slope = np.median(compound_slopes[compound_name])
                
                if tyre.category == TyreCategory.SLICK:
                    prior_weight = 0.3
                elif tyre.category == TyreCategory.INTER:
                    prior_weight = 0.4
                else:  
                    prior_weight = 0.5
                
                updated_rate = (
                    prior_weight * tyre.degradation_rate +
                    (1 - prior_weight) * median_slope
                )
                
                tyre.degradation_rate = updated_rate
                
                print(f"  {compound_name}: {tyre.degradation_rate:.4f} s/lap "
                      f"(from {len(compound_slopes[compound_name])} stints)")
            else:
                print(f"  {compound_name}: {tyre.degradation_rate:.4f} s/lap "
                      f"(using prior - insufficient valid stints)")
    
    def _compute_mismatch_penalty(
        self,
        compound: str,
        track_condition: str
    ) -> float:
        if compound not in self.tyre_profiles:
            return 0.0
        
        tyre_category = self.tyre_profiles[compound].category
        
        condition_map = {
            'DRY': TrackCondition.DRY,
            'DAMP': TrackCondition.DAMP,
            'WET': TrackCondition.WET
        }
        condition = condition_map.get(track_condition, TrackCondition.DRY)
        
        return self.config.mismatch_penalties.get(
            (tyre_category, condition),
            0.0
        )
    
    def _compute_latent_states(self, laps_df: pd.DataFrame):
        self._latent_states = {}
        self._latent_uncertainty = {}
        
        obs_var = self.sigma_epsilon ** 2
        proc_var = self.sigma_eta ** 2
        
        for driver in laps_df["Driver"].unique():
            driver_laps = (
                laps_df[laps_df["Driver"] == driver]
                .sort_values("LapNumber")
                .reset_index(drop=True)
            )
            
            mu_alpha = None
            var_alpha = None
            states = []
            variances = []
            prev_stint = None
            prev_condition_category = None
            
            for _, lap in driver_laps.iterrows():
                compound = lap["Compound"]
                lap_time = lap["LapTimeSeconds"]
                fuel = lap["FuelMass"]
                stint = lap["Stint"]
                track_condition = lap.get("TrackCondition", "DRY")
                
                if compound not in self.tyre_profiles:
                    print(f"Warning: Unknown compound '{compound}' for {driver}, carrying forward state")
                    if mu_alpha is not None:
                        states.append(mu_alpha)
                        variances.append(var_alpha)
                    continue
                
                tyre = self.tyre_profiles[compound]
                
                condition_map = {
                    'DRY': TrackCondition.DRY,
                    'DAMP': TrackCondition.DAMP,
                    'WET': TrackCondition.WET
                }
                current_condition = condition_map.get(track_condition, TrackCondition.DRY)
                
                condition_category = 'DRY' if current_condition == TrackCondition.DRY else 'WET'
                
                condition_changed = (
                    prev_condition_category is not None and
                    prev_condition_category != condition_category
                )
                
                if mu_alpha is None or stint != prev_stint or condition_changed:
                    if condition_changed and self.config.debug_logging:
                        old_category = prev_condition_category
                        print(f"  {driver}: Track transition {old_category}→{condition_category}, resetting pace")
                    
                    mu_alpha = tyre.reset_pace
                    var_alpha = proc_var
                    prev_stint = stint
                    prev_condition_category = condition_category
                else:
                    abrasion_factor = self.track_abrasion
                    if tyre.category == TyreCategory.WET:
                        abrasion_factor = 1.0 + 0.3 * (self.track_abrasion - 1.0)
                    
                    nu = tyre.degradation_rate * abrasion_factor
                    
                    mismatch_penalty = self._compute_mismatch_penalty(
                        compound,
                        track_condition
                    )
                    
                    if mismatch_penalty > 0.5:
                        degradation_multiplier = 1.0 + (mismatch_penalty / 10.0)
                        nu = nu * degradation_multiplier
                    
                    mu_pred_temp = mu_alpha + nu
                    var_pred = var_alpha + proc_var
                    
                    expected_lap = (
                        mu_pred_temp +
                        self.fuel_effect * fuel +
                        mismatch_penalty
                    )
                    
                    innovation = lap_time - expected_lap
                    innovation_var = var_pred + obs_var
                    kalman_gain = var_pred / innovation_var
                    
                    effective_nu = nu * (1 - kalman_gain)
                    mu_pred = mu_alpha + effective_nu
                    
                    mu_alpha = mu_pred + kalman_gain * innovation
                    var_alpha = (1.0 - kalman_gain) * var_pred
                
                states.append(mu_alpha)
                variances.append(var_alpha)
            
            self._latent_states[driver] = states
            self._latent_uncertainty[driver] = variances
    
    def _compute_warmup_penalty(self, tyre: TyreProfile, lap_on_tyre: int) -> float:
        if not self.config.enable_warmup or lap_on_tyre > tyre.warmup_laps:
            return 0.0
        
        warmup_penalties = {
            TyreCategory.SLICK: 0.3,
            TyreCategory.INTER: 0.2,
            TyreCategory.WET: 0.15
        }
        
        max_penalty = warmup_penalties.get(tyre.category, 0.2)
        
        if tyre.warmup_laps > 0:
            penalty = max_penalty * (1 - (lap_on_tyre - 1) / tyre.warmup_laps)
        else:
            penalty = 0.0
        
        return penalty
    
    def predict_next_lap(
        self,
        driver: str,
        current_lap: int,
        laps_df: pd.DataFrame,
        track_condition: Optional[str] = None
    ) -> Tuple[float, float, Dict]:
        if not self._fitted:
            raise RuntimeError("Model must be fitted before prediction")
        
        driver_laps = laps_df[
            (laps_df['Driver'] == driver) &
            (laps_df['LapNumber'] <= current_lap)
        ].sort_values('LapNumber')
        
        if driver_laps.empty:
            return None, None, {}
        
        last_lap = driver_laps.iloc[-1]
        compound = last_lap['Compound']
        stint = last_lap['Stint']
        
        if compound not in self.tyre_profiles:
            print(f"Warning: Unknown compound '{compound}'")
            return None, None, {}
        
        tyre = self.tyre_profiles[compound]
        
        stint_laps = driver_laps[driver_laps['Stint'] == stint]
        laps_on_tyre = len(stint_laps)
        
        abrasion_factor = self.track_abrasion
        if tyre.category == TyreCategory.WET:
            abrasion_factor = 1.0 + 0.3 * (self.track_abrasion - 1.0)
        
        effective_degradation = tyre.degradation_rate * abrasion_factor
        
        if laps_on_tyre == 1:
            alpha_t = tyre.reset_pace
        else:
            alpha_t = tyre.reset_pace + (laps_on_tyre - 1) * effective_degradation
        
        warmup_penalty = self._compute_warmup_penalty(tyre, laps_on_tyre)
        alpha_t = alpha_t + warmup_penalty
        
        next_lap = current_lap + 1
        fuel_next = max(
            0,
            self.config.starting_fuel - (next_lap - 1) * self.config.fuel_burn_rate
        )
        
        if track_condition is None:
            track_condition = last_lap.get('TrackCondition', 'DRY')
        
        mismatch_penalty = self._compute_mismatch_penalty(compound, track_condition)
        
        predicted_time = alpha_t + self.fuel_effect * fuel_next + mismatch_penalty
        
        if driver in self._latent_uncertainty and self._latent_uncertainty[driver]:
            var_alpha = self._latent_uncertainty[driver][-1]
        else:
            var_alpha = self.sigma_eta ** 2
        
        std_dev = np.sqrt(var_alpha + self.sigma_epsilon ** 2)
        
        max_laps = tyre.max_degradation / max(effective_degradation, 0.001)
        
        if mismatch_penalty > 0.5:
            effective_laps = laps_on_tyre * (1.0 + mismatch_penalty / 5.0)
        else:
            effective_laps = laps_on_tyre
        
        health = max(0, min(100, 100 * (1 - effective_laps / max_laps)))
        
        info = {
            'latent_pace': alpha_t,
            'predicted_time': predicted_time,
            'std_dev': std_dev,
            'health': int(health),
            'laps_on_tyre': laps_on_tyre,
            'compound': compound,
            'category': tyre.category.value,
            'degradation_rate': tyre.degradation_rate,
            'effective_degradation': effective_degradation,  
            'track_abrasion': self.track_abrasion,  
            'mismatch_penalty': mismatch_penalty,
            'track_condition': track_condition,
            'confidence_95': (
                predicted_time - 1.96 * std_dev,
                predicted_time + 1.96 * std_dev
            )
        }
        
        return predicted_time, std_dev, info
    
    def get_degradation_rate(self, compound: str) -> float:
        """Get current degradation rate for compound."""
        if compound not in self.tyre_profiles:
            return 0.05
        return self.tyre_profiles[compound].degradation_rate
    
    def get_health(
        self,
        driver: str,
        current_lap: int,
        laps_df: pd.DataFrame,
        track_condition: Optional[str] = None
    ) -> Dict:
        """Get tyre health information."""
        _, _, info = self.predict_next_lap(
            driver,
            current_lap,
            laps_df,
            track_condition
        )
        
        if not info:
            return None
        
        return {
            'compound': info['compound'],
            'category': info['category'],
            'laps_on_tyre': info['laps_on_tyre'],
            'health': info['health'],
            'expected_delta': info['effective_degradation'] * info['laps_on_tyre'],
            'actual_delta': 0.0,
            'overdriving': False,
            'uncertainty': info['std_dev'],
            'latent_pace': info['latent_pace'],
            'mismatch_penalty': info['mismatch_penalty'],
            'track_condition': info['track_condition'],
            'track_abrasion': info['track_abrasion']  
        }