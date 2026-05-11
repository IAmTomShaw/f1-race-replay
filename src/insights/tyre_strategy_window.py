import matplotlib
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas

from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout
from src.gui.pit_wall_window import PitWallWindow

_BG = "#1a1a2e"
_FG = "#e0e0e0"

COMPOUND_COLORS = {
    0: "#E8002D",   # SOFT
    1: "#FFF200",   # MEDIUM
    2: "#EBEBEB",   # HARD
    3: "#39B54A",   # INTERMEDIATE
    4: "#0067FF",   # WET
}
COMPOUND_LABELS = {0: "S", 1: "M", 2: "H", 3: "I", 4: "W"}
COMPOUND_NAMES = {0: "Soft", 1: "Medium", 2: "Hard", 3: "Intermediate", 4: "Wet"}


class TyreStrategyWindow(PitWallWindow):
    def __init__(self):
        self._stints: dict[str, list[dict]] = {}
        self._current: dict[str, dict] = {}  # keys include current_lap
        self._positions: dict[str, int] = {}
        self._total_laps: int = 60
        self._last_drawn_lap: int = -1
        self._bar_patches: list[tuple] = []
        self._tooltip = None
        super().__init__()
        self.setWindowTitle("F1 Race Replay - Tyre Strategy")

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(8, 8, 8, 8)

        self._fig, self._ax = plt.subplots(figsize=(12, 8), facecolor=_BG)
        self._fig.tight_layout(pad=2.0)
        self._ax.set_facecolor(_BG)
        self._canvas = FigureCanvas(self._fig)
        self._canvas.mpl_connect("motion_notify_event", self._on_hover)
        layout.addWidget(self._canvas)

        self._draw_placeholder()

    def _draw_placeholder(self):
        self._ax.clear()
        self._ax.set_facecolor(_BG)
        self._ax.text(
            0.5, 0.5, "Waiting for telemetry data…",
            ha="center", va="center", color=_FG,
            transform=self._ax.transAxes, fontsize=14,
        )
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        self._canvas.draw_idle()

    def on_telemetry_data(self, data: dict):
        if not data.get("frame"):
            return
        drivers = data["frame"].get("drivers", {})
        if not drivers:
            return

        session = data.get("session_data", {})
        if "total_laps" in session:
            self._total_laps = session["total_laps"] or self._total_laps
        leader_lap = session.get("lap", self._last_drawn_lap)

        changed = False
        for code, dinfo in drivers.items():
            compound = int(dinfo.get("tyre", 1))
            tyre_life = max(0, int(dinfo.get("tyre_life", 0)))
            lap = int(dinfo.get("lap", 0))
            self._positions[code] = int(dinfo.get("position", 99))

            if code not in self._current:
                # tyre_life may include qualifying laps — store as initial offset for hover info only
                self._stints[code] = []
                self._current[code] = {
                    "compound": compound,
                    "start_lap": max(1, lap),
                    "current_lap": lap,
                    "initial_tyre_life": tyre_life,
                    "tyre_life": tyre_life,
                }
                changed = True
            else:
                prev = self._current[code]
                pit_stop = tyre_life < prev["tyre_life"] - 3 or compound != prev["compound"]
                if pit_stop:
                    # Stint ended the lap before the pit was detected
                    race_laps = max(0, lap - prev["start_lap"])
                    self._stints[code].append({
                        "compound": prev["compound"],
                        "start_lap": prev["start_lap"],
                        "race_laps": race_laps,
                        "total_age": prev["tyre_life"],
                        "initial_age": prev["initial_tyre_life"],
                    })
                    self._current[code] = {
                        "compound": compound,
                        "start_lap": lap,
                        "current_lap": lap,
                        "initial_tyre_life": tyre_life,
                        "tyre_life": tyre_life,
                    }
                    changed = True
                elif tyre_life != prev["tyre_life"] or lap != prev["current_lap"]:
                    prev["tyre_life"] = tyre_life
                    prev["current_lap"] = lap
                    changed = True

        if changed or leader_lap != self._last_drawn_lap:
            self._last_drawn_lap = leader_lap
            self._redraw()

    def _on_hover(self, event):
        if event.inaxes != self._ax or not self._bar_patches:
            if self._tooltip:
                self._tooltip.set_visible(False)
                self._canvas.draw_idle()
            return

        hit = None
        for patch, info in self._bar_patches:
            if patch.contains(event)[0]:
                hit = info
                break

        if self._tooltip is None:
            self._tooltip = self._ax.annotate(
                "", xy=(0, 0), xytext=(10, 10),
                textcoords="offset points",
                bbox=dict(boxstyle="round,pad=0.4", fc="#2a2a40", ec="#888888", alpha=0.95),
                color=_FG, fontsize=8,
                ha="left", va="bottom",
            )

        if hit:
            compound_name = COMPOUND_NAMES.get(hit["compound"], "?")
            race_laps = hit["race_laps"]
            total_age = hit["total_age"]
            pre_existing = hit.get("initial_age", 0)

            lines = [f"{hit['driver']}  —  {compound_name}"]
            lines.append(f"Race laps: {race_laps}")
            if pre_existing > 0:
                lines.append(f"Tyre age: {total_age} laps  (+{pre_existing} pre-used)")
            else:
                lines.append(f"Tyre age: {total_age} laps")

            self._tooltip.set_text("\n".join(lines))
            self._tooltip.xy = (event.xdata, event.ydata)
            self._tooltip.set_visible(True)
        else:
            self._tooltip.set_visible(False)

        self._canvas.draw_idle()

    def _redraw(self):
        ax = self._ax
        ax.clear()
        ax.set_facecolor(_BG)
        self._bar_patches = []
        self._tooltip = None  # annotation is cleared with ax.clear()

        if not self._current:
            return

        sorted_drivers = sorted(self._positions, key=lambda c: self._positions.get(c, 99))
        n = len(sorted_drivers)
        y_idx = {code: n - i for i, code in enumerate(sorted_drivers)}

        for code in sorted_drivers:
            y = y_idx[code]

            for stint in self._stints.get(code, []):
                color = COMPOUND_COLORS.get(stint["compound"], "#888888")
                left = stint["start_lap"] - 1
                width = stint["race_laps"]
                if width <= 0:
                    continue
                bars = ax.barh(y, width, left=left, height=0.6, color=color, alpha=0.9,
                               edgecolor="#333333", linewidth=0.5)
                info = {
                    "driver": code,
                    "compound": stint["compound"],
                    "race_laps": stint["race_laps"],
                    "total_age": stint["total_age"],
                    "initial_age": stint.get("initial_age", 0),
                }
                for patch in bars.patches:
                    self._bar_patches.append((patch, info))
                if width >= 3:
                    label = COMPOUND_LABELS.get(stint["compound"], "?")
                    ax.text(left + width / 2, y, label, ha="center", va="center",
                            color="black", fontsize=7, fontweight="bold")

            curr = self._current.get(code)
            if curr:
                # Use lap numbers for width — never zero on first frame
                race_laps = max(1, curr["current_lap"] - curr["start_lap"] + 1)
                color = COMPOUND_COLORS.get(curr["compound"], "#888888")
                left = curr["start_lap"] - 1
                bars = ax.barh(y, race_laps, left=left, height=0.6, color=color, alpha=1.0,
                               edgecolor="white", linewidth=0.8)
                info = {
                    "driver": code,
                    "compound": curr["compound"],
                    "race_laps": race_laps,
                    "total_age": curr["tyre_life"],
                    "initial_age": curr["initial_tyre_life"],
                }
                for patch in bars.patches:
                    self._bar_patches.append((patch, info))
                if race_laps >= 3:
                    label = COMPOUND_LABELS.get(curr["compound"], "?")
                    ax.text(left + race_laps / 2, y, label, ha="center", va="center",
                            color="black", fontsize=7, fontweight="bold")

        ax.set_yticks([y_idx[c] for c in sorted_drivers])
        ax.set_yticklabels(sorted_drivers, color=_FG, fontsize=9)
        ax.set_xlim(0, max(self._total_laps, self._last_drawn_lap + 5, 1))
        ax.set_ylim(0, n + 1)
        ax.set_xlabel("Lap", color=_FG, fontsize=10)
        ax.set_title("Tyre Strategy", color=_FG, fontsize=13, pad=8)
        ax.tick_params(colors=_FG)
        for spine in ax.spines.values():
            spine.set_edgecolor("#444444")

        legend = [
            mpatches.Patch(color=COMPOUND_COLORS[0], label="Soft"),
            mpatches.Patch(color=COMPOUND_COLORS[1], label="Medium"),
            mpatches.Patch(color=COMPOUND_COLORS[2], label="Hard"),
            mpatches.Patch(color=COMPOUND_COLORS[3], label="Inter"),
            mpatches.Patch(color=COMPOUND_COLORS[4], label="Wet"),
        ]
        ax.legend(handles=legend, loc="upper right",
                  facecolor="#2a2a40", edgecolor="#555555",
                  labelcolor=_FG, fontsize=9)

        self._canvas.draw_idle()

    def on_connection_status_changed(self, status: str):
        if status != "Connected":
            self._draw_placeholder()


def main():
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("Tyre Strategy")
    window = TyreStrategyWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
