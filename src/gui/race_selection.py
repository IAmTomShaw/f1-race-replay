from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QTreeWidget, QTreeWidgetItem, QMessageBox, QInputDialog
)
from PySide6.QtWidgets import QProgressDialog
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QPixmap, QFont
import sys
import os
import subprocess
import tempfile
import uuid
from src.f1_data import get_race_weekends_by_year, load_session
from datetime import datetime
from src.gui.settings_dialog import SettingsDialog


# Worker thread to fetch schedule without blocking UI
class FetchScheduleWorker(QThread):
    result = Signal(object)
    error = Signal(str)

    def __init__(self, year, parent=None):
        super().__init__(parent)
        self.year = year

    def run(self):
        try:
            # enable cache if available in project
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
        self.current_year = datetime.now().year
        self.current_date = datetime.now().date()
        self.setWindowTitle("F1 Race Replay - Session Selection")
        self._setup_ui()
        self.resize(1000, 700)
        self.setMinimumSize(800, 600)
        self.setWindowState(self.windowState())

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)

        # Header (title)
        header_layout = QHBoxLayout()
        header_label = QLabel("F1 Race Replay 🏎️")
        font = header_label.font()
        settings_btn = QPushButton("⚙ Settings")
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.setFixedHeight(32)
        settings_btn.clicked.connect(self.open_settings)
        font.setPointSize(18)
        font.setBold(True)
        header_label.setFont(font)
        header_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        header_layout.addWidget(settings_btn)
        main_layout.addLayout(header_layout)

        # Year selection
        year_layout = QHBoxLayout()
        year_label = QLabel("Select Year:")
        self.year_combo = QComboBox()
        current_year = self.current_year
        for year in range(2010, current_year + 1):
            self.year_combo.addItem(str(year))
        self.year_combo.setCurrentText(str(current_year))
        self.year_combo.currentTextChanged.connect(self.load_schedule)

        year_layout.addWidget(year_label)
        year_layout.addWidget(self.year_combo)
        main_layout.addLayout(year_layout)

        # Main content: left = schedule, right = session list
        content_layout = QHBoxLayout()

        # Schedule tree (left)
        self.schedule_tree = QTreeWidget()
        self.schedule_tree.setHeaderLabels(["Round", "Event", "Country", "Start Date"])
        self.schedule_tree.setRootIsDecorated(False)
        content_layout.addWidget(self.schedule_tree, 3)
        self.schedule_tree.setColumnWidth(2, 180)

        # Session panel (right)
        self.session_panel = QWidget()
        self.session_panel_layout = QVBoxLayout()
        self.session_panel.setLayout(self.session_panel_layout)
        self.session_panel_layout.setAlignment(Qt.AlignTop)
        header_lbl = QLabel("Sessions")
        hdr_font = header_lbl.font()
        hdr_font.setPointSize(14)
        hdr_font.setBold(True)
        header_lbl.setFont(hdr_font)
        self.session_panel_layout.addWidget(header_lbl)

        # placeholder spacer
        self.session_list_container = QWidget()
        self.session_list_layout = QVBoxLayout()
        self.session_list_container.setLayout(self.session_list_layout)
        self.session_panel_layout.addWidget(self.session_list_container)

        content_layout.addWidget(self.session_panel, 1)

        main_layout.addLayout(content_layout)

        # connect click handler
        self.schedule_tree.itemClicked.connect(self.on_race_clicked)

        # Load initial schedule
        # hide sessions panel until a weekend is selected
        self.session_panel.hide()
        self.load_schedule(str(current_year))
        
    def load_schedule(self, year):
        if self.loading_session:
            return
        self.loading_session = True
        self.schedule_tree.clear()
        # hide sessions panel while loading / when nothing selected
        try:
            self.session_panel.hide()
        except Exception:
            pass
        self.worker = FetchScheduleWorker(int(year))
        self.worker.result.connect(self.populate_schedule)
        self.worker.error.connect(self.show_error)
        self.worker.start()
    def populate_schedule(self, events):
        for event in events:
            # Ensure all columns are strings (QTreeWidgetItem expects text)
            round_str = str(event.get("round_number", ""))
            name = str(event.get("event_name", ""))
            country = str(event.get("country", ""))
            date = str(event.get("date", ""))

            event_item = QTreeWidgetItem([round_str, name, country, date])
            event_item.setData(0, Qt.UserRole, event)
            self.schedule_tree.addTopLevelItem(event_item)

        # Make sure the round column is wide enough to be visible
        try:
            self.schedule_tree.resizeColumnToContents(0)
            self.schedule_tree.resizeColumnToContents(1)
        except Exception:
            pass

        self.loading_session = False



    def on_race_clicked(self, item, column):
        ev = item.data(0, Qt.UserRole)

        
        # ensure the sessions panel is visible when a race is selected
        try:
            self.session_panel.show()
        except Exception:
            pass
        
        # clear existing session widgets
        for i in reversed(range(self.session_list_layout.count())):
            w = self.session_list_layout.itemAt(i).widget()
            if w:
                w.setParent(None)
              
        try:

            event_date_str = ev.get("date", "")
            event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
            
            
            # If race hasn't happened yet
            if event_date > self.current_date:
                # Show message instead of session buttons
                label = QLabel("⏳ Race yet to be held")
                label.setAlignment(Qt.AlignCenter)
                font = label.font()
                font.setPointSize(12)
                label.setFont(font)
                label.setStyleSheet("color: gray; padding: 20px;")
                self.session_list_layout.addWidget(label)
                return  # Exit early, don't create session buttons
                
        except Exception as e:
            print(f"Error parsing date: {e}")
            # If date parsing fails, continue and show sessions anyway
        
        # Race has already happened - show session buttons
        # determine sessions to show
        ev_type = (ev.get("type") or "").lower()
        sessions = ["Qualifying", "Race"]
        if "sprint" in ev_type:
            sessions.insert(0, "Sprint Qualifying")
            # show sprint-related session
            sessions.insert(2, "Sprint")

        # add buttons for each session (launch playback in separate process)
        for s in sessions:
            btn = QPushButton(s)
            btn.clicked.connect(
                lambda _, sname=s, e=ev: self._on_session_button_clicked(e, sname)
            )
            self.session_list_layout.addWidget(btn)

    def _on_session_button_clicked(self, ev, session_label):
        """Launch main.py in a separate process to run the selected session.

        Uses the same CLI flags that `main.py` understands: `--qualifying`,
        `--sprint-qualifying`, `--sprint`. Runs the command detached so the
        Qt UI remains responsive.
        """
        try:
            year = int(self.year_combo.currentText())
        except Exception:
            year = None

        try:
            round_no = int(ev.get("round_number"))
        except Exception:
            round_no = None

        # map button labels to CLI flags
        flag = None
        if session_label == "Qualifying":
            flag = "--qualifying"
        elif session_label == "Sprint Qualifying":
            flag = "--sprint-qualifying"
        elif session_label == "Sprint":
            flag = "--sprint"

        main_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "main.py")
        )
        cmd = [sys.executable, main_path, "--viewer"]
        if year is not None:
            cmd += ["--year", str(year)]
        if round_no is not None:
            cmd += ["--round", str(round_no)]
        if flag:
            cmd.append(flag)

        # Show a modal loading dialog and load the session in a background thread.
        dlg = QProgressDialog("Loading session data...", None, 0, 0, self)
        dlg.setWindowTitle("Loading")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.setRange(0, 0)
        dlg.show()
        QApplication.processEvents()

        # Map label -> fastf1 session type code
        session_code = 'R'
        if session_label == "Qualifying":
            session_code = 'Q'
        elif session_label == "Sprint Qualifying":
            session_code = 'SQ'
        elif session_label == "Sprint":
            session_code = 'S'

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
            # create a unique ready-file path and pass it to the child
            ready_path = os.path.join(tempfile.gettempdir(), f"f1_ready_{uuid.uuid4().hex}")
            cmd_with_ready = list(cmd) + ["--ready-file", ready_path]

            try:
                proc = subprocess.Popen(cmd_with_ready)
            except Exception as exc:
                try:
                    dlg.close()
                except Exception:
                    pass
                QMessageBox.critical(self, "Playback error", f"Failed to start playback:\n{exc}")
                return

            # Poll for ready file or child exit
            timer = QTimer(self)

            def _check_ready():
                try:
                    if os.path.exists(ready_path):
                        try:
                            dlg.close()
                        except Exception:
                            pass
                        timer.stop()
                        try:
                            os.remove(ready_path)
                        except Exception:
                            pass
                        return
                    # if process exited early, show error
                    if proc.poll() is not None:
                        try:
                            dlg.close()
                        except Exception:
                            pass
                        timer.stop()
                        QMessageBox.critical(self, "Playback error", "Playback process exited before signaling readiness")
                except Exception:
                    # ignore transient file-system errors
                    pass

            timer.timeout.connect(_check_ready)
            timer.start(200)
            # keep references
            self._play_proc = proc
            self._ready_timer = timer

        def _on_error(msg):
            try:
                dlg.close()
            except Exception:
                pass
            QMessageBox.critical(self, "Load error", f"Failed to load session data:\n{msg}")

        worker = FetchSessionWorker(year, round_no, session_code)
        worker.result.connect(_on_loaded)
        worker.error.connect(_on_error)
        # Keep a reference so it doesn't get GC'd
        self._session_worker = worker
        worker.start()
    def show_error(self, message):
        QMessageBox.critical(self, "Error", f"Failed to load schedule: {message}")
        self.loading_session = False

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()
