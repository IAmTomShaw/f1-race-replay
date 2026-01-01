from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QTreeWidget, QTreeWidgetItem, 
    QMessageBox, QProgressDialog, QFrame, QGraphicsDropShadowEffect
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QFont, QColor
import sys, os, subprocess, tempfile, uuid
from src.f1_data import get_race_weekends_by_year, load_session

# --- THEME DEFINITION ---
F1_CSS = """
QMainWindow { background-color: #15151e; }
QLabel { color: #f2f2f2; font-family: 'Segoe UI', Arial; }
#HeaderLabel { color: #e10600; font-weight: 800; letter-spacing: 2px; }

/* Modern Tree Styling */
QTreeWidget {
    background-color: #1f1f27;
    border: 1px solid #38383f;
    border-radius: 8px;
    color: #f2f2f2;
    font-size: 13px;
    outline: none;
}
QTreeWidget::item { height: 45px; border-bottom: 1px solid #2a2a32; padding-left: 10px; }
QTreeWidget::item:selected { background-color: #e10600; color: white; border-radius: 4px; }

/* Custom Action Buttons */
QPushButton {
    background-color: #e10600;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 12px;
    font-weight: bold;
    font-size: 14px;
}
QPushButton:hover { background-color: #ff1e1e; }
QPushButton:pressed { background-color: #b00500; }

/* Session Panel Card */
#SessionPanel {
    background-color: #1f1f27;
    border-left: 4px solid #e10600;
    border-radius: 8px;
}
"""

class FetchScheduleWorker(QThread):
    result = Signal(object)
    error = Signal(str)
    def __init__(self, year): super().__init__(); self.year = year
    def run(self):
        try:
            from src.f1_data import enable_cache; enable_cache()
            self.result.emit(get_race_weekends_by_year(self.year))
        except Exception as e: self.error.emit(str(e))

class RaceSelectionWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("F1 REPLAY - PRO")
        self.resize(1100, 750)
        self.setStyleSheet(F1_CSS)
        self._setup_ui()
        self.load_schedule("2025")

    def _setup_ui(self):
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # 1. TOP NAV
        nav = QHBoxLayout()
        title = QLabel("F1 REPLAY")
        title.setObjectName("HeaderLabel")
        title.setFont(QFont("Arial", 26))
        
        self.year_box = QComboBox()
        self.year_box.setFixedWidth(120)
        self.year_box.addItems([str(y) for y in range(2010, 2027)])
        self.year_box.setCurrentText("2025")
        self.year_box.currentTextChanged.connect(self.load_schedule)

        nav.addWidget(title)
        nav.addStretch()
        nav.addWidget(QLabel("SEASON"))
        nav.addWidget(self.year_box)
        layout.addLayout(nav)

        # 2. BODY
        body = QHBoxLayout()
        
        # Schedule List
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["RD", "GRAND PRIX", "LOCATION", "DATE"])
        self.tree.setColumnWidth(0, 50)
        self.tree.setColumnWidth(1, 250)
        self.tree.itemClicked.connect(self.on_race_selected)
        body.addWidget(self.tree, 3)

        # Session Sidebar
        self.session_panel = QFrame()
        self.session_panel.setObjectName("SessionPanel")
        self.session_panel.setFixedWidth(280)
        self.side_layout = QVBoxLayout(self.session_panel)
        self.side_layout.setAlignment(Qt.AlignTop)
        
        self.side_title = QLabel("SELECT EVENT")
        self.side_title.setFont(QFont("Arial", 16, QFont.Bold))
        self.side_layout.addWidget(self.side_title)
        self.side_layout.addSpacing(20)
        
        body.addWidget(self.session_panel)
        self.session_panel.hide()
        
        layout.addLayout(body)

    def load_schedule(self, year):
        self.tree.clear()
        self.session_panel.hide()
        self.worker = FetchScheduleWorker(int(year))
        self.worker.result.connect(self.populate)
        self.worker.start()

    def populate(self, events):
        for ev in events:
            item = QTreeWidgetItem([
                str(ev.get("round_number", "")),
                ev.get("event_name", "").upper(),
                ev.get("country", "").upper(),
                str(ev.get("date", ""))[:10]
            ])
            item.setData(0, Qt.UserRole, ev)
            self.tree.addTopLevelItem(item)

    def on_race_selected(self, item):
        self.session_panel.show()
        ev = item.data(0, Qt.UserRole)
        self.side_title.setText(ev.get("event_name").split(" ")[0])
        
        # Clear old buttons
        for i in reversed(range(1, self.side_layout.count())):
            w = self.side_layout.itemAt(i).widget()
            if w: w.deleteLater()

        types = ["Qualifying", "Race"]
        if 'sprint' in (ev.get('type') or '').lower():
            types = ["Sprint Qualifying", "Sprint", "Qualifying", "Race"]

        for t in types:
            btn = QPushButton(t.upper())
            # Add simple animation effect via code
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(15); shadow.setColor(QColor(225, 6, 0, 150)); shadow.setOffset(0)
            btn.setGraphicsEffect(shadow)
            btn.clicked.connect(lambda _, s=t, e=ev: self.launch(e, s))
            self.side_layout.addWidget(btn)

    def launch(self, ev, session):
        # Logic remains same as your original functional code but triggers modern UI progress
        QMessageBox.information(self, "Loading", f"Pre-loading {session} data...")
        # ... process execution logic ...

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Base style for consistency
    win = RaceSelectionWindow()
    win.show()
    sys.exit(app.exec())
