import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QScrollArea
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


class InsightsMenu(QMainWindow):
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("F1 Insights")
        self.setGeometry(50, 50, 300, 600)
        
        # Keep references to opened windows
        self.opened_windows = []
        
        self._apply_theme()
        self.setup_ui()
    
    def _apply_theme(self):
        """Apply premium F1 dark theme consistent with main launcher."""
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0a0a14, stop:0.5 #0f0f1a, stop:1.0 #08080f);
            }
            QWidget {
                background: transparent;
                color: #e0e0ea;
                font-family: 'Segoe UI', 'Inter', 'Arial', sans-serif;
                font-size: 13px;
            }
            QLabel {
                color: #c8c8d8;
                background: transparent;
            }
            QFrame {
                background: transparent;
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #1e1e36, stop:1 #16162a);
                color: #e0e0ea;
                border: 1px solid #2a2a48;
                border-left: 3px solid #e10600;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #e10600, stop:1 #c00500);
                border: 1px solid #ff3020;
                border-left: 3px solid #ff5040;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #b50500, stop:1 #900400);
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                background: rgba(15, 15, 26, 0.6);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #3a3a55;
                border-radius: 3px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover {
                background: #e10600;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QMessageBox {
                background-color: #0a0a14;
                color: #e0e0e0;
            }
        """)
    
    def setup_ui(self):
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header
        header = self.create_header()
        main_layout.addWidget(header)
        
        # Scrollable content area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(2)
        content_layout.setContentsMargins(10, 10, 10, 10)
        
        # Add insight categories

        content_layout.addWidget(self.create_category_section(
            "Example Insights",
            [
                ("Example Insight Window", "Launch an example insight window", self.launch_example_window),
            ]
        ))

        content_layout.addWidget(self.create_category_section(
            "Live Telemetry",
            [
                ("Telemetry Stream Viewer", "View raw telemetry data", self.launch_telemetry_viewer),
                ("Driver Live Telemetry", "Speed, gear, throttle & braking for a selected driver", self.launch_driver_telemetry),
                ("Live Tyre Strategy", "Live tyre stints and pit stop timeline per driver", self.launch_tyre_strategy),
            ]
        ))

        content_layout.addWidget(self.create_category_section(
            "Track",
            [
                ("Track Position Map", "Live driver positions on real or circular track map", self.launch_track_position),
            ]
        ))

        content_layout.addWidget(self.create_category_section(
            "Race Events",
            [
                ("Race Control Feed", "Live FIA flags, penalties, safety car and DRS status", self.launch_race_control_feed),
            ]
        ))

        content_layout.addWidget(self.create_category_section(
            "Race Analysis",
            [
                ("Lap Time & Gap Evolution", "Lap time and gap trends per driver", self.launch_lap_time_chart),
            ]
        ))
        
        content_layout.addStretch()
        
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        # Footer
        footer = self.create_footer()
        main_layout.addWidget(footer)
    
    def create_header(self):
        header = QFrame()
        header.setFrameShape(QFrame.NoFrame)
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(225, 6, 0, 0.15), stop:1 transparent);
                border-bottom: 2px solid #e10600;
                padding: 12px;
            }
        """)
        
        layout = QVBoxLayout(header)
        
        title = QLabel("🏎️ F1 INSIGHTS")
        title.setFont(QFont("Segoe UI", 22, QFont.Bold))
        title.setStyleSheet("color: #ffffff; letter-spacing: 2px;")
        layout.addWidget(title)
        
        subtitle = QLabel("Launch telemetry insights and analysis tools")
        subtitle.setFont(QFont("Segoe UI", 11))
        subtitle.setStyleSheet("color: #9898b0;")
        layout.addWidget(subtitle)
        
        return header
    
    def create_footer(self):
        footer = QFrame()
        footer.setFrameShape(QFrame.NoFrame)
        footer.setStyleSheet("""
            QFrame {
                border-top: 1px solid #1c1c32;
                padding: 8px;
            }
        """)
        
        layout = QHBoxLayout(footer)
        
        info_label = QLabel("Requires telemetry stream enabled")
        info_label.setFont(QFont("Segoe UI", 10))
        info_label.setStyleSheet("color: #6868880;")
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        close_btn = QPushButton("Close Menu")
        close_btn.setFixedWidth(110)
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #e10600;
                color: #e10600;
                border-left: 1px solid #e10600;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #e10600;
                color: #ffffff;
                border-left: 1px solid #e10600;
            }
        """)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        return footer
    
    def create_category_section(self, category_name, insights):
        section = QFrame()
        section.setFrameShape(QFrame.NoFrame)
        
        layout = QVBoxLayout(section)
        layout.setSpacing(6)
        
        # Category label with F1 styling
        category_label = QLabel(category_name.upper())
        category_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
        category_label.setStyleSheet("""
            color: #e10600;
            letter-spacing: 1.5px;
            padding: 4px 0px;
        """)
        layout.addWidget(category_label)
        
        # Separator line with F1 red accent
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #e10600, stop:0.3 #40102a, stop:1 transparent);
                max-height: 2px;
                min-height: 2px;
            }
        """)
        layout.addWidget(separator)
        
        # Add insight buttons
        for name, description, callback in insights:
            btn = self.create_insight_button(name, description, callback)
            layout.addWidget(btn)
        
        return section
    
    def create_insight_button(self, name, description, callback):
        button = QPushButton()
        button.setCursor(Qt.PointingHandCursor)
        
        # Create button layout with name and description
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(2)
        btn_layout.setContentsMargins(8, 6, 8, 6)
        
        name_label = QLabel(name)
        name_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        name_label.setStyleSheet("color: #e8e8f0;")
        
        desc_label = QLabel(description)
        desc_label.setFont(QFont("Segoe UI", 10))
        desc_label.setStyleSheet("color: #8888a0;")
        
        btn_layout.addWidget(name_label)
        btn_layout.addWidget(desc_label)
        
        button.setLayout(btn_layout)
        button.setMinimumHeight(54)
        
        # Connect callback
        button.clicked.connect(callback)
        
        return button
    
    # Insight launch methods (placeholders for now)
    
    def launch_example_window(self):
        print("🚀 Launching: Example Insight Window")
        # Open the Example PitWallWindow
        from src.insights.example_pit_wall_window import ExamplePitWallWindow
        example_window = ExamplePitWallWindow()
        example_window.show()
        # Keep reference to prevent garbage collection
        self.opened_windows.append(example_window)

    def launch_driver_telemetry(self):
        print("🚀 Launching: Driver Live Telemetry")
        from src.insights.driver_telemetry_window import DriverTelemetryWindow
        window = DriverTelemetryWindow()
        window.show()
        self.opened_windows.append(window)

    def launch_track_position(self):
        print("🚀 Launching: Track Position Map")
        from src.insights.track_position_window import TrackPositionWindow
        window = TrackPositionWindow()
        window.show()
        self.opened_windows.append(window)

    def launch_race_control_feed(self):
        print("🚀 Launching: Race Control Feed")
        from src.insights.race_control_feed_window import RaceControlFeedWindow
        window = RaceControlFeedWindow()
        window.show()
        self.opened_windows.append(window)

    def launch_lap_time_chart(self):
        print("🚀 Launching: Lap Time & Gap Evolution")
        from src.insights.lap_time_chart_window import LapTimeChartWindow
        window = LapTimeChartWindow()
        window.show()
        self.opened_windows.append(window)

    def launch_telemetry_viewer(self):
        print("🚀 Launching: Telemetry Stream Viewer")
        try:
            import subprocess
            import sys
            subprocess.Popen([sys.executable, "-m", "src.insights.telemetry_stream_viewer"])
        except Exception as e:
            print(f"Failed to launch telemetry viewer: {e}")
            self.show_placeholder_message("Telemetry Stream Viewer")
    
    def launch_speed_monitor(self):
        print("🚀 Launching: Speed Monitor")
        self.show_placeholder_message("Speed Monitor")
    
    def launch_position_tracker(self):
        print("🚀 Launching: Position Tracker")
        self.show_placeholder_message("Position Tracker")
    
    def launch_tyre_strategy(self):
        print("🚀 Launching: Live Tyre Strategy")
        from src.insights.tyre_strategy_window import TyreStrategyWindow
        window = TyreStrategyWindow()
        window.show()
        self.opened_windows.append(window)
    
    def launch_pit_analysis(self):
        print("🚀 Launching: Pit Stop Analysis")
        self.show_placeholder_message("Pit Stop Analysis")
    
    def launch_gap_analysis(self):
        print("🚀 Launching: Gap Analysis")
        self.show_placeholder_message("Gap Analysis")
    
    def launch_sector_times(self):
        print("🚀 Launching: Sector Times")
        self.show_placeholder_message("Sector Times")
    
    def launch_lap_evolution(self):
        print("🚀 Launching: Lap Time & Gap Evolution")
        self.show_placeholder_message("Lap Time & Gap Evolution")
    
    def launch_top_speed(self):
        print("🚀 Launching: Top Speed Tracker")
        self.show_placeholder_message("Top Speed Tracker")
    
    def launch_flag_tracker(self):
        print("🚀 Launching: Flag Tracker")
        self.show_placeholder_message("Flag Tracker")
    
    def launch_overtake_counter(self):
        print("🚀 Launching: Overtake Counter")
        self.show_placeholder_message("Overtake Counter")
    
    def launch_drs_usage(self):
        print("🚀 Launching: DRS Usage")
        self.show_placeholder_message("DRS Usage")
    
    def show_placeholder_message(self, insight_name):
        from PySide6.QtWidgets import QMessageBox
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Coming Soon")
        msg.setIcon(QMessageBox.Information)
        msg.setText(f"{insight_name} will be available soon!")
        msg.setInformativeText(
            "This insight is planned for a future release.\n\n"
            "Developers can use PitWallWindow to create custom insights.\n"
            "See docs/PitWallWindow.md for more information."
        )
        msg.setStandardButtons(QMessageBox.Ok)
        msg.exec()


def launch_insights_menu():
    # Check if QApplication instance already exists
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    menu = InsightsMenu()
    menu.show()
    
    return menu


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("F1 Insights Menu")
    
    menu = InsightsMenu()
    menu.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
