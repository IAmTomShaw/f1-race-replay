from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, Iterable, List, Optional, Tuple


@dataclass
class DriverSnapshot:
    code: str
    position: int
    progress_m: float
    speed_kph: float
    tyre: object
    tyre_life: float
    lap: int
    drs: int


def build_driver_snapshots(frame: dict) -> List[DriverSnapshot]:
    drivers = frame.get("drivers", {}) if frame else {}
    snapshots: List[DriverSnapshot] = []

    for code, info in drivers.items():
        snapshots.append(
            DriverSnapshot(
                code=code,
                position=int(info.get("position", 999)),
                progress_m=float(info.get("dist", 0.0)),
                speed_kph=float(info.get("speed", 0.0)),
                tyre=info.get("tyre", "?"),
                tyre_life=float(info.get("tyre_life", 0.0)),
                lap=int(info.get("lap", 0) or 0),
                drs=int(info.get("drs", 0) or 0),
            )
        )

    snapshots.sort(key=lambda s: (s.position, -s.progress_m, s.code))
    return snapshots


def speed_mps(speed_kph: float) -> float:
    return max(1.0, float(speed_kph) / 3.6)


def drs_state(drs_value: int) -> str:
    if drs_value in (10, 12, 14):
        return "ON"
    if drs_value == 8:
        return "AVAIL"
    return "OFF"


def estimate_gap_seconds(front: DriverSnapshot, back: DriverSnapshot) -> float:
    gap_m = max(0.0, front.progress_m - back.progress_m)
    ref_speed = max(speed_mps(front.speed_kph), speed_mps(back.speed_kph))
    return gap_m / ref_speed


def recent_progress_rate(history: Deque[Tuple[float, float]], window_s: float) -> Optional[float]:
    if len(history) < 2:
        return None

    t_end = history[-1][0]
    eligible = [sample for sample in history if t_end - sample[0] <= window_s]
    if len(eligible) < 2:
        eligible = list(history)[-2:]

    t0, p0 = eligible[0]
    t1, p1 = eligible[-1]
    dt = t1 - t0
    if dt <= 0:
        return None

    return max(0.0, (p1 - p0) / dt)


def equivalent_lap_time(progress_rate_mps: Optional[float], circuit_length_m: Optional[float]) -> Optional[float]:
    if not progress_rate_mps or not circuit_length_m or progress_rate_mps <= 0:
        return None
    return circuit_length_m / progress_rate_mps


def find_virtual_rejoin(
    snapshots: Iterable[DriverSnapshot],
    selected_code: str,
    pit_loss_s: float,
    reference_speed_mps: float,
) -> Optional[dict]:
    ordered = list(snapshots)
    selected = next((snap for snap in ordered if snap.code == selected_code), None)
    if not selected:
        return None

    projected_progress = selected.progress_m - max(0.0, pit_loss_s) * max(1.0, reference_speed_mps)

    ranking: List[Tuple[str, float]] = []
    for snap in ordered:
        progress = projected_progress if snap.code == selected_code else snap.progress_m
        ranking.append((snap.code, progress))

    ranking.sort(key=lambda item: item[1], reverse=True)
    codes = [code for code, _ in ranking]
    projected_position = codes.index(selected_code) + 1

    ahead_code = codes[projected_position - 2] if projected_position > 1 else None
    behind_code = codes[projected_position] if projected_position < len(codes) else None

    ahead_gap_s = None
    behind_gap_s = None
    if ahead_code:
        ahead_progress = dict(ranking)[ahead_code]
        ahead_gap_s = max(0.0, ahead_progress - projected_progress) / max(1.0, reference_speed_mps)
    if behind_code:
        behind_progress = dict(ranking)[behind_code]
        behind_gap_s = max(0.0, projected_progress - behind_progress) / max(1.0, reference_speed_mps)

    min_gap = min(
        gap for gap in (ahead_gap_s, behind_gap_s) if gap is not None
    ) if ahead_gap_s is not None or behind_gap_s is not None else None

    if min_gap is None:
        traffic_risk = "Clear"
    elif min_gap < 1.0:
        traffic_risk = "Heavy traffic"
    elif min_gap < 2.0:
        traffic_risk = "Moderate traffic"
    else:
        traffic_risk = "Clean air"

    return {
        "projected_position": projected_position,
        "ahead_code": ahead_code,
        "behind_code": behind_code,
        "ahead_gap_s": ahead_gap_s,
        "behind_gap_s": behind_gap_s,
        "traffic_risk": traffic_risk,
        "projected_progress": projected_progress,
        "ranking": ranking,
    }


def detect_drs_trains(
    snapshots: Iterable[DriverSnapshot],
    gap_threshold_s: float = 1.2,
) -> List[dict]:
    ordered = list(snapshots)
    trains: List[dict] = []
    current_group: List[DriverSnapshot] = []
    current_gaps: List[float] = []

    for idx, snap in enumerate(ordered):
        if idx == 0:
            current_group = [snap]
            current_gaps = []
            continue

        front = ordered[idx - 1]
        gap_s = estimate_gap_seconds(front, snap)
        drs_hint = drs_state(snap.drs) in ("ON", "AVAIL")

        if gap_s <= gap_threshold_s or drs_hint:
            current_group.append(snap)
            current_gaps.append(gap_s)
        else:
            if len(current_group) >= 3:
                trains.append(_format_train(current_group, current_gaps))
            current_group = [snap]
            current_gaps = []

    if len(current_group) >= 3:
        trains.append(_format_train(current_group, current_gaps))

    return trains


def _format_train(group: List[DriverSnapshot], gaps: List[float]) -> dict:
    avg_gap = sum(gaps) / len(gaps) if gaps else 0.0
    active_drs = sum(1 for snap in group[1:] if drs_state(snap.drs) in ("ON", "AVAIL"))
    return {
        "lead": group[0].code,
        "tail": group[-1].code,
        "cars": [snap.code for snap in group],
        "length": len(group),
        "avg_gap_s": avg_gap,
        "active_drs_followers": active_drs,
    }


def classify_strategy_signal(
    gap_s: Optional[float],
    pace_delta_s_per_lap: Optional[float],
    tyre_life_delta: Optional[float],
    traffic_risk: str,
) -> Tuple[str, str]:
    if gap_s is None or pace_delta_s_per_lap is None or tyre_life_delta is None:
        return ("Insufficient data", "Need more replay history to score the move.")

    undercut_score = 0
    overcut_score = 0

    if gap_s <= 3.0:
        undercut_score += 2
    elif gap_s <= 5.0:
        undercut_score += 1

    if pace_delta_s_per_lap < -0.3:
        undercut_score += 2
    elif pace_delta_s_per_lap < 0:
        undercut_score += 1
    elif pace_delta_s_per_lap > 0.3:
        overcut_score += 2
    elif pace_delta_s_per_lap > 0:
        overcut_score += 1

    if tyre_life_delta > 3:
        undercut_score += 2
    elif tyre_life_delta > 0:
        undercut_score += 1
    elif tyre_life_delta < -3:
        overcut_score += 1

    if traffic_risk == "Clean air":
        undercut_score += 1
    elif traffic_risk == "Heavy traffic":
        overcut_score += 2
    elif traffic_risk == "Moderate traffic":
        overcut_score += 1

    if undercut_score >= overcut_score + 2:
        return ("Undercut favored", "Gap, tyre age, and projected rejoin traffic support stopping first.")
    if overcut_score >= undercut_score + 2:
        return ("Overcut possible", "Current pace or traffic risk argues for staying out longer.")
    return ("Marginal", "The gap is live, but the traffic and pace picture is not one-sided.")
