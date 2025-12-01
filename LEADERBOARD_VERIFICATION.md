# Leaderboard Verification System

## Overview

This document explains the **leaderboard verification system** that cross-checks final race positions against official race results to correct any inaccuracies caused by flawed telemetry data.

---

## The Problem

The telemetry-based leaderboard occasionally produces incorrect final positions after all chequered flags go out. This is due to:

- **Telemetry data gaps**: Missing or incomplete distance measurements
- **API inconsistencies**: FastF1 classification data doesn't always match official results
- **Timing discrepancies**: Subtle differences in how positions are calculated from telemetry vs. official timing

While these issues are rare, they result in an incorrect final leaderboard display.

---

## The Solution

### Hybrid Verification Approach

The system now uses a **two-stage verification process**:

1. **During Race**: Uses existing hybrid detection (telemetry + FastF1 API) for real-time race replay
2. **After Race**: Cross-checks final leaderboard against **Jolpica F1 API** for official results

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Race Replay (Real-time)                   │
│              FastF1 Telemetry + API Data                    │
│           (Existing hybrid detection system)                │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ▼
              Race Finishes
         All Drivers Processed
                     │
                     ▼
         ┌───────────────────────────┐
         │  LEADERBOARD VERIFICATION │
         │   (Jolpica F1 API Check)  │
         └───────────┬───────────────┘
                     │
                     ▼
              ┌──────────────┐
              │ Jolpica API  │  Official race results
              │  GET /results│  • Final positions
              └──────┬───────┘  • All classifications
                     │
                     ▼
         ┌──────────────────────┐
         │  Position Comparison │
         │  Current vs. Official│
         └──────────┬───────────┘
                     │
                     ▼
         ┌──────────────────────┐
         │ Discrepancies Found? │
         └──────────┬───────────┘
                     │
           ┌─────────┴─────────┐
           │                   │
          YES                 NO
           │                   │
           ▼                   ▼
    Apply Corrections    Display Complete
    Update Leaderboard   ✓ Verification OK
```

---

## Implementation

### Core Algorithm

```python
# 1. Race finishes normally using hybrid detection
if self.race_finished and self.final_positions:
    # Wait until near end to ensure all processing complete
    if self.frame_index >= self.n_frames - 100:
        # Cross-check against Jolpica API
        self.final_positions = verify_and_correct_final_positions(
            self.final_positions,
            self.year,
            self.round_number
        )
```

### Verification Logic

```python
def verify_and_correct_final_positions(current_positions, year, round_number):
    # 1. Fetch official results from Jolpica API
    api_results = fetch_race_results_from_jolpica(year, round_number)

    # 2. Build verified positions map
    verified_positions = {result['code']: result['position'] for result in api_results}

    # 3. Compare and identify discrepancies
    discrepancies = []
    for code in current_positions:
        if current_positions[code] != verified_positions[code]:
            discrepancies.append({
                'driver': code,
                'telemetry_position': current_positions[code],
                'verified_position': verified_positions[code]
            })

    # 4. Report and correct
    if discrepancies:
        print(f"⚠ Found {len(discrepancies)} position discrepancies:")
        for disc in discrepancies:
            print(f"  {disc['driver']}: P{disc['telemetry_position']} → P{disc['verified_position']}")
        return verified_positions  # Use official positions
    else:
        print("✓ Leaderboard verification complete - no discrepancies found!")
        return current_positions  # Keep telemetry positions
```

---

## Jolpica F1 API

The verification system uses the **Jolpica F1 API**, which is the open-source successor to the deprecated Ergast API.

### API Details

- **Endpoint**: `https://api.jolpi.ca/ergast/f1/{year}/{round}/results.json`
- **Rate Limit**: 200 requests per hour (unauthenticated)
- **License**: Apache 2.0
- **Maintained by**: Community volunteers

### Example Response

```json
{
  "MRData": {
    "RaceTable": {
      "Races": [{
        "Results": [
          {"position": "1", "Driver": {"code": "VER"}},
          {"position": "2", "Driver": {"code": "PER"}},
          {"position": "3", "Driver": {"code": "SAI"}}
        ]
      }]
    }
  }
}
```

---

## When Verification Occurs

The verification only runs when:

1. Race has finished (`self.race_finished == True`)
2. Final positions have been calculated (`self.final_positions` exists)
3. Near end of replay (`frame_index >= n_frames - 100`)
4. Year and round number are available
5. Verification hasn't already been performed

This ensures:
- All drivers have been properly processed
- No interruption to real-time replay experience
- Verification happens exactly once per race

---



## Benefits

 **Accuracy**: Final leaderboard always matches official FIA results
 **Transparency**: Console output shows exactly what was corrected
 **Non-intrusive**: Only affects final display, doesn't change real-time replay
 **Automatic**: No user intervention required
 **Reliable**: Uses official API maintained by F1 community

---

## References

- [Jolpica F1 API GitHub](https://github.com/jolpica/jolpica-f1)
- [Jolpica F1 API Tutorial](https://python.plainenglish.io/get-all-the-f1-season-results-in-5-minutes-with-python-jolpica-api-6ec13e6efac5)
- [Ergast API Deprecation Discussion](https://github.com/theOehrly/Fast-F1/discussions/445)

---

*Last Updated: December 2025*
*Author: Ajibola Ganiyu*
