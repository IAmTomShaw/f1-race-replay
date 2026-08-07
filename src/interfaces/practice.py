"""
Practice Session Replay & Stint Analyzer Interface.

Renders Practice Session (FP1 / FP2 / FP3) pace leaderboards, stint pace comparisons,
and long run vs qualifying simulation breakdowns.
"""

import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QSplitter, QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

PRACTICE_QSS = """
QMainWindow {
    background-color: #12121A;
    color: #E0E0E0;
}

QTabWidget::pane {
    border: 1px solid #2B2B3D;
    background: #181824;
}

QTabBar::tab {
    background: #1C1C28;
    color: #A0A0B0;
    padding: 8px 16px;
    font-weight: bold;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background: #E10600;
    color: #FFFFFF;
}

QTableWidget {
    background-color: #181824;
    gridline-color: #2B2B3D;
    color: #FFFFFF;
    font-size: 13px;
}

QHeaderView::section {
    background-color: #222232;
    color: #E10600;
    padding: 6px;
    font-weight: bold;
    border: 1px solid #2B2B3D;
}
"""


class PracticeSessionWindow(QMainWindow):
    """PySide6 interface for Practice Session Stint Pace Analysis."""

    def __init__(self, session_name: str, data: dict):
        super().__init__()
        self.session_name = session_name
        self.data = data

        self.setWindowTitle(f"F1 Practice Session Stint Pace Analyzer - {session_name} 🏎️")
        self.resize(1100, 700)
        self.setStyleSheet(PRACTICE_QSS)

        self._setup_ui()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Header
        header = QLabel(f"🏎️ {self.session_name.upper()} - PRACTICE STINT & PACE ANALYSIS")
        header.setFont(QFont("Arial", 16, QFont.Bold))
        header.setStyleSheet("color: #E10600; padding: 10px 0;")
        layout.addWidget(header)

        # Tabs: 1. Leaderboard & Best Laps, 2. Stint Pace Analysis
        tabs = QTabWidget()

        # Tab 1: Best Lap Times Leaderboard
        tab_best = QWidget()
        layout_best = QVBoxLayout(tab_best)
        table_best = self._create_best_laps_table()
        layout_best.addWidget(table_best)
        tabs.addTab(tab_best, "⏱️ Best Lap Leaderboard")

        # Tab 2: Stint Pace Analysis
        tab_stints = QWidget()
        layout_stints = QVBoxLayout(tab_stints)
        table_stints = self._create_stints_table()
        layout_stints.addWidget(table_stints)
        tabs.addTab(tab_stints, "📊 Long Run & Stint Pace")

        layout.addWidget(tabs)

    def _create_best_laps_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels([
            "Pos", "Driver", "Fastest Lap (s)", "Tyre", "S1 / S2 / S3", "Gap (s)"
        ])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        best_laps = self.data.get('best_laps', {})
        sorted_drivers = sorted(
            best_laps.values(),
            key=lambda x: (x['fastest_lap_time'] is None, x['fastest_lap_time'] or 9999)
        )

        table.setRowCount(len(sorted_drivers))
        top_time = sorted_drivers[0]['fastest_lap_time'] if sorted_drivers and sorted_drivers[0]['fastest_lap_time'] else None

        for pos, item in enumerate(sorted_drivers, start=1):
            table.setItem(pos - 1, 0, QTableWidgetItem(str(pos)))
            table.setItem(pos - 1, 1, QTableWidgetItem(item['driver']))

            t_val = f"{item['fastest_lap_time']:.3f}" if item['fastest_lap_time'] else "No Time"
            table.setItem(pos - 1, 2, QTableWidgetItem(t_val))
            table.setItem(pos - 1, 3, QTableWidgetItem(item['compound']))

            s_breakdown = f"{item['s1']:.2f} / {item['s2']:.2f} / {item['s3']:.2f}" if item['s1'] and item['s2'] and item['s3'] else "-"
            table.setItem(pos - 1, 4, QTableWidgetItem(s_breakdown))

            if top_time and item['fastest_lap_time']:
                gap = item['fastest_lap_time'] - top_time
                gap_str = "INTERVAL" if pos == 1 else f"+{gap:.3f}"
            else:
                gap_str = "-"
            table.setItem(pos - 1, 5, QTableWidgetItem(gap_str))

        return table

    def _create_stints_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels([
            "Driver", "Stint #", "Compound", "Run Type", "Avg Pace (s)"
        ])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        driver_stints = self.data.get('driver_stints', {})
        rows = []
        for driver, stint_list in driver_stints.items():
            for stint in stint_list:
                rows.append((driver, stint))

        table.setRowCount(len(rows))
        for idx, (driver, stint) in enumerate(rows):
            table.setItem(idx, 0, QTableWidgetItem(driver))
            table.setItem(idx, 1, QTableWidgetItem(str(stint['stint_number'])))
            table.setItem(idx, 2, QTableWidgetItem(stint['compound']))
            table.setItem(idx, 3, QTableWidgetItem(stint['run_type']))

            pace_str = f"{stint['avg_pace_sec']:.3f} ({stint['total_laps']} Laps)" if stint['avg_pace_sec'] else f"({stint['total_laps']} Laps)"
            table.setItem(idx, 4, QTableWidgetItem(pace_str))

        return table


def run_practice_replay(session, data: dict, title: str = "Practice Session"):
    app = QApplication.instance()
    is_standalone = False
    if app is None:
        app = QApplication(sys.argv)
        is_standalone = True

    win = PracticeSessionWindow(title, data)
    win.show()
    if is_standalone:
        sys.exit(app.exec())
    return win
