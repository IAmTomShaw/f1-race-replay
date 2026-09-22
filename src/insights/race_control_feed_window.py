"""
Race Control Feed insight window.

Displays FIA race control messages (flags, penalties, safety car,
DRS, investigations) as a scrolling feed synced to replay time.
"""

import sys
import math
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QTextBrowser
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor
from src.gui.pit_wall_window import PitWallWindow


# ── Colour palette (matches the app's existing dark theme) ────────────────
_BG           = "#282828"
_BG_DARKER    = "#1E1E1E"
_BORDER       = "#3A3A3A"
_TEXT_PRIMARY  = "#E0E0E0"
_TEXT_DIMMED   = "#888888"
_TEXT_TIME     = "#999999"

# Category accent colours (used for the left-edge indicator bar)
_CAT_COLOURS = {
    "Flag":      "#FFD700",   # amber/gold
    "SafetyCar": "#FF8C00",   # orange
    "Drs":       "#00CED1",   # cyan
    "Other":     "#666666",   # subtle grey
    "CarEvent":  "#B0B0B0",   # light grey
}

# Flag-specific overrides for the accent colour
_FLAG_COLOURS = {
    "YELLOW":         "#FFD700",
    "DOUBLE YELLOW":  "#FFD700",
    "RED":            "#E74C3C",
    "GREEN":          "#2ECC71",
    "CHEQUERED":      "#F0F0F0",
    "BLUE":           "#3498DB",
    "BLACK AND WHITE":"#B0B0B0",
    "BLACK AND ORANGE":"#FF8C00",
    "CLEAR":          "#2ECC71",
}


def _format_time(seconds):
    """Convert seconds to HH:MM:SS string."""
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02}:{m:02}:{s:02}"


def _accent_for_event(event):
    """Return accent hex colour for a race control event."""
    flag = event.get("flag", "")
    category = event.get("category", "Other")

    if flag and flag in _FLAG_COLOURS:
        return _FLAG_COLOURS[flag]

    return _CAT_COLOURS.get(category, _CAT_COLOURS["Other"])


def _clean_sector(val):
    """Return a clean sector string, or empty if NaN / empty."""
    if not val:
        return ""
    try:
        f = float(val)
        if math.isnan(f):
            return ""
        return str(int(f))
    except (ValueError, TypeError):
        return str(val)


# ── State labels ──────────────────────────────────────────────────────────
_WAITING_TEXT = "Waiting for race control messages..."
_NO_DATA_TEXT = (
    "No race control data in cache.\n\n"
    "Delete the .pkl file in computed_data/\n"
    "and re-run the session to regenerate."
)


class RaceControlFeedWindow(PitWallWindow):
    """Scrolling feed of FIA race control messages synced to the replay."""

    def __init__(self):
        self._seen_hashes = set()
        self._state = "init"  # "init" | "waiting" | "no_data" | "active"
        self._last_frame_index = -1
        super().__init__()
        self.setWindowTitle("Race Control Feed")
        self.setGeometry(120, 120, 420, 620)

    def setup_ui(self):
        central = QWidget()
        central.setStyleSheet(f"background: {_BG};")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header bar
        header = QWidget()
        header.setStyleSheet(
            f"background: {_BG_DARKER}; border-bottom: 1px solid {_BORDER};"
        )
        header.setFixedHeight(56)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(14, 8, 14, 8)
        header_layout.setSpacing(2)

        title = QLabel("RACE CONTROL")
        title.setFont(QFont("Arial", 13, QFont.Bold))
        title.setStyleSheet(f"color: {_TEXT_PRIMARY}; border: none;")
        header_layout.addWidget(title)

        self._status_line = QLabel("Waiting for data...")
        self._status_line.setFont(QFont("Arial", 10))
        self._status_line.setStyleSheet(f"color: {_TEXT_DIMMED}; border: none;")
        header_layout.addWidget(self._status_line)

        root.addWidget(header)

        # Event list
        self._text_browser = QTextBrowser()
        self._text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background: {_BG};
                color: {_TEXT_PRIMARY};
                border: none;
                outline: none;
            }}
            QScrollBar:vertical {{
                border: none;
                background: {_BG};
                width: 12px;
                margin: 0px;
            }}
            QScrollBar::handle:vertical {{
                background: {_BORDER};
                min-height: 20px;
                border-radius: 4px;
                margin: 2px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: #555555;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
                border: none;
                background: none;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: none;
            }}
        """)
        self._text_browser.setOpenExternalLinks(False)
        self._text_browser.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._text_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self._text_browser, stretch=1)

        # State label (waiting / no-data messages)
        self._state_label = QLabel(_WAITING_TEXT)
        self._state_label.setFont(QFont("Arial", 11))
        self._state_label.setStyleSheet(
            f"color: {_TEXT_DIMMED}; padding: 32px; background: {_BG};"
        )
        self._state_label.setAlignment(Qt.AlignCenter)
        self._state_label.setWordWrap(True)
        root.addWidget(self._state_label)

        # Start with list hidden and state label shown
        self._text_browser.hide()

    def _set_state(self, state):
        """Transition between init/waiting/no_data/active states."""
        if state == self._state:
            return
        self._state = state

        if state == "active":
            self._state_label.hide()
            self._text_browser.show()
        elif state == "waiting":
            self._state_label.setText(_WAITING_TEXT)
            self._state_label.show()
            self._text_browser.hide()
        elif state == "no_data":
            self._state_label.setText(_NO_DATA_TEXT)
            self._state_label.show()
            self._text_browser.hide()

    def on_telemetry_data(self, data):
        # Update header status line
        session_data = data.get("session_data", {})
        if session_data:
            time_str = session_data.get("time", "")
            lap = session_data.get("lap", "")
            total = session_data.get("total_laps", "")
            lap_text = f"Lap {lap}/{total}" if total else f"Lap {lap}"
            self._status_line.setText(f"{lap_text}  ·  {time_str}")
            self._status_line.setStyleSheet(f"color: {_TEXT_DIMMED}; border: none;")

        # Detect rewinds or restarts to flush the feed
        frame_idx = data.get("frame_index", -1)
        if frame_idx >= 0 and self._last_frame_index >= 0 and frame_idx < self._last_frame_index:
            self._seen_hashes.clear()
            self._text_browser.clear()
            self._set_state("init")
        self._last_frame_index = frame_idx

        # Determine state from the has_rc_data flag (sent by the replay)
        has_rc_data = data.get("has_rc_data")
        if has_rc_data is not None and self._state in ("init", "waiting", "no_data"):
            if has_rc_data:
                self._set_state("waiting")
            else:
                self._set_state("no_data")

        # Process race control events
        events = data.get("race_control_events", [])
        for event in events:
            event_hash = f"{event['time']}|{event['message']}"
            if event_hash in self._seen_hashes:
                continue
            self._seen_hashes.add(event_hash)

            if self._state != "active":
                self._set_state("active")

            self._add_event_item(event)

    def _add_event_item(self, event):
        """Append a formatted event to the text browser."""
        icon_color = _accent_for_event(event)
        time_str = _format_time(event["time"])
        message = event.get("message", "")
        sector = _clean_sector(event.get("sector", ""))
        
        sector_html = f'<br><span style="color: {_TEXT_DIMMED}; font-size: 11px;">Sector {sector}</span>' if sector else ""
        
        # We use a reliable HTML table structure to render the color accent bar
        # alongside the text content inside the QTextBrowser.
        html = f"""
        <table width="100%" cellspacing="0" cellpadding="8" style="background: {_BG};">
            <tr>
                <td width="3" style="background-color: {icon_color}; padding: 0;"></td>
                <td width="85" style="border-bottom: 1px solid {_BORDER}; vertical-align: top; padding-left: 10px; white-space: nowrap;">
                    <span style="color: {_TEXT_TIME}; font-family: Consolas; font-size: 12px;">{time_str}</span>
                </td>
                <td style="border-bottom: 1px solid {_BORDER}; vertical-align: top;">
                    <span style="color: {_TEXT_PRIMARY}; font-family: Arial; font-size: 14px;">{message}</span>
                    {sector_html}
                </td>
            </tr>
        </table>
        """
        
        self._text_browser.append(html)
        
        # Scroll to bottom
        scrollbar = self._text_browser.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def on_connection_status_changed(self, status):
        if status == "Disconnected":
            self._status_line.setText("Disconnected")
            self._status_line.setStyleSheet(f"color: #E74C3C; border: none;")
        elif status == "Connecting...":
            self._status_line.setText("Connecting...")
            self._status_line.setStyleSheet(f"color: #FF8C00; border: none;")


# ──────────────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Race Control Feed")
    window = RaceControlFeedWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
