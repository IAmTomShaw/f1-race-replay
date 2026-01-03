from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QMessageBox
)
from PySide6.QtWidgets import QProgressDialog
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QFont
import sys
import os
import subprocess
import tempfile
import uuid
from src.f1_data import get_race_weekends_by_year, load_session

# Worker thread to fetch schedule without blocking UI
class FetchScheduleWorker(QThread):
    result = Signal(object)
    error = Signal(str)

    def __init__(self, year, parent=None):
        super().__init__(parent)
        self.year = year

    def run(self):
        try:
            try:
                from src.f1_data import enable_cache
                enable_cache()
            except Exception:
                pass
            events = get_race_weekends_by_year(self.year)
            self.result.emit(events)
        except Exception as e:
            self.error.emit(str(e))


class RaceSelectionWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.worker = None
        self.loading_session = False
        self.selected_session_title = None
        self.selected_year = 2025  # default year

        self.setWindowTitle("F1 Race Replay - Session Selection")
        self.resize(1200, 1000)
        self.setMinimumSize(800, 600)
        self.setWindowState(self.windowState())

        # Dark F1-style theme
        self.setStyleSheet("""
        QMainWindow { background-color: #0f0f0f; color: #ffffff; }
        QLabel { color: #ffffff; font-size: 14px; }
        QPushButton {
            background-color: #1e1e1e;
            border: 1px solid #333;
            border-radius: 12px;
            padding: 8px 16px;
            font-size: 14px;
        }
        QPushButton:hover { background-color: #e10600; border-color: #e10600; }
        QTreeWidget { background-color: #151515; border: none; font-size: 13px; }
        QTreeWidget::item { padding: 10px; }
        QTreeWidget::item:selected { background-color: #e10600; }
        QTreeWidget { alternate-background-color: #121212; }
        QHeaderView::section { background-color: #0f0f0f; padding: 8px; border: none; font-weight: bold; }
        QProgressDialog { background-color: #151515; }
        QMessageBox { background-color: #151515; }
        """)

        self._setup_ui()
        self.load_schedule(str(self.selected_year))

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout()
        main_layout.setSpacing(16)
        central_widget.setLayout(main_layout)

        # Header
        header_layout = QHBoxLayout()
        title_lbl = QLabel("F1 RACE REPLAY")
        title_font = QFont("Arial", 22, QFont.Bold)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet("color: #ffffff; letter-spacing: 2px;")
        subtitle_lbl = QLabel("Official Session Archive")
        subtitle_lbl.setStyleSheet("color: #aaaaaa; font-size: 12px;")
        header_box = QVBoxLayout()
        header_box.addWidget(title_lbl)
        header_box.addWidget(subtitle_lbl)
        header_layout.addLayout(header_box)
        header_layout.addStretch()
        main_layout.addLayout(header_layout)

        # Year selection as pill buttons
        self.year_bar = QHBoxLayout()
        self.year_bar.setSpacing(8)
        main_layout.addLayout(self.year_bar)

        self.year_buttons = []
        current_year = 2025
        for y in range(2010, current_year + 1):
            btn = QPushButton(str(y))
            btn.setCheckable(True)
            btn.setStyleSheet(self._get_year_button_style(y))
            btn.clicked.connect(lambda checked, yr=y: self._on_year_clicked(yr))
            self.year_bar.addWidget(btn)
            self.year_buttons.append(btn)

        # Main content layout
        content_layout = QHBoxLayout()
        content_layout.setSpacing(16)

        # Schedule tree (left)
        self.schedule_tree = QTreeWidget()
        self.schedule_tree.setHeaderLabels(["Round", "Event", "Country", "Start Date"])
        self.schedule_tree.setRootIsDecorated(False)
        content_layout.addWidget(self.schedule_tree, 3)
        self.schedule_tree.setColumnWidth(2, 180)

        # Session panel (right)
        self.session_panel = QWidget()
        self.session_panel_layout = QVBoxLayout()
        self.session_panel_layout.setAlignment(Qt.AlignTop)
        self.session_panel.setLayout(self.session_panel_layout)
        session_header = QLabel("Sessions")
        session_font = session_header.font()
        session_font.setPointSize(14)
        session_font.setBold(True)
        session_header.setFont(session_font)
        self.session_panel_layout.addWidget(session_header)
        self.session_list_container = QWidget()
        self.session_list_layout = QVBoxLayout()
        self.session_list_layout.setSpacing(12)
        self.session_list_container.setLayout(self.session_list_layout)
        self.session_panel_layout.addWidget(self.session_list_container)
        content_layout.addWidget(self.session_panel, 1)

        main_layout.addLayout(content_layout)

        # Connections
        self.schedule_tree.itemClicked.connect(self.on_race_clicked)
        self.session_panel.hide()

    def _get_year_button_style(self, year):
        if year == self.selected_year:
            return "background-color: #e10600; color: #ffffff; border-radius: 12px; padding: 8px 16px;"
        else:
            return "background-color: #1e1e1e; color: #ffffff; border-radius: 12px; padding: 8px 16px;"

    def _on_year_clicked(self, year):
        self.selected_year = year
        for btn in self.year_buttons:
            btn.setStyleSheet(self._get_year_button_style(int(btn.text())))
        self.load_schedule(str(year))

    def load_schedule(self, year):
        if self.loading_session:
            return
        self.loading_session = True
        self.schedule_tree.clear()
        self.session_panel.hide()
        self.worker = FetchScheduleWorker(int(year))
        self.worker.result.connect(self.populate_schedule)
        self.worker.error.connect(self.show_error)
        self.worker.start()

    def populate_schedule(self, events):
        for event in events:
            round_str = str(event.get("round_number", ""))
            name = str(event.get("event_name", ""))
            country = str(event.get("country", ""))
            date = str(event.get("date", ""))
            event_item = QTreeWidgetItem([round_str, name, country, date])
            event_item.setData(0, Qt.UserRole, event)
            self.schedule_tree.addTopLevelItem(event_item)
        self.schedule_tree.resizeColumnToContents(0)
        self.schedule_tree.resizeColumnToContents(1)
        self.loading_session = False

    def on_race_clicked(self, item, column):
        ev = item.data(0, Qt.UserRole)
        self.session_panel.show()
        ev_type = (ev.get('type') or '').lower()
        sessions = ["Qualifying", "Race"]
        if 'sprint' in ev_type:
            sessions.insert(0, "Sprint Qualifying")
            sessions.insert(2, "Sprint")
        for i in reversed(range(self.session_list_layout.count())):
            w = self.session_list_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
        for s in sessions:
            btn = QPushButton()
            icon = "🏁"
            if s == "Qualifying": icon = "⏱️"
            elif s == "Sprint Qualifying": icon = "⚡"
            elif s == "Sprint": icon = "🔥"
            btn.setText(f"{icon}  {s}")
            btn.setMinimumHeight(48)
            btn.clicked.connect(lambda _, sname=s, e=ev: self._on_session_button_clicked(e, sname))
            self.session_list_layout.addWidget(btn)

    def _on_session_button_clicked(self, ev, session_label):
        try:
            year = int(self.selected_year)
        except Exception:
            year = None
        try:
            round_no = int(ev.get("round_number"))
        except Exception:
            round_no = None
        flag = None
        if session_label == "Qualifying":
            flag = "--qualifying"
        elif session_label == "Sprint Qualifying":
            flag = "--sprint-qualifying"
        elif session_label == "Sprint":
            flag = "--sprint"
        main_path = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', 'main.py'))
        cmd = [sys.executable, main_path]
        if year is not None:
            cmd += ["--year", str(year)]
        if round_no is not None:
            cmd += ["--round", str(round_no)]
        if flag:
            cmd.append(flag)

        dlg = QProgressDialog("Loading session data...", None, 0, 0, self)
        dlg.setWindowTitle("Loading")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.setRange(0, 0)
        dlg.show()
        QApplication.processEvents()

        session_code = 'R'
        if session_label == "Qualifying": session_code = 'Q'
        elif session_label == "Sprint Qualifying": session_code = 'SQ'
        elif session_label == "Sprint": session_code = 'S'

        class FetchSessionWorker(QThread):
            result = Signal(object)
            error = Signal(str)
            def __init__(self, year, round_no, session_type, parent=None):
                super().__init__(parent)
                self.year = year
                self.round_no = round_no
                self.session_type = session_type
            def run(self):
                try:
                    try:
                        from src.f1_data import enable_cache
                        enable_cache()
                    except Exception:
                        pass
                    sess = load_session(self.year, self.round_no, self.session_type)
                    self.result.emit(sess)
                except Exception as e:
                    self.error.emit(str(e))

        def _on_loaded(session_obj):
            ready_path = os.path.join(tempfile.gettempdir(), f"f1_ready_{uuid.uuid4().hex}")
            cmd_with_ready = list(cmd) + ["--ready-file", ready_path]
            try:
                proc = subprocess.Popen(cmd_with_ready)
            except Exception as exc:
                try: dlg.close()
                except Exception: pass
                QMessageBox.critical(self, "Playback error", f"Failed to start playback:\n{exc}")
                return
            timer = QTimer(self)
            def _check_ready():
                try:
                    if os.path.exists(ready_path):
                        try: dlg.close()
                        except Exception: pass
                        timer.stop()
                        try: os.remove(ready_path)
                        except Exception: pass
                        return
                    if proc.poll() is not None:
                        try: dlg.close()
                        except Exception: pass
                        timer.stop()
                        QMessageBox.critical(self, "Playback error", "Playback process exited before signaling readiness")
                except Exception:
                    pass
            timer.timeout.connect(_check_ready)
            timer.start(200)
            self._play_proc = proc
            self._ready_timer = timer

        def _on_error(msg):
            try: dlg.close()
            except Exception: pass
            QMessageBox.critical(self, "Load error", f"Failed to load session data:\n{msg}")

        worker = FetchSessionWorker(year, round_no, session_code)
        worker.result.connect(_on_loaded)
        worker.error.connect(_on_error)
        self._session_worker = worker
        worker.start()

    def show_error(self, message):
        QMessageBox.critical(self, "Error", f"Failed to load schedule: {message}")
        self.loading_session = False
