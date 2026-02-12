import sys
import json
from datetime import datetime
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, 
    QTextEdit, QLabel, QStatusBar, QSplitter, QListWidget,
    QTabWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from src.services.stream import TelemetryStreamClient

class TelemetryStreamViewer(QMainWindow):
    # This window is used to demonstrate the telemetry stream data being sent from the replay process. It connects to the telemetry stream server, receives real-time telemetry data, and displays it in a simple UI for debugging and demonstration purposes.
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("F1 Race Replay - Telemetry Stream Viewer")
        self.setGeometry(100, 100, 1200, 800)
        
        # Initialize client
        self.client = TelemetryStreamClient()
        self.client.data_received.connect(self.on_data_received)
        self.client.connection_status.connect(self.on_connection_status)
        self.client.error_occurred.connect(self.on_error)
        
        # Data tracking
        self.message_count = 0
        self.last_frame_index = -1
        self.drivers_seen = set()
        
        # Setup UI
        self.setup_ui()
        self.setup_status_bar()
        
        # Start client
        self.client.start()
        
    def setup_ui(self):
        """Create the main UI layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        
        # Create splitter for main content
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left panel - Raw data log
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        
        left_layout.addWidget(QLabel("Raw Telemetry Stream:"))
        self.raw_log = QTextEdit()
        self.raw_log.setFont(QFont("Courier", 10))
        left_layout.addWidget(self.raw_log)
        
        # Right panel - Parsed data
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        
        # Tabs for different data views
        self.tab_widget = QTabWidget()
        right_layout.addWidget(self.tab_widget)
        
        self.setup_summary_tab()
        self.setup_drivers_tab()
        self.setup_events_tab()
        
        # Add widgets to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([600, 600])  # Equal split
        
    def setup_summary_tab(self):
        """Create summary tab showing session overview."""
        summary_widget = QWidget()
        layout = QVBoxLayout(summary_widget)
        
        self.summary_text = QTextEdit()
        self.summary_text.setFont(QFont("Courier", 11))
        self.summary_text.setMaximumHeight(200)
        layout.addWidget(QLabel("Session Summary:"))
        layout.addWidget(self.summary_text)
        
        # Recent messages
        layout.addWidget(QLabel("Recent Raw Messages:"))
        self.recent_messages = QListWidget()
        layout.addWidget(self.recent_messages)
        
        self.tab_widget.addTab(summary_widget, "Summary")
        
    def setup_drivers_tab(self):
        """Create drivers tab showing driver positions and data."""
        drivers_widget = QWidget()
        layout = QVBoxLayout(drivers_widget)
        
        layout.addWidget(QLabel("Driver Positions & Data:"))
        self.drivers_text = QTextEdit()
        self.drivers_text.setFont(QFont("Courier", 10))
        layout.addWidget(self.drivers_text)
        
        self.tab_widget.addTab(drivers_widget, "Drivers")
        
    def setup_events_tab(self):
        """Create events tab showing track status and race events."""
        events_widget = QWidget()
        layout = QVBoxLayout(events_widget)
        
        layout.addWidget(QLabel("Track Status & Race Events:"))
        self.events_list = QListWidget()
        layout.addWidget(self.events_list)
        
        self.tab_widget.addTab(events_widget, "Events")
        
    def setup_status_bar(self):
        """Create status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.connection_label = QLabel("Disconnected")
        self.messages_label = QLabel("Messages: 0")
        self.frame_label = QLabel("Frame: -")
        
        self.status_bar.addPermanentWidget(self.connection_label)
        self.status_bar.addPermanentWidget(self.messages_label)
        self.status_bar.addPermanentWidget(self.frame_label)
        
    def on_data_received(self, data):
        """Handle incoming telemetry data."""
        self.message_count += 1
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        
        # Update raw log
        json_str = json.dumps(data, indent=2)
        log_entry = f"[{timestamp}] Message #{self.message_count}\n{json_str}\n{'='*50}\n"
        self.raw_log.append(log_entry)
        
        # Auto-scroll to bottom
        cursor = self.raw_log.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.raw_log.setTextCursor(cursor)
            
        # Update summary
        self.update_summary(data)
        
        # Update drivers view
        self.update_drivers_view(data)
        
        # Update events view
        self.update_events_view(data)
        
        # Update status bar
        self.messages_label.setText(f"Messages: {self.message_count}")
        if 'frame_index' in data:
            self.frame_label.setText(f"Frame: {data['frame_index']}")
            self.last_frame_index = data['frame_index']
            
    def update_summary(self, data):
        """Update the summary tab with session information."""
        # Add to recent messages list
        summary_line = f"Frame {data.get('frame_index', '?')}: "
        if 'frame' in data and data['frame']:
            summary_line += f"Time {data['frame'].get('t', '?')}s"
        if 'track_status' in data:
            summary_line += f" | Status: {data['track_status']}"
        if 'playback_speed' in data:
            summary_line += f" | Speed: {data['playback_speed']}x"
        if 'is_paused' in data:
            summary_line += f" | {'PAUSED' if data['is_paused'] else 'PLAYING'}"
            
        self.recent_messages.insertItem(0, summary_line)
        if self.recent_messages.count() > 20:
            self.recent_messages.takeItem(self.recent_messages.count() - 1)
            
        # Update summary text
        summary_info = []
        summary_info.append(f"Total Messages Received: {self.message_count}")
        summary_info.append(f"Current Frame: {self.last_frame_index}")
        summary_info.append(f"Drivers Seen: {len(self.drivers_seen)}")
        
        if 'total_frames' in data:
            summary_info.append(f"Total Frames: {data['total_frames']}")
        if 'track_status' in data:
            summary_info.append(f"Track Status: {data['track_status']}")
        if 'playback_speed' in data:
            summary_info.append(f"Playback Speed: {data['playback_speed']}x")
        if 'is_paused' in data:
            summary_info.append(f"Playback State: {'PAUSED' if data['is_paused'] else 'PLAYING'}")
            
        self.summary_text.setText('\n'.join(summary_info))
        
    def update_drivers_view(self, data):
        """Update the drivers tab with current driver data."""
        if 'frame' not in data or not data['frame'] or 'drivers' not in data['frame']:
            return
            
        drivers_data = data['frame']['drivers']
        drivers_info = []
        
        for code, driver_data in drivers_data.items():
            self.drivers_seen.add(code)
            
            line = f"{code}: "
            if 'x' in driver_data and 'y' in driver_data:
                line += f"Pos({driver_data['x']:.1f}, {driver_data['y']:.1f}) "
            if 'speed' in driver_data:
                line += f"Speed({driver_data['speed']:.1f}km/h) "
            if 'lap' in driver_data:
                line += f"Lap({driver_data['lap']}) "
            if 'dist' in driver_data:
                line += f"Dist({driver_data['dist']:.1f}m)"
                
            drivers_info.append(line)
            
        self.drivers_text.setText('\n'.join(sorted(drivers_info)))
        
    def update_events_view(self, data):
        """Update the events tab with track status changes."""
        if 'track_status' in data:
            timestamp = datetime.now().strftime("%H:%M:%S")
            event_text = f"[{timestamp}] Track Status: {data['track_status']}"
            if 'frame_index' in data:
                event_text += f" (Frame {data['frame_index']})"
            
            # Only add if it's a change or first message
            if self.events_list.count() == 0:
                self.events_list.insertItem(0, event_text)
            else:
                last_item = self.events_list.item(0)
                if last_item and data['track_status'] not in last_item.text():
                    self.events_list.insertItem(0, event_text)
                    
            # Keep only recent events
            while self.events_list.count() > 100:
                self.events_list.takeItem(self.events_list.count() - 1)
                
    def on_connection_status(self, status):
        """Handle connection status updates."""
        self.connection_label.setText(f"Status: {status}")
        if status == "Connected":
            self.connection_label.setStyleSheet("color: green; font-weight: bold;")
        elif status == "Connecting...":
            self.connection_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.connection_label.setStyleSheet("color: red; font-weight: bold;")
            
    def on_error(self, error_msg):
        """Handle error messages."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        error_entry = f"[{timestamp}] ERROR: {error_msg}\n"
        self.raw_log.append(error_entry)
        self.status_bar.showMessage(f"Error: {error_msg}", 5000)
        
    def closeEvent(self, event):
        """Handle window close event."""
        if self.client.isRunning():
            self.client.stop()
            self.client.wait()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Telemetry Stream Viewer")
    
    # Create and show main window
    viewer = TelemetryStreamViewer()
    viewer.show()
    
    # Run the application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()