"""
overtaking_insight.py
Live overtaking probability panel for the F1 Race Replay pit wall.

Extends PitWallWindow — same pattern as DriverTelemetryWindow and the
existing insight panels. Runs as a separate process, connects to the
TelemetryStreamServer via TCP, and receives frames through on_telemetry_data().

What it shows:
    For every pair of adjacent cars currently within DRS range (~1.0s gap),
    display a probability bar from the trained XGBoost overtaking classifier:

        LEC → VER   gap 0.61s   ████████░░░░░░░░░░░░  41%

    Colour coding:
        Red   (≥ 50%) — likely overtake
        Amber (≥ 25%) — watch this pair
        Green (< 25%) — low threat

Gap approximation:
    The live stream sends each driver's distance along the current lap (metres)
    and speed (km/h). We approximate the time gap as:

        gap_s ≈ gap_metres / car_behind_speed_ms

    This is accurate enough for DRS detection (~80m at 290 km/h ≈ 1.0s).
    The known limitation: in heavy braking zones, instantaneous speed
    underestimates the effective gap slightly. This is acceptable for a
    visualisation tool — production F1 systems use transponder timing.

Usage (standalone):
    F1_MODEL_DIR=/path/to/models python -m src.insights.overtaking_insight

Usage (from insights menu):
    Launched as a subprocess — see src/gui/insights_menu.py
"""

import os
import sys

import matplotlib
matplotlib.use("QtAgg")

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QFrame,
)
from PySide6.QtGui import QFont
from PySide6.QtCore import Qt

from src.gui.pit_wall_window import PitWallWindow
from src.overtaking_integrator import OvertakingIntegrator

# ── Visual constants (matching the existing insight colour scheme) ────────────
_BG          = "#282828"
_PANEL_BG    = "#1e1e1e"
_TEXT        = "#F0F0F0"
_SUBTEXT     = "#888888"
_RED         = "#E74C3C"   # ≥ 50% — likely overtake
_AMBER       = "#F39C12"   # ≥ 25% — watch
_GREEN       = "#2ECC71"   # < 25% — low threat
_BAR_EMPTY   = "#444444"

_MAX_PAIRS   = 6           # maximum threat pairs to display
_BAR_WIDTH   = 18          # characters in ASCII probability bar


def _prob_colour(prob: float) -> str:
    if prob >= 0.50:
        return _RED
    elif prob >= 0.25:
        return _AMBER
    return _GREEN


def _bar(prob: float) -> str:
    """Return an ASCII probability bar: '████████░░░░░░░░░░  44%'"""
    filled = round(prob * _BAR_WIDTH)
    return "█" * filled + "░" * (_BAR_WIDTH - filled) + f"  {prob * 100:.0f}%"


class OvertakingInsight(PitWallWindow):
    """
    Pit wall insight panel — live overtaking probability.

    Lifecycle:
        1. __init__() — load model via OvertakingIntegrator
        2. on_session_ready(session) — call integrator.initialize_from_session()
           so compound + tyre_life lookups are available
        3. on_telemetry_data(data) — called every frame by the stream:
               compute gaps → call integrator → render results
        4. on_connection_status_changed(status) — clear display on disconnect
    """

    def __init__(self, model_path: str, compound_map_path: str):
        self._circuit_length_m: float | None = None
        self._session_loaded  = False   # True once FastF1 session data is loaded
        self._session_loading = False   # Guard against concurrent load attempts
        self._integrator = OvertakingIntegrator(model_path, compound_map_path)
        super().__init__()
        self.setWindowTitle("F1 Race Replay — Overtaking Probability")
        self.setMinimumWidth(460)
        self.resize(460, 360)

    # ── UI ────────────────────────────────────────────────────────────────

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Header
        title = QLabel("🏎  Overtaking Probability")
        title.setFont(QFont("Arial", 13, QFont.Bold))
        title.setStyleSheet(f"color: {_TEXT};")
        root.addWidget(title)

        subtitle = QLabel("Cars within DRS range · updated every frame")
        subtitle.setFont(QFont("Arial", 9))
        subtitle.setStyleSheet(f"color: {_SUBTEXT};")
        root.addWidget(subtitle)

        # Thin divider
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color: #444444;")
        root.addWidget(line)

        # One label row per possible threat pair
        self._pair_labels: list[QLabel] = []
        for _ in range(_MAX_PAIRS):
            lbl = QLabel()
            lbl.setFont(QFont("Courier New", 11))
            lbl.setStyleSheet(f"color: {_TEXT}; padding: 3px 0px;")
            lbl.setVisible(False)
            root.addWidget(lbl)
            self._pair_labels.append(lbl)

        # Shown when no cars are in DRS range
        self._empty_label = QLabel("No cars in DRS range")
        self._empty_label.setFont(QFont("Arial", 10))
        self._empty_label.setStyleSheet(f"color: {_SUBTEXT};")
        self._empty_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self._empty_label)

        root.addStretch()

        # Legend row
        legend_row = QHBoxLayout()
        for colour, text in [(_RED, "≥50% likely"), (_AMBER, "≥25% watch"), (_GREEN, "<25% low")]:
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {colour}; font-size: 14px;")
            lbl = QLabel(text)
            lbl.setFont(QFont("Arial", 8))
            lbl.setStyleSheet(f"color: {_SUBTEXT};")
            legend_row.addWidget(dot)
            legend_row.addWidget(lbl)
            legend_row.addSpacing(10)
        legend_row.addStretch()
        root.addLayout(legend_row)

        self.setStyleSheet(f"background-color: {_BG};")

    # ── Session initialisation ────────────────────────────────────────────

    def on_session_ready(self, session):
        """
        Called once the FastF1 session is loaded.
        Builds the compound + tyre_life lookup from session.laps.

        The stream doesn't send compound or tyre_life per driver —
        we need to load them from the laps DataFrame here, same approach
        as TyreDegradationIntegrator.initialize_from_session().
        """
        ok = self._integrator.initialize_from_session(session)
        if ok:
            print("OvertakingInsight: integrator ready")
        else:
            print("OvertakingInsight: integrator failed to initialise — probabilities unavailable")

    # ── Frame processing ──────────────────────────────────────────────────

    def on_telemetry_data(self, data: dict):
        if "frame" not in data or not data["frame"]:
            return

        frame   = data["frame"]
        drivers = frame.get("drivers", {})
        if not drivers:
            return

        # Capture circuit length once
        if self._circuit_length_m is None and data.get("circuit_length_m"):
            self._circuit_length_m = float(data["circuit_length_m"])
        if self._circuit_length_m is None:
            return

        # On first frame that carries session_info, load FastF1 lap data so
        # we can look up compound and tyre_life — the stream doesn't send these
        # per driver, but they're available via the FastF1 session object.
        if not self._session_loaded and not self._session_loading:
            session_info = data.get("session_info")
            if session_info and session_info.get("year") and session_info.get("round_num"):
                self._try_load_session(
                    year      = int(session_info["year"]),
                    round_num = int(session_info["round_num"]),
                )

        pairs = self._compute_threat_pairs(drivers)
        self._render(pairs)

    def _try_load_session(self, year: int, round_num: int):
        """
        Load FastF1 session in a background thread so we don't block the UI.
        Called once on the first frame that carries session_info.
        Sets self._session_loaded = True when done.
        """
        import threading

        self._session_loading = True

        def _load():
            try:
                import fastf1
                print(f"OvertakingInsight: loading FastF1 session {year} round {round_num}...")
                session = fastf1.get_session(year, round_num, "R")
                session.load(telemetry=False, weather=False)
                ok = self._integrator.initialize_from_session(session)
                if ok:
                    print("OvertakingInsight: tyre data loaded — full model active")
                else:
                    print("OvertakingInsight: tyre data load failed — using fallback values")
            except Exception as e:
                print(f"OvertakingInsight: session load error — {e}")
            finally:
                self._session_loaded  = True
                self._session_loading = False

        threading.Thread(target=_load, daemon=True).start()

    def _compute_threat_pairs(self, drivers: dict) -> list[dict]:
        """
        Sort all drivers by absolute track position, find adjacent pairs
        within DRS range, ask the model for overtake probability.

        Returns a list of dicts sorted by probability descending.
        """
        L = self._circuit_length_m

        # Build state list from the raw driver frame dicts
        states = []
        for code, d in drivers.items():
            try:
                dist     = float(d.get("dist")  or 0)
                lap      = int(d.get("lap")      or 0)
                speed_kh = float(d.get("speed")  or 1)   # km/h
                states.append({
                    "code":      code,
                    "raw":       d,                        # ← full dict for tyre data
                    "track_pos": lap * L + dist,
                    "dist":      dist,
                    "lap":       lap,
                    "speed_ms":  max(speed_kh / 3.6, 1.0),
                })
            except (TypeError, ValueError):
                continue

        # Sort: leader (largest track_pos) first
        states.sort(key=lambda x: x["track_pos"], reverse=True)

        pairs = []
        for i in range(1, len(states)):
            ahead  = states[i - 1]
            behind = states[i]

            gap_m = ahead["track_pos"] - behind["track_pos"]
            if gap_m < 0:               # lap wrap-around
                gap_m += L

            # Approximate gap in seconds from distance and speed
            gap_s = gap_m / behind["speed_ms"]

            if not self._integrator.is_in_drs_range(gap_s):
                continue

            prob = self._integrator.get_overtake_probability_from_frame(
                behind_driver = behind["code"],
                ahead_driver  = ahead["code"],
                behind_data   = behind["raw"],
                ahead_data    = ahead["raw"],
                gap_s         = gap_s,
                lap           = behind["lap"],
                position      = i + 1,
            )

            pairs.append({
                "behind": behind["code"],
                "ahead":  ahead["code"],
                "gap_s":  gap_s,
                "prob":   prob,
            })

        pairs.sort(key=lambda x: x["prob"], reverse=True)
        return pairs[:_MAX_PAIRS]

    # ── Rendering ─────────────────────────────────────────────────────────

    def _render(self, pairs: list[dict]):
        has_pairs = len(pairs) > 0
        self._empty_label.setVisible(not has_pairs)

        for i, lbl in enumerate(self._pair_labels):
            if i < len(pairs):
                p   = pairs[i]
                col = _prob_colour(p["prob"])
                # Format: "LEC → VER   gap 0.61s   ████████░░░░░░░░░░  41%"
                text = (
                    f"{p['behind']:>3} → {p['ahead']:<3}  "
                    f"gap {p['gap_s']:.2f}s   "
                    f"{_bar(p['prob'])}"
                )
                lbl.setText(text)
                lbl.setStyleSheet(f"color: {col}; padding: 3px 0px;")
                lbl.setVisible(True)
            else:
                lbl.setVisible(False)

    # ── Connection handling ───────────────────────────────────────────────

    def on_connection_status_changed(self, status: str):
        if status != "Connected":
            for lbl in self._pair_labels:
                lbl.setVisible(False)
            self._empty_label.setText(
                "Disconnected — waiting for F1 Race Replay..."
            )
            self._empty_label.setVisible(True)
        else:
            self._empty_label.setText("No cars in DRS range")


# ── Standalone entry point ────────────────────────────────────────────────────

def main():
    """
    Launch as a standalone process.
    F1_MODEL_DIR environment variable sets the models folder.
    Defaults to ./models if not set.
    """
    model_dir = os.environ.get("F1_MODEL_DIR", "./models")
    model_path       = os.path.join(model_dir, "overtaking_model.pkl")
    compound_map_path = os.path.join(model_dir, "compound_map.json")

    for path in (model_path, compound_map_path):
        if not os.path.exists(path):
            print(f"OvertakingInsight: model file not found: {path}")
            print(f"Set F1_MODEL_DIR to the folder containing your .pkl and .json files")
            sys.exit(1)

    app = QApplication(sys.argv)
    window = OvertakingInsight(
        model_path        = model_path,
        compound_map_path = compound_map_path,
    )
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()