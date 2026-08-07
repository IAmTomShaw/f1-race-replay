from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QTreeWidget, QTreeWidgetItem, QMessageBox
)
from PySide6.QtWidgets import QProgressDialog
from PySide6.QtCore import QThread, Signal, Qt, QTimer
#from PySide6.QtGui import QPixmap, QFont
import sys
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from src.f1_data import get_race_weekends_by_year, get_race_weekends_by_place, get_all_unique_race_names
from src.gui.settings_dialog import SettingsDialog
from src.lib.season import get_season

# Worker thread to fetch schedule without blocking UI
class FetchScheduleWorker(QThread):
    result = Signal(object)
    error = Signal(str)

    def __init__(self, year, parent=None):
        super().__init__(parent)
        self.year = year

    def run(self): #check
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
        self.current_year = get_season()
        self.selected_year=self.current_year 

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
        self.year_combo.addItem("All Years")

        for year in range(2018, self.current_year + 1):
            self.year_combo.addItem(str(year))

        self.year_combo.setCurrentText(str(self.current_year))
        self.year_combo.currentTextChanged.connect(self.load_by_year)

        year_layout.addWidget(year_label)
        year_layout.addWidget(self.year_combo)
        main_layout.addLayout(year_layout)

        #Race Selection
        place_layout=QHBoxLayout()
        place_label=QLabel("Select Race:")
        self.place_combo=QComboBox()
        self.place_combo.addItem("All Races")
        self.place_combo.addItems(get_all_unique_race_names())
        self.place_combo.currentTextChanged.connect(self.load_by_place)


        place_layout.addWidget(place_label)
        place_layout.addWidget(self.place_combo)
        main_layout.addLayout(place_layout)

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
        self.load_schedule(year=self.current_year)
        
    def load_schedule(self, year=None, events=None):
        if self.loading_session:
            return
        
        self.schedule_tree.clear()
        # hide sessions panel while loading / when nothing selected
        try:
            self.session_panel.hide()
        except Exception:
            pass
        
        #Race filter
        if events is not None:
            self.populate_schedule(events)
            self.loading_session = False
            return
        
        #Year filter
        if year is not None:
            self.loading_session = True
            self.worker = FetchScheduleWorker(int(year))
            self.worker.result.connect(self.populate_schedule)
            self.worker.error.connect(self.show_error)
            self.worker.start()
            return
        
        self.loading_session=False

    def load_by_year(self, year_text):
        if self.loading_session:
            return
        
        #Reset by_race filter
        if year_text!="All Years":
            self.place_combo.blockSignals(True)
            self.place_combo.setCurrentText("All Races")
            self.place_combo.blockSignals(False)

        if year_text=="All Years":
            self.selected_year=None
            self.schedule_tree.clear()
            return
        
        if not year_text.isdigit():
            return
        
        self.selected_year=int(year_text)
        self.load_schedule(year=self.selected_year)

    def load_by_place(self,race_name):
        if race_name=="All Races":
            if self.selected_year is not None:
                self.load_schedule(year=self.selected_year)
            return
        
        #Reset year filter
        self.year_combo.blockSignals(True)
        self.year_combo.setCurrentText("All Years")
        self.year_combo.blockSignals(False)
        self.selected_year=None

        self.schedule_tree.clear()
        
        events=get_race_weekends_by_place(race_name)
        self.load_schedule(events=events)

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
        # determine sessions to show
        ev_type = (ev.get("type") or "").lower()
        if "sprint" in ev_type:
            sessions = ["FP1", "Sprint Qualifying", "Sprint", "Qualifying", "Race"]
        else:
            sessions = ["FP1", "FP2", "FP3", "Qualifying", "Race"]

        # clear existing session widgets
        for i in reversed(range(self.session_list_layout.count())):
            w = self.session_list_layout.itemAt(i).widget()
            if w:
                w.setParent(None)

        # determine which sessions have already occurred (data available)
        now = datetime.now(timezone.utc)
        session_dates = ev.get("session_dates", {})

        available_sessions = []
        for s in sessions:
            candidates = [s]
            if s == "FP1": candidates = ["Practice 1", "FP1"]
            elif s == "FP2": candidates = ["Practice 2", "FP2"]
            elif s == "FP3": candidates = ["Practice 3", "FP3"]
            elif s == "Sprint Qualifying": candidates = ["Sprint Qualifying", "Sprint Shootout", "SQ"]
            elif s == "Sprint": candidates = ["Sprint", "S"]
            elif s == "Qualifying": candidates = ["Qualifying", "Q"]
            elif s == "Race": candidates = ["Race", "R"]

            session_date_str = None
            for cand in candidates:
                if cand in session_dates:
                    session_date_str = session_dates[cand]
                    break

            if session_date_str:
                try:
                    session_dt = datetime.fromisoformat(session_date_str)
                    if session_dt <= now:
                        available_sessions.append(s)
                except Exception:
                    available_sessions.append(s)
            else:
                # no date info means historical data — assume available
                available_sessions.append(s)

        if not available_sessions:
            label = QLabel("Sessions not available")
            label.setAlignment(Qt.AlignCenter)
            self.session_list_layout.addWidget(label)
        else:
            for s in sessions:
                if s in available_sessions:
                    btn = QPushButton(s)
                    btn.clicked.connect(
                        lambda _, sname=s, e=ev: self._on_session_button_clicked(e, sname)
                    )
                    self.session_list_layout.addWidget(btn)

    def _on_session_button_clicked(self, ev, session_label):
        """Launch main.py in a separate process to run the selected session.

        Uses the same CLI flags that `main.py` understands: `--fp1`, `--fp2`,
        `--fp3`, `--qualifying`, `--sprint-qualifying`, `--sprint`. Runs the command
        detached so the Qt UI remains responsive.
        """
        try:
            year = ev.get("year") or self.selected_year
        except Exception:
            year = None

        try:
            round_no = int(ev.get("round_number"))
        except Exception:
            round_no = None

        # map button labels to CLI flags
        flag = None
        if session_label == "FP1":
            flag = "--fp1"
        elif session_label == "FP2":
            flag = "--fp2"
        elif session_label == "FP3":
            flag = "--fp3"
        elif session_label == "Qualifying":
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
        if "--verbose" in sys.argv:
            cmd.append("--verbose")
        # Spawn the subprocess directly – the child process loads the session
        # itself, so there is no need to pre-load it here (which was causing
        # the session to be loaded twice and doubling the wait time).
        dlg = QProgressDialog("Loading session data...", None, 0, 0, self)
        dlg.setWindowTitle("Loading")
        dlg.setWindowModality(Qt.ApplicationModal)
        dlg.setCancelButton(None)
        dlg.setMinimumDuration(0)
        dlg.setRange(0, 0)
        dlg.show()
        QApplication.processEvents()

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
    def show_error(self, message):
        QMessageBox.critical(self, "Error", f"Failed to load schedule: {message}")
        self.loading_session = False

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()
