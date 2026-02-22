import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, 
    QTextEdit, QGroupBox
)
from PySide6.QtGui import QFont
from src.gui.pit_wall_window import PitWallWindow


class ExamplePitWallWindow(PitWallWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("F1 Race Replay - Example Pit Wall")
    
    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        layout = QVBoxLayout(central_widget)
        
        # Session info group
        session_group = QGroupBox("Session Information")
        session_layout = QVBoxLayout(session_group)
        
        self.frame_label = QLabel("Frame: -")
        self.frame_label.setFont(QFont("Arial", 14))
        session_layout.addWidget(self.frame_label)
        
        self.drivers_label = QLabel("Active Drivers: -")
        self.drivers_label.setFont(QFont("Arial", 14))
        session_layout.addWidget(self.drivers_label)
        
        self.track_status_label = QLabel("Track Status: -")
        self.track_status_label.setFont(QFont("Arial", 14))
        session_layout.addWidget(self.track_status_label)
        
        self.playback_label = QLabel("Playback: -")
        self.playback_label.setFont(QFont("Arial", 14))
        session_layout.addWidget(self.playback_label)
        
        layout.addWidget(session_group)
        
        # Driver details
        drivers_group = QGroupBox("Driver Details")
        drivers_layout = QVBoxLayout(drivers_group)
        
        self.drivers_text = QTextEdit()
        self.drivers_text.setFont(QFont("Courier", 10))
        self.drivers_text.setReadOnly(True)
        drivers_layout.addWidget(self.drivers_text)
        
        layout.addWidget(drivers_group)
    
    def on_telemetry_data(self, data):
        # Update frame info
        if 'frame_index' in data:
            frame_text = f"Frame: {data['frame_index']}"
            if 'total_frames' in data:
                frame_text += f" / {data['total_frames']}"
            self.frame_label.setText(frame_text)
        
        # Update track status
        if 'track_status' in data:
            self.track_status_label.setText(f"Track Status: {data['track_status']}")
        
        # Update playback state
        if 'playback_speed' in data and 'is_paused' in data:
            state = "PAUSED" if data['is_paused'] else "PLAYING"
            self.playback_label.setText(f"Playback: {state} ({data['playback_speed']}x)")
        
        # Update driver information
        if 'frame' in data and data['frame'] and 'drivers' in data['frame']:
            drivers_data = data['frame']['drivers']
            self.drivers_label.setText(f"Active Drivers: {len(drivers_data)}")
            
            # Format driver details
            driver_lines = []
            for code, driver_info in sorted(drivers_data.items()):
                line_parts = [f"{code}:"]
                
                if 'lap' in driver_info:
                    line_parts.append(f"Lap {driver_info['lap']}")
                
                if 'speed' in driver_info:
                    line_parts.append(f"{driver_info['speed']:.0f} km/h")
                
                if 'dist' in driver_info:
                    line_parts.append(f"{driver_info['dist']:.0f}m")
                
                driver_lines.append("  ".join(line_parts))
            
            self.drivers_text.setText('\n'.join(driver_lines))
    
    def on_connection_status_changed(self, status):
        if status == "Connected":
            self.frame_label.setText("Frame: Waiting for data...")
        elif status == "Disconnected":
            self.frame_label.setText("Frame: Disconnected")
    
    def on_stream_error(self, error_msg):
        # Errors are already shown in the status bar by the base class
        # You can add additional error handling here if needed
        pass


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Example Pit Wall")
    
    window = ExamplePitWallWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
