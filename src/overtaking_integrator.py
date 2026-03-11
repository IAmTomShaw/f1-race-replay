"""
overtaking_integrator.py
Wraps the trained XGBoost overtaking classifier for use in the replay tool.

Follows the same pattern as TyreDegradationIntegrator:
  - load model once at init
  - initialize_from_session() builds lap-data lookups (compound, tyre_life)
    because the live stream does NOT send these fields per driver
  - get_overtake_probability() is the per-frame interface
  - results are cached by (behind, ahead, lap) to avoid re-running the model
    on the same lap multiple times
"""

import joblib
import json
import pandas as pd
from typing import Optional, Dict, Tuple


# Compound name → integer mapping (must match training encoding)
_DEFAULT_COMPOUND_MAP = {"SOFT": 0, "MEDIUM": 1, "HARD": 2}

# DRS detection threshold — ~1.0s at race speeds (~80m at 290 km/h)
DRS_WINDOW_S = 1.0


class OvertakingIntegrator:

    def __init__(self, model_path: str, compound_map_path: Optional[str] = None):
        """
        Load the trained overtaking model.

        Args:
            model_path:        path to overtaking_model.pkl
            compound_map_path: path to compound_map.json (optional — uses
                               default SOFT/MEDIUM/HARD map if not provided)
        """
        self._model = joblib.load(model_path)
        self._initialized = False
        self._cache: Dict[str, float] = {}

        # Compound map: {"SOFT": 0, "MEDIUM": 1, "HARD": 2}
        if compound_map_path:
            with open(compound_map_path) as f:
                self._compound_map = json.load(f)
        else:
            self._compound_map = _DEFAULT_COMPOUND_MAP

        # Lap data lookup built from session.laps at init time:
        # {(driver_code, lap_number): (compound_encoded, tyre_life)}
        self._lap_lookup: Dict[Tuple[str, int], Tuple[int, int]] = {}

    # ── Session initialisation ────────────────────────────────────────────

    def initialize_from_session(self, session) -> bool:
        """
        Build compound + tyre_life lookup from FastF1 session.laps.

        Must be called once before get_overtake_probability().
        The live stream does not send compound or tyre_life per driver —
        we read them from the laps DataFrame instead, exactly as
        TyreDegradationIntegrator does.

        Args:
            session: FastF1 session object (already loaded)

        Returns:
            True if successful, False on error.
        """
        try:
            laps = session.laps
            if laps is None or laps.empty:
                print("OvertakingIntegrator: empty laps DataFrame")
                return False

            built = 0
            for _, row in laps.iterrows():
                driver   = row.get("Driver")
                lap_num  = row.get("LapNumber")
                compound = row.get("Compound")
                tyre_life = row.get("TyreLife")

                if driver is None or lap_num is None:
                    continue
                if compound is None or tyre_life is None:
                    continue

                compound_enc = self._compound_map.get(str(compound).upper(), 0)
                try:
                    tyre_life_int = int(tyre_life)
                    lap_num_int   = int(lap_num)
                except (ValueError, TypeError):
                    continue

                self._lap_lookup[(driver, lap_num_int)] = (compound_enc, tyre_life_int)
                built += 1

            print(f"OvertakingIntegrator: built lap lookup for {built} lap rows")
            self._initialized = True
            return True

        except Exception as e:
            print(f"OvertakingIntegrator initialization error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_overtake_probability_from_frame(
        self,
        behind_driver: str,
        ahead_driver:  str,
        behind_data:   dict,
        ahead_data:    dict,
        gap_s:         float,
        lap:           int,
        position:      int,
    ) -> float:
        """
        Preferred entry point — reads compound + tyre_life directly from
        the frame dict (populated by race_replay.py's augmented broadcast).
        Falls back to lap lookup if the stream fields are missing.
        """
        # Try frame data first (populated when degradation integrator is running)
        behind_compound = self._compound_map.get(
            str(behind_data.get("compound", "")).upper(),
            self._lap_lookup.get((behind_driver, lap), (1, 15))[0]
        )
        behind_default_tyre = self._lap_lookup.get((behind_driver, lap), (1, 15))[1]
        behind_tyre_raw = behind_data.get("tyre_life")
        try:
            if behind_tyre_raw is None or behind_tyre_raw == "":
                behind_tyre = behind_default_tyre
            else:
                behind_tyre = int(behind_tyre_raw)
        except (ValueError, TypeError):
            behind_tyre = behind_default_tyre

        ahead_compound = self._compound_map.get(
            str(ahead_data.get("compound", "")).upper(),
            self._lap_lookup.get((ahead_driver, lap), (1, 15))[0]
        )
        ahead_default_tyre = self._lap_lookup.get((ahead_driver, lap), (1, 15))[1]
        ahead_tyre_raw = ahead_data.get("tyre_life")
        try:
            if ahead_tyre_raw is None or ahead_tyre_raw == "":
                ahead_tyre = ahead_default_tyre
            else:
                ahead_tyre = int(ahead_tyre_raw)
        except (ValueError, TypeError):
            ahead_tyre = ahead_default_tyre

        tyre_delta = ahead_tyre - behind_tyre
        cache_key  = f"{behind_driver}_{ahead_driver}_{lap}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        features = pd.DataFrame([{
            "GapAhead":             gap_s,
            "TyreDelta":            tyre_delta,
            "CompoundEncoded":      behind_compound,
            "CompoundAheadEncoded": ahead_compound,
            "TyreLife":             behind_tyre,
            "TyreLifeAhead":        ahead_tyre,
            "LapNumber":            lap,
            "Position":             position,
        }])

        try:
            prob = float(self._model.predict_proba(features)[0][1])
        except Exception as e:
            print(f"OvertakingIntegrator: predict failed — {e}")
            prob = 0.0

        self._cache[cache_key] = prob
        return prob


    # ── Per-frame interface ───────────────────────────────────────────────

    def get_overtake_probability(
        self,
        behind_driver: str,
        ahead_driver:  str,
        gap_s:         float,
        lap:           int,
        position:      int,
    ) -> float:
        """
        Return probability (0–1) of an overtake occurring this lap.

        Compound and tyre_life are looked up from session.laps (built at
        init time) because the live stream does not provide them per frame.

        Result is cached by (behind, ahead, lap) — the model only needs to
        run once per pair per lap since the inputs don't change mid-lap.

        Args:
            behind_driver: 3-letter code of the following car  (e.g. "LEC")
            ahead_driver:  3-letter code of the car in front   (e.g. "VER")
            gap_s:         time gap in seconds (approximated from distance)
            lap:           current lap number
            position:      on-track position of the car behind

        Returns:
            float in [0, 1]
        """
        cache_key = f"{behind_driver}_{ahead_driver}_{lap}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Look up compound + tyre_life for both drivers on this lap.
        # These come from session.laps — loaded via initialize_from_session().
        #
        # KNOWN LIMITATION: insight panels run as separate processes connected
        # only by the TCP telemetry stream. The stream does not currently
        # broadcast compound or tyre_life per driver. If initialize_from_session()
        # was not called (or the lookup misses), we fall back to neutral mid-race
        # values so the panel still shows gap-based probability rather than crashing.
        #
        # Proposed fix (for PR follow-up): add year/round/session_type to the
        # stream broadcast so insight panels can load FastF1 data themselves.
        behind_compound, behind_tyre = self._lap_lookup.get(
            (behind_driver, lap), (1, 15)   # fallback: MEDIUM, 15 laps
        )
        ahead_compound, ahead_tyre = self._lap_lookup.get(
            (ahead_driver, lap), (1, 15)
        )

        tyre_delta = ahead_tyre - behind_tyre

        features = pd.DataFrame([{
            "GapAhead":             gap_s,
            "TyreDelta":            tyre_delta,
            "CompoundEncoded":      behind_compound,
            "CompoundAheadEncoded": ahead_compound,
            "TyreLife":             behind_tyre,
            "TyreLifeAhead":        ahead_tyre,
            "LapNumber":            lap,
            "Position":             position,
        }])

        try:
            prob = float(self._model.predict_proba(features)[0][1])
        except Exception as e:
            print(f"OvertakingIntegrator: predict failed for {behind_driver}/{ahead_driver} lap {lap}: {e}")
            prob = 0.0

        self._cache[cache_key] = prob
        return prob

    def is_in_drs_range(self, gap_s: float) -> bool:
        """True if gap is within DRS activation threshold."""
        return 0.0 < gap_s <= DRS_WINDOW_S

    def clear_cache(self):
        """Clear prediction cache — call between sessions."""
        self._cache.clear()