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
        
        self.setup_ui()
    
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
            ]
        ))

        content_layout.addWidget(self.create_category_section(
            "Track",
            [
                ("Track Position Map", "Live driver positions on real or circular track map", self.launch_track_position),
            ]
        ))

        content_layout.addWidget(self.create_category_section(
            "Live Data",
            [
                ("Timing Tower", "Live precision gap timing — gap to car ahead and to the leader", self.launch_timing_tower),
                ("Driver Head-to-Head", "Real-time comparative telemetry for two selected drivers", self.launch_head_to_head),
            ]
        ))

        content_layout.addWidget(self.create_category_section(
            "Strategy",
            [
                ("Race Pace Chart", "Lap time progression per driver across the race", self.launch_race_pace),
                ("Undercut Alerts", "Live undercut and overcut opportunity detection log", self.launch_undercut_alerts),
            ]
        ))

        content_layout.addWidget(self.create_category_section(
            "Race Events",
            [
                ("Race Control Feed", "Live FIA flags, penalties, safety car and DRS status", self.launch_race_control_feed),
            ]
        ))

        content_layout.addWidget(self.create_category_section(
            "AI",
            [
                ("Engineer Chat", "Ask the race engineer AI questions about the live race", self.launch_engineer_chat),
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
        
        layout = QVBoxLayout(header)
        
        title = QLabel("🏎️ F1 Insights")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        layout.addWidget(title)
        
        subtitle = QLabel("Launch telemetry insights and analysis tools")
        subtitle.setFont(QFont("Arial", 11))
        layout.addWidget(subtitle)
        
        return header
    
    def create_footer(self):
        footer = QFrame()
        footer.setFrameShape(QFrame.NoFrame)
        
        layout = QHBoxLayout(footer)
        
        info_label = QLabel("Requires telemetry stream enabled")
        info_label.setFont(QFont("Arial", 10))
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        close_btn = QPushButton("Close Menu")
        close_btn.setFixedWidth(100)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        
        return footer
    
    def create_category_section(self, category_name, insights):
        section = QFrame()
        section.setFrameShape(QFrame.NoFrame)
        
        layout = QVBoxLayout(section)
        layout.setSpacing(4)
        
        # Category label
        category_label = QLabel(category_name.upper())
        category_label.setFont(QFont("Arial", 12, QFont.Bold))
        layout.addWidget(category_label)
        
        # Separator line
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
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
        btn_layout.setContentsMargins(4, 4, 4, 4)
        
        name_label = QLabel(name)
        name_label.setFont(QFont("Arial", 12, QFont.Bold))
        
        desc_label = QLabel(description)
        desc_label.setFont(QFont("Arial", 10))
        
        btn_layout.addWidget(name_label)
        btn_layout.addWidget(desc_label)
        
        button.setLayout(btn_layout)
        button.setMinimumHeight(50)
        
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

    def launch_telemetry_viewer(self):
        print("🚀 Launching: Telemetry Stream Viewer")
        try:
            import subprocess
            import sys
            subprocess.Popen([sys.executable, "-m", "src.insights.telemetry_stream_viewer"])
        except Exception as e:
            print(f"Failed to launch telemetry viewer: {e}")
            self.show_placeholder_message("Telemetry Stream Viewer")
    
    def launch_timing_tower(self):
        print("🚀 Launching: Timing Tower")
        from src.insights.timing_tower_window import TimingTowerWindow
        window = TimingTowerWindow()
        window.show()
        self.opened_windows.append(window)

    def launch_head_to_head(self):
        print("🚀 Launching: Driver Head-to-Head")
        from src.insights.head_to_head_window import HeadToHeadWindow
        window = HeadToHeadWindow()
        window.show()
        self.opened_windows.append(window)

    def launch_race_pace(self):
        print("🚀 Launching: Race Pace Chart")
        from src.insights.race_pace_window import RacePaceWindow
        window = RacePaceWindow()
        window.show()
        self.opened_windows.append(window)

    def launch_undercut_alerts(self):
        print("🚀 Launching: Undercut Alerts")
        from src.insights.undercut_alert_window import UndercutAlertWindow
        window = UndercutAlertWindow()
        window.show()
        self.opened_windows.append(window)

    def launch_engineer_chat(self):
        print("🚀 Launching: Engineer Chat")
        from src.insights.engineer_chat_window import EngineerChatWindow
        window = EngineerChatWindow()
        window.show()
        self.opened_windows.append(window)

    def launch_speed_monitor(self):
        print("🚀 Launching: Speed Monitor")
        self.show_placeholder_message("Speed Monitor")
    
    def launch_position_tracker(self):
        print("🚀 Launching: Position Tracker")
        self.show_placeholder_message("Position Tracker")
    
    def launch_tyre_strategy(self):
        print("🚀 Launching: Tyre Strategy")
        self.show_placeholder_message("Tyre Strategy")
    
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
        print("🚀 Launching: Lap Time Evolution")
        self.show_placeholder_message("Lap Time Evolution")
    
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
