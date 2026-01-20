"""Strategy Analyst - LLM-based race strategy recommendations using Ollama.

This module provides auditable, fact-based strategy recommendations using local LLMs.
Designed to prevent hallucination by enforcing strict context boundaries.

The system is designed as a decision-support agent with:
- Controlled vocabulary for factors and uncertainties
- Structured, auditable JSON outputs
- Post-race evaluation loop (reason → act → evaluate)
"""
import json
from typing import Dict, Any, List, Literal
from dataclasses import dataclass, asdict
from enum import Enum

try:
    import ollama
except ImportError:
    ollama = None
    print("Warning: ollama not installed. Run: pip install ollama")

import pandas as pd


# ============================================================================
# CONTROLLED VOCABULARY - Prevents LLM from inventing categories
# ============================================================================

class StrategyFactor(str, Enum):
    """Controlled vocabulary for strategy factors."""
    TYRE_AGE_HIGH = "tyre_age_high"
    TYRE_AGE_LOW = "tyre_age_low"
    STINT_LONG = "stint_long"
    STINT_SHORT = "stint_short"
    PACE_IMPROVING = "pace_improving"
    PACE_DEGRADING = "pace_degrading"
    PACE_STABLE = "pace_stable"
    GAP_SUFFICIENT = "gap_sufficient"
    GAP_INSUFFICIENT = "gap_insufficient"
    POSITION_SAFE = "position_safe"
    POSITION_AT_RISK = "position_at_risk"
    LAPS_REMAINING_HIGH = "laps_remaining_high"
    LAPS_REMAINING_LOW = "laps_remaining_low"
    TRAFFIC_AHEAD = "traffic_ahead"
    CLEAR_TRACK = "clear_track"


class StrategyUncertainty(str, Enum):
    """Controlled vocabulary for known uncertainties."""
    TRACK_CONDITION_UNKNOWN = "track_condition_unknown"
    WEATHER_UNKNOWN = "weather_unknown"
    WEATHER_EVOLUTION_UNKNOWN = "weather_evolution_unknown"
    TYRE_ALLOCATION_UNKNOWN = "tyre_allocation_unknown"
    TYRE_PERFORMANCE_UNKNOWN = "tyre_performance_unknown"
    PACE_TREND_UNKNOWN = "pace_trend_unknown"
    COMPETITOR_STRATEGY_UNKNOWN = "competitor_strategy_unknown"
    GAP_ESTIMATE_UNRELIABLE = "gap_estimate_unreliable"


class StrategyAction(str, Enum):
    """Valid strategy actions."""
    PIT_NOW = "pit_now"
    STAY_OUT = "stay_out"
    BOX_LAP = "box_lap"
    PUSH = "push"
    DEFEND = "defend"


class OutcomeType(str, Enum):
    """Post-race outcome classification."""
    OPTIMAL = "OPTIMAL"          # Podium finish
    ACCEPTABLE = "ACCEPTABLE"    # Points finish (4-10)
    SUBOPTIMAL = "SUBOPTIMAL"    # No points (11+)


# Map enum values to display names for LLM prompt
FACTOR_DESCRIPTIONS = {
    "tyre_age_high": "Tyre is old (20+ laps)",
    "tyre_age_low": "Tyre is fresh (<5 laps)",
    "stint_long": "Current stint is long (15+ laps)",
    "stint_short": "Current stint is short (<10 laps)",
    "pace_improving": "Lap times improving",
    "pace_degrading": "Lap times degrading",
    "pace_stable": "Lap times stable",
    "gap_sufficient": "Safe gap to car behind",
    "gap_insufficient": "Small gap to car behind",
    "position_safe": "Track position secure",
    "position_at_risk": "Track position under threat",
    "laps_remaining_high": "Many laps left (20+)",
    "laps_remaining_low": "Few laps left (<10)",
    "traffic_ahead": "Traffic ahead on track",
    "clear_track": "Clear track ahead",
}

UNCERTAINTY_DESCRIPTIONS = {
    "track_condition_unknown": "Current track condition (wet/dry/damp) unknown",
    "weather_unknown": "Current weather unknown",
    "weather_evolution_unknown": "How weather will change unknown",
    "tyre_allocation_unknown": "How many tyre sets available unknown",
    "tyre_performance_unknown": "Tyre degradation rate unknown",
    "pace_trend_unknown": "Whether pace is improving/degrading unknown",
    "competitor_strategy_unknown": "What competitors will do unknown",
    "gap_estimate_unreliable": "Gap to other cars uncertain",
}


# Build allowed lists for LLM prompt
ALLOWED_FACTORS = "\n".join([f"  - {k}: {v}" for k, v in FACTOR_DESCRIPTIONS.items()])
ALLOWED_UNCERTAINTIES = "\n".join([f"  - {k}: {v}" for k, v in UNCERTAINTY_DESCRIPTIONS.items()])


@dataclass
class StrategyRecommendation:
    """Structured, auditable strategy recommendation."""
    action: str  # StrategyAction or "ERROR" for system errors
    confidence: float  # 0.0-1.0
    reasoning: str
    factors: List[str]  # StrategyFactor values or error indicators
    uncertainties: List[str]  # StrategyUncertainty values or error indicators
    raw_response: str  # For debugging/audit trail

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class StrategyEvaluation:
    """Post-race strategy outcome evaluation."""
    outcome: OutcomeType
    final_position: int
    position_delta: int  # Position change from recommendation point
    justification: str  # Human-readable explanation of outcome classification

    def to_dict(self) -> Dict:
        """Convert to dictionary with enum value as string."""
        data = asdict(self)
        data['outcome'] = self.outcome.value if isinstance(self.outcome, OutcomeType) else self.outcome
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def extract_strategy_context(session: Any, driver_code: str, lap_number: int) -> Dict[str, Any]:
    """Extract current race situation for a driver at a specific lap.

    Args:
        session: FastF1 Session object
        driver_code: Driver abbreviation (e.g., 'VER', 'HAM')
        lap_number: Lap number to analyze

    Returns:
        Dictionary with driver context including position, tyre, stint info
    """
    laps = session.laps.pick_drivers(driver_code)

    if laps.empty:
        return {
            "driver": driver_code,
            "lap": lap_number,
            "position": 0,
            "compound": "UNKNOWN",
            "tyre_age": 0,
            "stint_length": 0,
            "total_laps": session.total_laps if hasattr(session, 'total_laps') else 0,
            "gap_ahead": "N/A",
            "driver_ahead": "N/A",
            "available_facts": "Limited - no lap data",
        }

    # Get current stint info
    current_lap_data = laps[laps['LapNumber'] == lap_number]
    if current_lap_data.empty:
        # Find closest lap
        closest_lap = laps.iloc[(laps['LapNumber'] - lap_number).abs().argsort()[:1]]
        stint = closest_lap['Stint'].iloc[0] if not closest_lap.empty else 1
    else:
        stint = current_lap_data['Stint'].iloc[-1]

    stint_laps = laps[laps['Stint'] == stint]

    # Get compound and tyre age
    compound = stint_laps['Compound'].iloc[-1] if not stint_laps.empty else "UNKNOWN"

    if 'TyreLife' in stint_laps.columns and not stint_laps['TyreLife'].isna().all():
        tyre_life = stint_laps['TyreLife'].iloc[-1]
    else:
        tyre_life = len(stint_laps)

    # Get position
    if not current_lap_data.empty and 'Position' in current_lap_data.columns:
        position = int(current_lap_data['Position'].iloc[-1])
    elif 'Position' in stint_laps.columns:
        position = int(stint_laps['Position'].iloc[-1])
    else:
        position = 0

    # Calculate recent pace trend (last 3 laps in current stint)
    pace_trend = "UNKNOWN"
    if len(stint_laps) >= 4 and 'LapTime' in stint_laps.columns:
        recent_laps = stint_laps.tail(4)['LapTime'].dropna()
        if len(recent_laps) >= 3:
            # Compare last lap to average of previous 3
            last_lap = recent_laps.iloc[-1].total_seconds()
            prev_avg = recent_laps.iloc[:-1].mean().total_seconds()
            if last_lap < prev_avg - 0.5:
                pace_trend = "IMPROVING"
            elif last_lap > prev_avg + 0.5:
                pace_trend = "DEGRADING"
            else:
                pace_trend = "STABLE"

    # Calculate gap to car ahead
    gap_ahead = "N/A"
    driver_ahead = "N/A"

    if not current_lap_data.empty and 'Time' in current_lap_data.columns:
        current_time = current_lap_data['Time'].iloc[-1]
        if pd.notna(current_time):
            all_laps_at_current = session.laps[session.laps['LapNumber'] == lap_number]
            if not all_laps_at_current.empty and 'Time' in all_laps_at_current.columns:
                all_laps_at_current = all_laps_at_current.dropna(subset=['Time'])
                all_laps_at_current = all_laps_at_current.sort_values('Time')

                current_idx = all_laps_at_current[all_laps_at_current['Driver'] == driver_code].index
                if not current_idx.empty:
                    pos_in_list = all_laps_at_current.index.get_loc(current_idx[0])

                    # Car ahead (better position)
                    if pos_in_list > 0:
                        ahead_row = all_laps_at_current.iloc[pos_in_list - 1]
                        if 'Driver' in ahead_row:
                            driver_ahead = ahead_row['Driver']
                            time_diff = (current_time - ahead_row['Time']).total_seconds()
                            if time_diff > 0:
                                gap_ahead = f"+{time_diff:.3f}"

    # Explicitly state what we DON'T know
    uncertainties = []
    if not hasattr(session, 'weather_data') or session.weather_data is None:
        uncertainties.append("current_weather_unknown")
    if pace_trend == "UNKNOWN":
        uncertainties.append("pace_trend_unknown")

    return {
        "driver": driver_code,
        "lap": lap_number,
        "position": position,
        "compound": str(compound),
        "tyre_age": int(tyre_life),
        "stint_length": len(stint_laps),
        "total_laps": session.total_laps if hasattr(session, 'total_laps') else laps['LapNumber'].max(),
        "gap_ahead": gap_ahead,
        "driver_ahead": driver_ahead,
        "pace_trend": pace_trend,
        "laps_remaining": (session.total_laps if hasattr(session, 'total_laps') else laps['LapNumber'].max()) - lap_number,
        "available_facts": "position, compound, tyre_age, stint_length, gap_ahead, pace_trend",
        "uncertainties": uncertainties,
    }


def ask_strategy_agent(
    session: Any,
    driver_code: str,
    lap_number: int,
    question: str,
    model: str = "llama3.2"
) -> StrategyRecommendation:
    """Query Ollama for strategy recommendation.

    Args:
        session: FastF1 Session object
        driver_code: Driver abbreviation
        lap_number: Current lap number
        question: Strategy question to ask
        model: Ollama model to use (default: llama3.2)

    Returns:
        StrategyRecommendation with structured, auditable output
    """
    if ollama is None:
        return StrategyRecommendation(
            action="ERROR",
            confidence=0.0,
            reasoning="ollama package not installed. Run: pip install ollama",
            factors=[],
            uncertainties=["ollama_not_available"],
            raw_response="",
        )

    context = extract_strategy_context(session, driver_code, lap_number)

    # Build explicit fact list to prevent hallucination
    fact_list = "\n".join([
        f"- Driver: {context['driver']} (Position {context['position']})",
        f"- Lap: {context['lap']} / {context['total_laps']} ({context['laps_remaining']} laps remaining)",
        f"- Tyre: {context['compound']} (Age: {context['tyre_age']} laps)",
        f"- Stint length: {context['stint_length']} laps",
        f"- Gap ahead: {context['gap_ahead']} ({context['driver_ahead']})",
        f"- Pace trend: {context['pace_trend']}",
    ])

    uncertainty_list = "\n".join([f"- {u}" for u in context.get('uncertainties', [])])

    prompt = f"""You are an F1 race strategist. Analyze the provided race data and provide a recommendation.

=== AVAILABLE FACTS (use ONLY these) ===
{fact_list}

=== KNOWN UNCERTAINTIES ===
{uncertainty_list if uncertainty_list else "- None"}

=== CRITICAL CONSTRAINTS ===
IMPORTANT: Use ONLY the information explicitly provided above.
- Do NOT assume track conditions (wet/dry/evolving) unless stated
- Do NOT assume tyre performance characteristics beyond the given data
- Do NOT invent gap values or pace information
- If information is missing to answer confidently, state it in uncertainties

=== ALLOWED FACTORS (choose from these only) ===
{ALLOWED_FACTORS}

=== ALLOWED UNCERTAINTIES (choose from these only) ===
{ALLOWED_UNCERTAINTIES}

Question: {question}

=== RESPONSE FORMAT (JSON only) ===
Respond with valid JSON only, no markdown, no explanation outside JSON:
{{
  "action": "pit_now" | "stay_out" | "box_lap" | "push" | "defend",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation based ONLY on provided facts",
  "factors": ["factor_key_1", "factor_key_2"],
  "uncertainties": ["uncertainty_key_1"]
}}

Action definitions:
- pit_now: Recommend pitting immediately this lap
- stay_out: Recommend staying out on current tyres
- box_lap: Recommend pitting in 1-2 laps
- push: Recommend pushing current pace
- defend: Recommend defensive driving

Your JSON response:"""

    try:
        response = ollama.generate(model=model, prompt=prompt)
        raw = response['response'].strip()

        # Extract JSON from response (handle markdown code blocks)
        json_str = raw
        if '```' in raw:
            # Extract from code block
            start = raw.find('{')
            end = raw.rfind('}') + 1
            if start >= 0 and end > start:
                json_str = raw[start:end]

        # Parse JSON
        try:
            data = json.loads(json_str)
            return StrategyRecommendation(
                action=data.get('action', 'UNKNOWN'),
                confidence=float(data.get('confidence', 0.0)),
                reasoning=data.get('reasoning', ''),
                factors=data.get('factors', []),
                uncertainties=data.get('uncertainties', []),
                raw_response=raw,
            )
        except json.JSONDecodeError:
            # Fallback: try to parse old format
            return _parse_fallback_format(raw)

    except Exception as e:
        return StrategyRecommendation(
            action="ERROR",
            confidence=0.0,
            reasoning=f"LLM error: {str(e)}",
            factors=[],
            uncertainties=["llm_error"],
            raw_response="",
        )


def _parse_fallback_format(response: str) -> StrategyRecommendation:
    """Parse old pipe-delimited format as fallback."""
    parts = [p.strip() for p in response.split('|')]

    if len(parts) >= 3:
        try:
            confidence = float(parts[1])
        except ValueError:
            confidence = 0.5

        return StrategyRecommendation(
            action=parts[0],
            confidence=confidence,
            reasoning='|'.join(parts[2:]).strip(),
            factors=[],
            uncertainties=["fallback_parse"],
            raw_response=response,
        )
    else:
        return StrategyRecommendation(
            action="UNKNOWN",
            confidence=0.0,
            reasoning=response,
            factors=[],
            uncertainties=["parse_failed"],
            raw_response=response,
        )


def evaluate_strategy_outcome(
    session: Any,
    driver_code: str,
    recommendation: StrategyRecommendation,
    actual_pit_lap: int
) -> StrategyEvaluation:
    """Evaluate if the strategy was optimal given the actual outcome.

    This completes the reason → act → evaluate loop.

    Args:
        session: FastF1 Session object
        driver_code: Driver abbreviation
        recommendation: The recommendation that was (or would have been) made
        actual_pit_lap: The lap the driver actually pitted (if they did)

    Returns:
        StrategyEvaluation with outcome assessment and justification
    """
    laps = session.laps.pick_drivers(driver_code)
    if laps.empty:
        return StrategyEvaluation(
            outcome=OutcomeType.SUBOPTIMAL,
            final_position=99,
            position_delta=0,
            justification="No lap data available for evaluation",
        )

    final_position = int(laps['Position'].iloc[-1]) if 'Position' in laps.columns else 0

    # Get position at recommendation time for delta calculation
    rec_lap_data = laps[laps['LapNumber'] == recommendation.confidence]  # Using confidence as lap placeholder
    if rec_lap_data.empty and 'Position' in laps.columns:
        position_at_rec = int(laps.iloc[0]['Position'])  # Fallback to first lap
    else:
        position_at_rec = final_position

    position_delta = position_at_rec - final_position  # Negative = improved

    # Get pit stops
    pit_laps = []
    for _, lap in laps.iterrows():
        if pd.notna(lap.get('PitInTime')):
            pit_laps.append(int(lap['LapNumber']))

    # Classify outcome
    if final_position <= 3:
        outcome = OutcomeType.OPTIMAL
        justification = f"Podium finish (P{final_position}). "
    elif final_position <= 10:
        outcome = OutcomeType.ACCEPTABLE
        justification = f"Points finish (P{final_position}). "
    else:
        outcome = OutcomeType.SUBOPTIMAL
        justification = f"No points (P{final_position}). "

    # Add context about position change
    if position_delta > 0:
        justification += f"Gained {position_delta} positions since recommendation."
    elif position_delta < 0:
        justification += f"Lost {-position_delta} positions since recommendation."
    else:
        justification += "Position maintained."

    # Add strategy execution note
    if actual_pit_lap and actual_pit_lap in pit_laps:
        justification += f" Recommendation followed (pitted lap {actual_pit_lap})."
    elif actual_pit_lap:
        justification += f" Recommendation NOT followed (pitted lap {actual_pit_lap} vs different strategy)."

    return StrategyEvaluation(
        outcome=outcome,
        final_position=final_position,
        position_delta=position_delta,
        justification=justification,
    )
