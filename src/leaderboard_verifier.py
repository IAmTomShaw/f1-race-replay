"""
Leaderboard Verification Module

This module cross-checks the final race positions using the Jolpica F1 API
to correct any inaccuracies in the telemetry-derived leaderboard.

The Jolpica F1 API is a free, open-source API that replaces the deprecated Ergast API.
API Endpoint: https://api.jolpi.ca/ergast/f1/
Rate Limit: 200 requests per hour (unauthenticated)
"""

import requests
from typing import Dict, List, Optional


def fetch_race_results_from_jolpica(year: int, round_number: int) -> Optional[List[Dict]]:
    """
    Fetches official race results from the Jolpica F1 API.

    Args:
        year: The F1 season year
        round_number: The race round number in the season

    Returns:
        List of driver results with their official positions, or None if request fails
        Each result contains: {'code': str, 'position': int, 'driver_id': str}
    """
    url = f"https://api.jolpi.ca/ergast/f1/{year}/{round_number}/results.json"

    try:
        print(f"Verifying race results via Jolpica API: {year} Round {round_number}...")
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()

        # Navigate the Jolpica/Ergast API structure
        races = data.get('MRData', {}).get('RaceTable', {}).get('Races', [])

        if not races:
            print("⚠ No race data found in Jolpica API response")
            return None

        race = races[0]
        results = race.get('Results', [])

        if not results:
            print("⚠ No results found in Jolpica API response")
            return None

        # Extract driver codes and positions
        verified_results = []
        for result in results:
            driver = result.get('Driver', {})
            driver_code = driver.get('code', '')
            position_str = result.get('position', '')

            # Parse position (could be integer or string like "R" for retired)
            try:
                position = int(position_str)
            except (ValueError, TypeError):
                # Non-finishing drivers (DNF, DSQ, etc.) - assign high number
                position = 999

            verified_results.append({
                'code': driver_code,
                'position': position,
                'driver_id': driver.get('driverId', ''),
                'status': result.get('status', 'Unknown')
            })

        print(f"✓ Successfully fetched {len(verified_results)} driver results from Jolpica API")
        return verified_results

    except requests.exceptions.RequestException as e:
        print(f"⚠ Failed to fetch race results from Jolpica API: {e}")
        return None
    except (KeyError, IndexError) as e:
        print(f"⚠ Failed to parse Jolpica API response: {e}")
        return None


def verify_and_correct_final_positions(
    current_positions: Dict[str, int],
    year: int,
    round_number: int
) -> Dict[str, int]:
    """
    Cross-checks the current leaderboard against official results from Jolpica API.
    If discrepancies are found, returns the corrected positions.

    Args:
        current_positions: Current positions from telemetry {driver_code: position}
        year: The F1 season year
        round_number: The race round number

    Returns:
        Corrected positions dictionary {driver_code: position}
    """
    # Fetch official results from Jolpica API
    api_results = fetch_race_results_from_jolpica(year, round_number)

    if not api_results:
        print("⚠ Could not verify leaderboard - using telemetry-based positions")
        return current_positions

    # Build verified positions map
    verified_positions = {}
    for result in api_results:
        code = result['code']
        position = result['position']
        verified_positions[code] = position

    # Compare current positions with verified positions
    discrepancies = []
    for code in current_positions:
        if code in verified_positions:
            current_pos = current_positions[code]
            verified_pos = verified_positions[code]

            if current_pos != verified_pos:
                discrepancies.append({
                    'driver': code,
                    'telemetry_position': current_pos,
                    'verified_position': verified_pos
                })

    # Report findings
    if discrepancies:
        print(f"\n⚠ Found {len(discrepancies)} position discrepancies:")
        for disc in discrepancies:
            print(f"  {disc['driver']}: P{disc['telemetry_position']} → P{disc['verified_position']} (corrected)")
        print("✓ Final leaderboard corrected using Jolpica API data\n")
        return verified_positions
    else:
        print("✓ Leaderboard verification complete - no discrepancies found!")
        return current_positions


def should_verify_leaderboard(frames: List[Dict], current_frame_index: int) -> bool:
    """
    Determines if we should verify the leaderboard at this frame.
    Only verify after the race has finished and all drivers have been processed.

    Args:
        frames: List of all race frames
        current_frame_index: Current frame being rendered

    Returns:
        True if verification should be performed
    """
    if current_frame_index < len(frames) - 1:
        return False  # Not at end of race yet

    # Check if race is finished
    current_frame = frames[current_frame_index]
    return current_frame.get('race_finished', False)
