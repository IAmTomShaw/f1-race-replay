import datetime
import os
from typing import Dict, List, Optional, Tuple

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False

RaceSummary = Dict[str, object]


def build_race_summary(frames: List[Dict]) -> RaceSummary:
    """
    Compute lightweight race summary information from replay frames.
    Returns classification, pit-stop counts, and fastest lap estimate.
    """
    if not frames:
        return {"classification": [], "pit_stops": {}, "fastest_lap": None}

    last_frame = frames[-1]
    classification = []
    entries = []

    for code, data in last_frame.get("drivers", {}).items():
        pos = data.get("position")
        # Fallback to distance ordering if official position is missing
        pos = pos if pos is not None else data.get("dist", 0)
        entries.append((pos, code, data))

    entries.sort(key=lambda item: item[0])
    for idx, (_, code, data) in enumerate(entries, start=1):
        classification.append(
            {
                "pos": idx,
                "code": code,
                "lap": int(data.get("lap", 0) or 0),
                "tyre": data.get("tyre"),
            }
        )

    pit_stops: Dict[str, int] = {}
    tyre_state: Dict[str, object] = {}
    fastest = {"code": None, "lap": None, "time": None}
    lap_start: Dict[str, float] = {}
    current_lap: Dict[str, int] = {}

    for frame in frames:
        t = frame.get("t", 0.0)
        for code, data in frame.get("drivers", {}).items():
            tyre = data.get("tyre")
            last_tyre = tyre_state.get(code)
            if last_tyre is None:
                tyre_state[code] = tyre
            elif tyre != last_tyre:
                pit_stops[code] = pit_stops.get(code, 0) + 1
                tyre_state[code] = tyre

            lap = int(data.get("lap", 0) or 0)
            if code not in lap_start:
                lap_start[code] = t
                current_lap[code] = lap
                continue

            if lap != current_lap.get(code, lap):
                # Lap completion detected
                duration = t - lap_start.get(code, t)
                if duration > 0 and (fastest["time"] is None or duration < fastest["time"]):
                    fastest = {"code": code, "lap": current_lap.get(code, lap), "time": duration}
                lap_start[code] = t
                current_lap[code] = lap

    return {"classification": classification, "pit_stops": pit_stops, "fastest_lap": fastest}


def _format_time(seconds: Optional[float]) -> str:
    if seconds is None:
        return "N/A"
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02}:{secs:05.2f}"


def export_pdf_report(
    output_path: str,
    summary: RaceSummary,
    snapshot: Optional[Dict[str, object]] = None,
    title: str = "Race Report",
):
    """
    Export a compact PDF report to disk. If reportlab is missing, raises RuntimeError.
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab is required for PDF export but is not installed")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    cursor_y = height - 50

    def draw_line(text: str, size: int = 11, leading: int = 16):
        nonlocal cursor_y
        c.setFont("Helvetica", size)
        c.drawString(40, cursor_y, text)
        cursor_y -= leading

    draw_line(title, size=16, leading=22)
    draw_line(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), size=9, leading=14)
    cursor_y -= 6

    draw_line("Final Classification", size=13, leading=18)
    for row in summary.get("classification", []):
        draw_line(f"P{row['pos']:>2}  {row['code']}   Lap {row.get('lap', 'N/A')}")

    cursor_y -= 6
    fastest = summary.get("fastest_lap") or {}
    fastest_label = (
        f"{fastest.get('code', 'N/A')} (Lap {fastest.get('lap', 'N/A')}) - {_format_time(fastest.get('time'))}"
    )
    draw_line(f"Fastest Lap: {fastest_label}", leading=18)

    draw_line("Pit Stops", size=13, leading=18)
    pit_data = summary.get("pit_stops") or {}
    if not pit_data:
        draw_line("No pit-stop data available", leading=14)
    else:
        for code, count in sorted(pit_data.items()):
            draw_line(f"{code}: {count}")

    if snapshot:
        cursor_y -= 6
        draw_line("Telemetry Snapshot", size=13, leading=18)
        for key in ("code", "lap", "speed", "gear", "drs", "throttle", "brake"):
            if key in snapshot:
                draw_line(f"{key.title()}: {snapshot[key]}", leading=14)

    c.showPage()
    c.save()
