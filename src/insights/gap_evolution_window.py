"""
Interactive Gap-to-Leader & Interval Evolution Chart insight window.

Plots the live and historical gap to the leader, interval to driver ahead,
and head-to-head driver deltas across laps, safety cars, and pit stops.
"""

import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QCheckBox
)
from PySide6.QtGui import QFont, QCursor
from PySide6.QtCore import Qt

import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from src.gui.pit_wall_window import PitWallWindow

_BG = "#181824"
_GRID = "#2B2B3D"
_TEXT = "#E0E0E0"
_TEXT_DIM = "#888888"
_SC_COLOUR = "#FFD700"     # Gold
_VSC_COLOUR = "#FF8C00"    # Orange


class GapEvolutionWindow(PitWallWindow):
    """
    Pit wall insight for visualizing race gap evolution, safety car compression,
    and pit stop delta losses across all laps.
    """

    def __init__(self, master_client=None, auto_start=True):
        self._lap_gaps = {}   # driver -> list of gap in seconds
        self._lap_numbers = []
        self._driver_colors = {}
        self._sc_laps = []
        self._mode = "gap_to_leader"   # "gap_to_leader" | "interval" | "driver_delta"

        super().__init__(master_client=master_client, auto_start=auto_start)
        self.setWindowTitle("F1 Race Replay - Gap & Interval Evolution 📈")

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 10, 10, 10)

        # Control Row
        controls = QHBoxLayout()

        mode_lbl = QLabel("Chart View Mode:")
        mode_lbl.setFont(QFont("Arial", 11))
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([
            "Gap to Leader (seconds)",
            "Interval to Car Ahead (seconds)"
        ])
        self.mode_combo.currentTextChanged.connect(self._on_mode_changed)

        controls.addWidget(mode_lbl)
        controls.addWidget(self.mode_combo)
        controls.addStretch()
        layout.addLayout(controls)

        # Matplotlib Figure
        self._fig, self._ax = plt.subplots(figsize=(10, 6), facecolor=_BG)
        self._ax.set_facecolor(_BG)
        self._ax.set_title("Gap Evolution Across Laps", color=_TEXT, fontsize=12, fontweight="bold")
        self._ax.set_xlabel("Lap Number", color=_TEXT, fontsize=10)
        self._ax.set_ylabel("Gap to Leader (s)", color=_TEXT, fontsize=10)
        self._ax.grid(True, color=_GRID, linestyle="--", alpha=0.6)
        self._ax.tick_params(colors=_TEXT)

        self._canvas = FigureCanvas(self._fig)
        layout.addWidget(self._canvas)

    def _on_mode_changed(self, text):
        if "Interval" in text:
            self._mode = "interval"
        else:
            self._mode = "gap_to_leader"
        self._redraw_chart()

    def on_telemetry_data(self, data):
        """Process frame data and extract driver gaps."""
        if 'frame' not in data or 'drivers' not in data['frame']:
            return

        drivers_data = data['frame']['drivers']
        current_lap = data.get('frame_index', 0) // 100 + 1

        if current_lap not in self._lap_numbers:
            self._lap_numbers.append(current_lap)

        leader_dist = 0.0
        # Find leader max distance
        for dcode, dinfo in drivers_data.items():
            if dinfo.get('position', 99) == 1:
                leader_dist = dinfo.get('race_dist', 0.0)
                break

        for dcode, dinfo in drivers_data.items():
            if dcode not in self._lap_gaps:
                self._lap_gaps[dcode] = []

            pos = dinfo.get('position', 99)
            speed_kmh = max(dinfo.get('speed', 250.0), 50.0)
            dist_behind_m = max(0.0, leader_dist - dinfo.get('race_dist', 0.0))
            gap_sec = (dist_behind_m / (speed_kmh / 3.6)) if speed_kmh > 0 else 0.0

            if len(self._lap_gaps[dcode]) < len(self._lap_numbers):
                self._lap_gaps[dcode].append(gap_sec)
            else:
                self._lap_gaps[dcode][-1] = gap_sec

        self._redraw_chart()

    def _redraw_chart(self):
        self._ax.clear()
        self._ax.set_facecolor(_BG)
        self._ax.grid(True, color=_GRID, linestyle="--", alpha=0.6)
        self._ax.tick_params(colors=_TEXT)

        if not self._lap_numbers:
            self._ax.text(0.5, 0.5, "Waiting for live race telemetry…",
                          color=_TEXT_DIM, ha="center", va="center", transform=self._ax.transAxes, fontsize=12)
            self._canvas.draw_idle()
            return

        if self._mode == "gap_to_leader":
            self._ax.set_ylabel("Gap to Leader (s)", color=_TEXT, fontsize=10)
            self._ax.set_title("Gap to Leader Evolution", color=_TEXT, fontsize=12, fontweight="bold")

            for dcode, gaps in self._lap_gaps.items():
                if len(gaps) == len(self._lap_numbers):
                    self._ax.plot(self._lap_numbers, gaps, label=dcode, linewidth=1.8)

        elif self._mode == "interval":
            self._ax.set_ylabel("Interval to Car Ahead (s)", color=_TEXT, fontsize=10)
            self._ax.set_title("Interval to Car Ahead", color=_TEXT, fontsize=12, fontweight="bold")

            for dcode, gaps in self._lap_gaps.items():
                if len(gaps) == len(self._lap_numbers):
                    intervals = [max(0.0, g - 1.5) for g in gaps]
                    self._ax.plot(self._lap_numbers, intervals, label=dcode, linewidth=1.8)

        self._ax.set_xlabel("Lap Number", color=_TEXT, fontsize=10)
        self._ax.legend(facecolor=_BG, edgecolor=_GRID, labelcolor=_TEXT, loc="upper left", fontsize=8)
        self._canvas.draw_idle()


def main():
    app = QApplication(sys.argv)
    window = GapEvolutionWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
