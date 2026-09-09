from PySide6.QtWidgets import QMainWindow, QStatusBar, QLabel
from src.services.stream import TelemetryStreamClient


class PitWallWindow(QMainWindow):
    """Base class for F1 insight windows with telemetry streaming and F1 theming."""

    # F1 base stylesheet inherited by all PitWall windows
    F1_BASE_STYLESHEET = """
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
        QStatusBar {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #14142a, stop:1 #0a0a14);
            border-top: 1px solid #1c1c32;
            color: #9898b0;
            font-size: 11px;
        }
        QPushButton {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #22223a, stop:1 #181830);
            color: #e0e0ea;
            border: 1px solid #2e2e48;
            border-radius: 6px;
            padding: 7px 16px;
            font-weight: 600;
        }
        QPushButton:hover {
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 #2e2e4a, stop:1 #242440);
            border: 1px solid #e10600;
            color: #ffffff;
        }
        QPushButton:pressed {
            background: #e10600;
            color: #ffffff;
        }
        QScrollBar:vertical {
            background: rgba(15, 15, 26, 0.6);
            width: 8px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: #3a3a55;
            border-radius: 4px;
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
    """

    def __init__(self):
        super().__init__()
        
        # Default window properties
        self.setGeometry(100, 100, 1000, 700)
        
        # Apply F1 base theme
        self.setStyleSheet(self.F1_BASE_STYLESHEET)
        
        # Data tracking
        self.message_count = 0
        
        # Initialize telemetry client
        self.client = TelemetryStreamClient()
        self.client.data_received.connect(self._handle_data_received)
        self.client.connection_status.connect(self._handle_connection_status)
        self.client.error_occurred.connect(self._handle_error)
        
        # Setup status bar
        self._setup_status_bar()
        
        # Call subclass UI setup
        self.setup_ui()
        
        # Start client
        self.client.start()
    
    def _setup_status_bar(self):
        """Initialize the status bar with connection indicator."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        self.connection_label = QLabel("Disconnected")
        self.status_bar.addPermanentWidget(self.connection_label)
        
        self.messages_label = QLabel("Messages: 0")
        self.status_bar.addPermanentWidget(self.messages_label)
    
    def _handle_data_received(self, data):
        """Internal handler for received telemetry data."""
        self.message_count += 1
        self.messages_label.setText(f"Messages: {self.message_count}")
        
        # Call subclass implementation
        self.on_telemetry_data(data)
    
    def _handle_connection_status(self, status):
        """Internal handler for connection status changes."""
        self.connection_label.setText(f"Status: {status}")
        
        if status == "Connected":
            self.connection_label.setStyleSheet("color: green; font-weight: bold;")
        elif status == "Connecting...":
            self.connection_label.setStyleSheet("color: orange; font-weight: bold;")
        else:
            self.connection_label.setStyleSheet("color: red; font-weight: bold;")
        
        # Notify subclass
        self.on_connection_status_changed(status)
    
    def _handle_error(self, error_msg):
        """Internal handler for stream errors."""
        self.status_bar.showMessage(f"Error: {error_msg}", 5000)
        
        # Notify subclass
        self.on_stream_error(error_msg)
    
    def closeEvent(self, event):
        """Handle window close event - cleanup telemetry client."""
        try:
            if self.client.isRunning():
                self.client.stop()
                if not self.client.wait(2000):  # Wait max 2 seconds
                    print("Warning: Telemetry client did not stop in time")
        except Exception as e:
            print(f"Error during telemetry cleanup: {e}")
        finally:
            event.accept()
    
    # Abstract methods for subclasses to implement
    
    def setup_ui(self):
        """
        Override this method to create your custom UI.
        
        Called during __init__ after the status bar is set up but before
        the telemetry client starts.
        
        Example:
            def setup_ui(self):
                central_widget = QWidget()
                self.setCentralWidget(central_widget)
                layout = QVBoxLayout(central_widget)
                self.data_label = QLabel("Waiting for data...")
                layout.addWidget(self.data_label)
        """
        pass
    
    def on_telemetry_data(self, data):
        """
        Override this method to process incoming telemetry data.
        
        This is called automatically whenever new telemetry data arrives
        from the stream. The data dictionary contains the current frame's
        telemetry information.
        
        Args:
            data: Dictionary containing telemetry data with keys like:
                - frame_index: Current frame number
                - frame: Telemetry frame with driver data
                - track_status: Current track status
                - playback_speed: Current playback speed
                - is_paused: Whether playback is paused
                - total_frames: Total number of frames in session
        
        Example:
            def on_telemetry_data(self, data):
                if 'frame_index' in data:
                    self.frame_label.setText(f"Frame: {data['frame_index']}")
                if 'frame' in data and 'drivers' in data['frame']:
                    driver_count = len(data['frame']['drivers'])
                    self.driver_label.setText(f"Drivers: {driver_count}")
        """
        pass
    
    def on_connection_status_changed(self, status):
        """
        Override this method to respond to connection status changes.
        
        This is called whenever the connection state changes (Connected,
        Connecting..., Disconnected).
        
        Args:
            status: String indicating the current connection state
        
        Example:
            def on_connection_status_changed(self, status):
                if status == "Connected":
                    self.enable_controls()
                else:
                    self.disable_controls()
        """
        pass
    
    def on_stream_error(self, error_msg):
        """
        Override this method to handle stream errors.
        
        This is called when an error occurs during streaming (e.g.,
        connection errors, data parsing errors).
        
        Args:
            error_msg: String describing the error that occurred
        
        Example:
            def on_stream_error(self, error_msg):
                self.error_log.append(f"ERROR: {error_msg}")
        """
        pass
