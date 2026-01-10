import sys
import os
import subprocess
import tempfile
import urllib.request
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QMessageBox,
    QLineEdit, QHeaderView
)
from PySide6.QtCore import QThread, Signal, Qt, QSize
from PySide6.QtGui import QFont, QIcon

# Ensure your f1_data module is accessible
try:
    from src.f1_data import get_race_weekends_by_year
except ImportError:
    def get_race_weekends_by_year(year): return []

# --- Background Flag Loader ---
class FlagLoaderWorker(QThread):
    flag_ready = Signal(str, str)

    def __init__(self, countries):
        super().__init__()
        self.countries = set(countries)
        self.flag_dir = os.path.join(tempfile.gettempdir(), "f1_flags_v4")
        if not os.path.exists(self.flag_dir):
            os.makedirs(self.flag_dir)

    def run(self):
        overrides = {
            "UAE": "ae", "USA": "us", "UK": "gb", "Great Britain": "gb",
            "United States": "us", "Russia": "ru", "Korea": "kr", "Japan": "jp",
            "Netherlands": "nl", "Saudi Arabia": "sa"
        }
        for name in self.countries:
            if not name: continue
            code = overrides.get(name, name[:2].lower()) 
            path = os.path.join(self.flag_dir, f"{code}.png")
            if not os.path.exists(path):
                try:
                    url = f"https://flagcdn.com/w40/{code}.png"
                    urllib.request.urlretrieve(url, path)
                except: continue
            self.flag_ready.emit(name, path)

# --- Fetch Schedule Worker ---
class FetchScheduleWorker(QThread):
    result = Signal(object)
    error = Signal(str)

    def __init__(self, year):
        super().__init__()
        self.year = year

    def run(self):
        try:
            events = get_race_weekends_by_year(self.year)
            self.result.emit(events)
        except Exception as e:
            self.error.emit(str(e))

class RaceSelectionWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.selected_year = 2025
        self.setWindowTitle("F1 Race Replay - Session Selection")
        self.resize(1200, 800)
        
        self.setStyleSheet("""
            QMainWindow { background-color: #0f0f0f; }
            QLabel { color: #ffffff; }
            QLineEdit { 
                background-color: #1a1a1a; color: white; border: 1px solid #333; 
                border-radius: 4px; padding: 12px; font-size: 14px;
            }
            QPushButton {
                background-color: #1e1e1e; border: 1px solid #333; border-radius: 6px;
                padding: 10px; color: white; font-weight: bold;
            }
            QPushButton:hover { background-color: #e10600; border-color: #e10600; }
            QTreeWidget { 
                background-color: #151515; border: 1px solid #222; color: white; 
                outline: none; alternate-background-color: #1a1a1a; font-size: 13px;
            }
            QTreeWidget::item { padding: 12px; border-bottom: 1px solid #1f1f1f; }
            QTreeWidget::item:selected { background-color: #e10600; color: white; }
            QHeaderView::section { 
                background-color: #0f0f0f; color: #888; padding: 10px; border: none;
                font-weight: bold; text-transform: uppercase; font-size: 11px;
            }
        """)

        self._setup_ui()
        self.load_schedule(self.selected_year)

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Header Area
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("F1 REPLAY ARCHIVE")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        subtitle = QLabel("Select a season and session to begin playback")
        subtitle.setStyleSheet("color: #666; font-size: 12px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header_layout.addLayout(title_box)
        
        # Year selection row
        year_box = QHBoxLayout()
        for y in range(2018, 2026):
            btn = QPushButton(str(y))
            btn.setFixedWidth(65)
            btn.setCheckable(True)
            if y == self.selected_year: btn.setChecked(True)
            btn.clicked.connect(lambda _, yr=y: self._on_year_clicked(yr))
            year_box.addWidget(btn)
        header_layout.addLayout(year_box)
        layout.addLayout(header_layout)

        # Main Layout: List and Session Panel
        content = QHBoxLayout()
        content.setSpacing(25)

        left_col = QVBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("🔍 Search Grand Prix or Country...")
        self.search_bar.textChanged.connect(self._filter_schedule)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["RD", "EVENT", "COUNTRY", "DATE"])
        self.tree.setIconSize(QSize(24, 16))
        
        # UI FIX: SMART COLUMN SIZING
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # RD
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)           # Event fills space
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) # Full Country Name
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) # Date
        
        self.tree.itemClicked.connect(self.on_race_clicked)
        left_col.addWidget(self.search_bar)
        left_col.addWidget(self.tree)
        content.addLayout(left_col, 3)

        # Session Panel (Right Sidebar)
        self.session_panel = QWidget()
        self.session_panel.setFixedWidth(280)
        self.session_panel.setStyleSheet("background-color: #121212; border-radius: 8px;")
        self.session_layout = QVBoxLayout(self.session_panel)
        self.session_layout.setContentsMargins(20, 25, 20, 25)
        
        panel_label = QLabel("AVAILABLE SESSIONS")
        panel_label.setStyleSheet("color: #e10600; font-size: 11px; font-weight: bold; letter-spacing: 1px;")
        self.session_layout.addWidget(panel_label)
        
        self.session_buttons_container = QVBoxLayout()
        self.session_buttons_container.setSpacing(10)
        self.session_layout.addLayout(self.session_buttons_container)
        
        self.session_layout.addStretch()
        content.addWidget(self.session_panel)
        self.session_panel.hide()
        layout.addLayout(content)

    def _on_year_clicked(self, year):
        self.selected_year = year
        self.load_schedule(year)

    def load_schedule(self, year):
        self.tree.clear()
        self.session_panel.hide()
        self.worker = FetchScheduleWorker(year)
        self.worker.result.connect(self.populate_schedule)
        self.worker.start()

    def populate_schedule(self, events):
        countries = []
        for event in events:
            country = event.get("country", "")
            countries.append(country)
            item = QTreeWidgetItem([
                str(event.get("round_number", "")),
                event.get("event_name", ""),
                country,
                str(event.get("date", ""))
            ])
            item.setData(0, Qt.UserRole, event)
            item.setData(2, Qt.UserRole, country)
            self.tree.addTopLevelItem(item)
        
        self.flag_worker = FlagLoaderWorker(countries)
        self.flag_worker.flag_ready.connect(self._update_flag)
        self.flag_worker.start()

    def _update_flag(self, country, path):
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.data(2, Qt.UserRole) == country:
                item.setIcon(2, QIcon(path))

    def _filter_schedule(self, text):
        query = text.lower()
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            match = query in item.text(1).lower() or query in item.text(2).lower()
            item.setHidden(not match)

    def on_race_clicked(self, item):
        ev = item.data(0, Qt.UserRole)
        self.session_panel.show()
        
        while self.session_buttons_container.count():
            child = self.session_buttons_container.takeAt(0)
            if child.widget(): child.widget().deleteLater()

        sessions = ["Qualifying", "Race"]
        if 'sprint' in (ev.get('type') or '').lower():
            sessions = ["Sprint Qualifying", "Sprint", "Qualifying", "Race"]

        for s in sessions:
            btn = QPushButton(f"{self._get_icon(s)}  {s.upper()}")
            btn.setMinimumHeight(55)
            btn.clicked.connect(lambda _, sn=s, e=ev: self._start_replay(e, sn))
            self.session_buttons_container.addWidget(btn)

    def _get_icon(self, s):
        return {"Qualifying": "⏱️", "Sprint Qualifying": "⚡", "Sprint": "🔥", "Race": "🏁"}.get(s, "🏎️")

    def _start_replay(self, event_data, session_name):
        year = self.selected_year
        round_no = event_data.get("round_number")
        
        try:
            cmd = [
                sys.executable, "main.py", 
                "--year", str(year), 
                "--round", str(round_no), 
                "--session", session_name
            ]
            subprocess.Popen(cmd)
            print(f"Launched: {year} RD {round_no} {session_name}")
            
        except Exception as e:
            QMessageBox.critical(self, "Launch Error", f"Could not start replay: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = RaceSelectionWindow()
    window.show()
    sys.exit(app.exec())
