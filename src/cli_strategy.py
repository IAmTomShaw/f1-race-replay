"""CLI for testing the Strategy Analyst with race data.

Provides both live strategy recommendations and post-race evaluation
to complete the reason → act → evaluate loop.
"""
import sys
import argparse
import json

sys.path.append('.')

from src.f1_data import load_session, enable_cache
from src.strategy_analyzer import (
    ask_strategy_agent,
    evaluate_strategy_outcome,
    extract_strategy_context,
    StrategyEvaluation
)


def print_recommendation(rec, show_json=False):
    """Pretty print strategy recommendation."""
    print(f"\n{'─'*50}")
    print(f"  RECOMMENDATION: {rec.action.upper()}")
    print(f"{'─'*50}")
    print(f"Confidence:  {rec.confidence:.0%}")
    print(f"Reasoning:   {rec.reasoning}")

    if rec.factors:
        print(f"\nKey Factors:")
        for factor in rec.factors:
            print(f"  • {factor}")

    if rec.uncertainties:
        print(f"\nUncertainties:")
        for unc in rec.uncertainties:
            print(f"  ⚠ {unc}")

    # Confidence bar
    confidence_bar = "█" * int(rec.confidence * 20)
    print(f"\nConfidence: [{confidence_bar:<20}]")

    if show_json:
        print(f"\nFull JSON (for audit/analysis):")
        print(rec.to_json())


def print_evaluation(evaluation: StrategyEvaluation, driver_code: str, recommended_action: str):
    """Pretty print strategy outcome evaluation."""
    print(f"\n{'='*50}")
    print("  POST-RACE EVALUATION")
    print(f"{'='*50}")
    print(f"Driver:            {driver_code}")
    print(f"Recommended:       {recommended_action}")
    print(f"Final position:    {evaluation.final_position}")
    print(f"Position delta:    {'+' if evaluation.position_delta >= 0 else ''}{evaluation.position_delta}")
    print(f"Outcome:           {evaluation.outcome.value}")
    print(f"\nJustification:")
    print(f"  {evaluation.justification}")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(
        description='F1 Strategy Analyst - LLM-based race strategy recommendations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get live strategy recommendation
  python cli_strategy.py --year 2024 --round 12 --driver VER --lap 30

  # Analyze with specific question
  python cli_strategy.py --year 2024 --round 12 --driver VER --lap 30 \\
    --question "Is the undercut feasible?"

  # Post-race evaluation
  python cli_strategy.py --year 2024 --round 12 --driver VER --lap 30 \\
    --evaluate --actual-pit-lap 32

  # Show full JSON output
  python cli_strategy.py --year 2024 --round 12 --driver VER --lap 30 --json
        """
    )

    parser.add_argument('--year', type=int, default=2024, help='Race year')
    parser.add_argument('--round', type=int, required=True, help='Race round number')
    parser.add_argument('--driver', type=str, default='VER', help='Driver code (e.g., VER, HAM, LEC)')
    parser.add_argument('--lap', type=int, required=True, help='Lap number to analyze')
    parser.add_argument('--question', type=str,
                       default='Should we pit now or stay out?',
                       help='Strategy question to ask')
    parser.add_argument('--model', type=str, default='llama3.2',
                       help='Ollama model to use (default: llama3.2)')
    parser.add_argument('--session', type=str, default='R',
                       choices=['R', 'S', 'Q'],
                       help='Session type: R=Race, S=Sprint, Q=Qualifying')
    parser.add_argument('--json', action='store_true',
                       help='Output full JSON for audit/analysis')
    parser.add_argument('--evaluate', action='store_true',
                       help='Run post-race evaluation (requires --actual-pit-lap)')
    parser.add_argument('--actual-pit-lap', type=int,
                       help='Actual lap the driver pitted (for evaluation)')

    args = parser.parse_args()

    # Enable FastF1 cache
    enable_cache()

    print(f"\n{'='*50}")
    print("  F1 STRATEGY ANALYST")
    print(f"{'='*50}")
    print(f"Loading {args.year} Round {args.round} {args.session} session...")
    print(f"Driver: {args.driver} | Lap: {args.lap}")
    print(f"Model: {args.model}")
    print(f"{'='*50}\n")

    # Load session
    try:
        session = load_session(args.year, args.round, args.session)
        print(f"Session loaded: {session}\n")
    except Exception as e:
        print(f"Error loading session: {e}")
        sys.exit(1)

    # Show current context
    context = extract_strategy_context(session, args.driver, args.lap)
    print("Current Race Context:")
    print(f"  Position:    {context['position']}")
    print(f"  Tyre:        {context['compound']} (Age: {context['tyre_age']} laps)")
    print(f"  Stint:       {context['stint_length']} laps")
    print(f"  Gap ahead:   {context['gap_ahead']} ({context['driver_ahead']})")
    print(f"  Pace trend:  {context['pace_trend']}")
    print(f"  Laps remain: {context['laps_remaining']}")

    if context.get('uncertainties'):
        print(f"\n  Known limitations:")
        for unc in context['uncertainties']:
            print(f"    ⚠ {unc}")
    print()

    # Get strategy recommendation
    print(f"\nQuestion: {args.question}")
    print("-" * 50)

    rec = ask_strategy_agent(
        session=session,
        driver_code=args.driver,
        lap_number=args.lap,
        question=args.question,
        model=args.model
    )

    print_recommendation(rec, show_json=args.json)

    # Post-race evaluation
    if args.evaluate:
        if args.actual_pit_lap:
            print("\nRunning post-race evaluation...")
            evaluation = evaluate_strategy_outcome(
                session=session,
                driver_code=args.driver,
                recommendation=rec,
                actual_pit_lap=args.actual_pit_lap
            )
            print_evaluation(evaluation, args.driver, rec.action)
        else:
            print("\n⚠ Evaluation requested but --actual-pit-lap not provided.")
            print("  Run with --actual-pit-lap N to specify when the driver actually pitted.")

    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
