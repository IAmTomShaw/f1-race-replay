import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFrame
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import numpy as np

from src.gui.pit_wall_window import PitWallWindow
from src.lib.tyres import get_tyre_compound_str


class TyreDegradationWindow(PitWallWindow):
    """
    Window for analyzing tyre degradation impact over the course of a race.
    Shows cumulative degradation for all drivers by default; user can select
    an individual driver to focus.
    """

    def __init__(self):
        # Initialize attributes before calling parent __init__ because
        # PitWallWindow.__init__ calls setup_ui() which expects these
        # attributes to exist.
        self.current_driver = "All Drivers"
        self.driver_data = {}  # Store data list for each driver

        # Fallback tyre degradation rates (seconds per lap)
        self.degradation_rates = {
            0: 0.0179,  # SOFT (example value)
            1: 0.015,   # MEDIUM (estimated)
            2: 0.0179,  # HARD (user specified)
            3: 0.02,    # INTERMEDIATE (estimated)
            4: 0.012    # WET (estimated)
        }
        self._fallback_degradation_rates = dict(self.degradation_rates)

        # Expected tyre life (laps) per compound for health normalization
        # 100% at lap 1 of stint, 0% at expected life, negative beyond expected life
        self.expected_tyre_life = {
            0: 20,  # SOFT
            1: 25,  # MEDIUM
            2: 30,  # HARD
            3: 18,  # INTERMEDIATE
            4: 22   # WET
        }
        self._fallback_expected_tyre_life = dict(self.expected_tyre_life)
        self.tyre_profile_source = "Fallback"

        super().__init__()
        self.setWindowTitle("F1 Tyre Degradation Analysis")
        self.setGeometry(200, 200, 1000, 700)

        # Timer for periodic plot updates to reduce lag
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_plot)
        self.update_timer.start(100)  # Update every 0.1 seconds

    def setup_ui(self):
        """Create the UI components."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)

        # Header
        header = self.create_header()
        main_layout.addWidget(header)

        # Controls
        controls = self.create_controls()
        main_layout.addWidget(controls)

        # Plot area
        self.figure = Figure(figsize=(10, 6))
        self.canvas = FigureCanvas(self.figure)
        main_layout.addWidget(self.canvas)

        # Initial plot
        self.update_plot()

    def create_header(self):
        """Create the header section."""
        header = QFrame()
        header.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(header)

        title = QLabel("🛞 Tyre Degradation Analysis")
        title.setFont(QFont("Arial", 20, QFont.Bold))
        layout.addWidget(title)

        self.subtitle = QLabel(
            f"Cumulative degradation impact for selected driver • Profile: {self.tyre_profile_source}"
        )
        self.subtitle.setFont(QFont("Arial", 12))
        layout.addWidget(self.subtitle)

        return header

    def create_controls(self):
        """Create the control panel."""
        controls = QFrame()
        controls.setFrameShape(QFrame.NoFrame)

        layout = QHBoxLayout(controls)

        # Driver selection
        driver_label = QLabel("Select Driver:")
        driver_label.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(driver_label)

        self.driver_combo = QComboBox()
        # Default option to show all drivers
        self.driver_combo.addItem("All Drivers")
        self.driver_combo.setMinimumWidth(150)
        self.driver_combo.currentTextChanged.connect(self.on_driver_changed)
        layout.addWidget(self.driver_combo)

        layout.addStretch()

        # Refresh button
        refresh_btn = QPushButton("Refresh Data")
        refresh_btn.clicked.connect(self.refresh_data)
        layout.addWidget(refresh_btn)

        return controls

    def on_telemetry_data(self, data):
        """Process incoming telemetry data and store per-driver tyre info."""
        profile = data.get('tyre_profile')
        if profile:
            self._update_tyre_profile(profile)

        if 'frame' in data and 'drivers' in data['frame']:
            drivers = data['frame']['drivers']

            # Keep combo: All Drivers + driver codes
            driver_codes = list(drivers.keys())
            desired = ["All Drivers"] + driver_codes
            current_items = [self.driver_combo.itemText(i) for i in range(self.driver_combo.count())]
            if current_items != desired:
                try:
                    self.driver_combo.currentTextChanged.disconnect(self.on_driver_changed)
                except Exception:
                    pass
                self.driver_combo.clear()
                self.driver_combo.addItems(desired)
                self.driver_combo.currentTextChanged.connect(self.on_driver_changed)
                if self.current_driver not in desired:
                    self.current_driver = "All Drivers"
                    self.driver_combo.setCurrentText(self.current_driver)

            # Append telemetry entry for each driver
            frame_index = data.get('frame_index', 0)
            for code, pos in drivers.items():
                if code not in self.driver_data:
                    self.driver_data[code] = []

                tyre_data = {
                    'frame': frame_index,
                    'tyre': pos.get('tyre', 0),
                    'tyre_life': pos.get('tyre_life', 0),
                    'lap': pos.get('lap', 0)
                }
                self.driver_data[code].append(tyre_data)
                # cap memory per driver to last 1000 points for performance
                if len(self.driver_data[code]) > 1000:
                    self.driver_data[code] = self.driver_data[code][-1000:]

        # Plot updates are now handled by a timer to reduce lag

    def on_driver_changed(self, driver):
        """Handle driver selection change."""
        if driver:
            self.current_driver = driver
            self.update_plot()

    def refresh_data(self):
        """Refresh the data collection (clears stored telemetry)."""
        self.driver_data = {}
        self.update_plot()

    def _update_tyre_profile(self, profile):
        """Update race-specific tyre degradation profile from telemetry stream."""
        updated = False

        max_life = profile.get('max_tyre_life', {}) if isinstance(profile, dict) else {}
        if isinstance(max_life, dict) and max_life:
            parsed_life = {}
            for key, value in max_life.items():
                try:
                    tyre_key = int(key)
                    tyre_life = int(value)
                except (TypeError, ValueError):
                    continue
                if tyre_life > 0:
                    parsed_life[tyre_key] = tyre_life

            merged_life = dict(self._fallback_expected_tyre_life)
            merged_life.update(parsed_life)
            if parsed_life and merged_life != self.expected_tyre_life:
                self.expected_tyre_life = merged_life
                self.tyre_profile_source = "Race Session"
                updated = True

        rates = profile.get('degradation_rates', {}) if isinstance(profile, dict) else {}
        if isinstance(rates, dict) and rates:
            parsed_rates = {}
            for key, value in rates.items():
                try:
                    tyre_key = int(key)
                    rate = float(value)
                except (TypeError, ValueError):
                    continue
                if rate >= 0:
                    parsed_rates[tyre_key] = rate

            merged_rates = dict(self._fallback_degradation_rates)
            merged_rates.update(parsed_rates)
            if parsed_rates and merged_rates != self.degradation_rates:
                self.degradation_rates = merged_rates
                self.tyre_profile_source = "Race Session"
                updated = True

        if updated and hasattr(self, 'subtitle'):
            self.subtitle.setText(
                f"Cumulative degradation impact for selected driver • Profile: {self.tyre_profile_source}"
            )

    def update_plot(self):
        """Update the degradation plot for all drivers or a single driver."""
        self.figure.clear()

        ax = self.figure.add_subplot(111)

        # If no telemetry yet, show placeholder
        if not self.driver_data:
            ax.text(0.5, 0.5, "Waiting for telemetry data...\nSelect a driver to view degradation analysis",
                   ha='center', va='center', transform=ax.transAxes, fontsize=14)
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            self.canvas.draw()
            return

        # Helper to compute plot points for a single driver's stored data
        def compute_degradation_series(entries):
            if not entries:
                return [], []
            entries = sorted(entries, key=lambda x: x['frame'])
            tyre_lives = [e['tyre_life'] for e in entries]
            compounds = [e['tyre'] for e in entries]
            laps = [e['lap'] for e in entries]

            # Build stints
            stints = []
            current_stint = None
            previous_life = None
            for i, (life, compound, lap) in enumerate(zip(tyre_lives, compounds, laps)):
                # Start a new stint when:
                # 1) compound changes, or
                # 2) tyre life resets/decreases (pit stop on same compound)
                is_new_stint = (
                    current_stint is None
                    or current_stint['compound'] != compound
                    or (previous_life is not None and life < previous_life)
                )

                if is_new_stint:
                    current_stint = {
                        'compound': compound,
                        'start_life': life,
                        'start_lap': lap,
                        'lives': [life],
                        'laps': [lap]
                    }
                    stints.append(current_stint)
                else:
                    current_stint['lives'].append(life)
                    current_stint['laps'].append(lap)

                previous_life = life

            plot_x = []
            plot_y = []
            for stint in stints:
                compound = stint['compound']
                expected_life = self.expected_tyre_life.get(compound, 25)
                start_lap = stint['start_lap']
                start_life = stint['start_life']
                for life, lap in zip(stint['lives'], stint['laps']):
                    # Degrade health by race laps completed in this stint
                    # so the curve decreases gradually lap-by-lap.
                    # If the tyre is already used at stint start, initial
                    # health starts below 100% based on start_life.
                    laps_in_stint = max(0, lap - start_lap)
                    effective_life_progress = max(0, (start_life - 1) + laps_in_stint)
                    if expected_life > 1:
                        health_pct = 100 - (effective_life_progress / (expected_life - 1)) * 100
                    else:
                        health_pct = 100.0
                    plot_x.append(lap)
                    plot_y.append(health_pct)

            return plot_x, plot_y

        # Compute the current max lap across all drivers for x-axis synchronization
        max_lap = max((max(e['lap'] for e in entries) for entries in self.driver_data.values() if entries), default=0)

        # If a single driver is selected, show only that driver
        if self.current_driver and self.current_driver != "All Drivers":
            driver = self.current_driver
            entries = self.driver_data.get(driver, [])
            px, py = compute_degradation_series(entries)
            if px and py:
                ax.plot(px, py, linewidth=2, color='tab:blue', label=driver)
            ax.set_title(f'Tyre Degradation Analysis - {driver}')
            ax.set_xlabel('Race Lap')
            ax.set_ylabel('Tyre Health (%)')
            ax.set_xlim(0, max_lap + 1)
            ax.grid(True, alpha=0.3)
            ax.legend()
            self.figure.tight_layout()
            self.canvas.draw()
            return

        # Otherwise plot all drivers
        cmap = plt.get_cmap('tab10')
        drivers_sorted = sorted(self.driver_data.keys())
        plotted = False
        for idx, driver in enumerate(drivers_sorted):
            entries = self.driver_data.get(driver, [])
            px, py = compute_degradation_series(entries)
            if px and py:
                color = cmap(idx % 10)
                ax.plot(px, py, linewidth=1.5, color=color, label=driver, alpha=0.9)
                plotted = True

        if not plotted:
            ax.text(0.5, 0.5, "No tyre data to plot yet", ha='center', va='center', transform=ax.transAxes)

        ax.set_title('Tyre Degradation Analysis - All Drivers')
        ax.set_xlabel('Race Lap')
        ax.set_ylabel('Tyre Health (%)')
        ax.set_xlim(0, max_lap + 1)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='upper left', fontsize='small', ncol=2)
        self.figure.tight_layout()
        self.canvas.draw()


def main():
    """Launch the tyre degradation analysis window."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    window = TyreDegradationWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())