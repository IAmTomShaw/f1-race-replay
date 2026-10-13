"""Read the replay's computed positions at the moments the official ones are measured.

The official ``Position`` for lap N is taken when the driver crosses the line at
the end of lap N. In the replay, that is the first frame where the driver's
``lap`` value reaches N+1. We read the replay position slightly after that frame
(``offset_s``) so that rounding noise right on the line does not decide the result.
"""

from typing import Callable, Optional

import numpy as np
import pandas as pd

from src.eval.ground_truth import label_segments

PositionFn = Callable[[dict], dict]

COMPUTED_COLUMNS = ["driver", "lap", "computed_pos", "frame_idx", "method"]


def driver_codes(frames: list) -> list:
    """Every driver code that appears in at least one frame, sorted."""
    codes = set()
    for frame in frames:
        codes.update(frame.get("drivers", {}).keys())
    return sorted(codes)


def find_lap_crossings(frames: list, driver: str) -> dict:
    """Map lap N to the index of the first frame where the driver's lap is >= N+1.

    Only laps the driver was actually seen on get a crossing. If the replay jumps
    from lap 3 to lap 5, lap 3 ends at the jump and lap 4 has no crossing.
    Frames without the driver are skipped.
    """
    crossings = {}
    current = None
    for idx, frame in enumerate(frames):
        car = frame.get("drivers", {}).get(driver)
        if car is None or car.get("lap") is None:
            continue
        lap = int(car["lap"])
        if current is None:
            current = lap
        elif lap > current:
            crossings[current] = idx
            current = lap
    return crossings
