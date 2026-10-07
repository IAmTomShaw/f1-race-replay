import sys
import os
import subprocess
import tempfile
import uuid
import functools
from datetime import datetime, timezone
from typing import Dict, Optional, Any, Callable, List

# --- PYSIDE6 ---
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QMessageBox, QScrollArea, QFrame,
    QGridLayout, QSizePolicy, QProgressDialog
)
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QFont, QCursor, QGuiApplication, QPalette

from src.f1_data import (
    get_race_weekends_by_year, 
    get_race_weekends_by_place, 
    get_all_unique_race_names, 
    load_session
)

from src.gui.settings_dialog import SettingsDialog
from src.lib.season import get_season

# Flag mapping for countries/races
COUNTRY_FLAGS = {
    "bahrain": "🇧🇭",
    "saudi arabia": "🇸🇦",
    "australia": "🇦🇺",
    "japan": "🇯🇵",
    "china": "🇨🇳",
    "miami": "🇺🇸",
    "united states": "🇺🇸",
    "usa": "🇺🇸",
    "emilia romagna": "🇮🇹",
    "monaco": "🇲🇨",
    "canada": "🇨🇦",
    "spain": "🇪🇸",
    "austria": "🇦🇹",
    "great britain": "🇬🇧",
    "uk": "🇬🇧",
    "hungary": "🇭🇺",
    "belgium": "🇧🇪",
    "netherlands": "🇳🇱",
    "italy": "🇮🇹",
    "azerbaijan": "🇦🇿",
    "singapore": "🇸🇬",
    "mexico": "🇲🇽",
    "brazil": "🇧🇷",
    "las vegas": "🇺🇸",
    "qatar": "🇶🇦",
    "abu dhabi": "🇦🇪",
    "uae": "🇦🇪",
    "portugal": "🇵🇹",
    "turkey": "🇹🇷",
    "russia": "🇷🇺",
    "france": "🇫🇷",
    "germany": "🇩🇪",
    "styria": "🇦🇹",
    "70th anniversary": "🇬🇧",
    "tuscany": "🇮🇹",
    "eifel": "🇩🇪",
    "sakhir": "🇧🇭"
}

#function to get country flag based on country name or event name
#   event_name is implemented in cases like "70th Anniversary Grand Prix" where the country name is not present in the event name
def get_country_flag(country_name, event_name=""):
    c = (country_name or "").lower().strip()
    e = (event_name or "").lower().strip()
    for key, flag in COUNTRY_FLAGS.items():
        if key in c or key in e:
            return flag
    return "🏎️"

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

class RaceCardWidget(QFrame):
    """
    QFrame representing an F1 race weekend card.
    Displays round details, country flag, and session buttons.
    """
    
    def __init__(self, event_data: Dict[str, Any], on_session_click_callback: Callable, parent=None):
        super().__init__(parent)
        self.event_data = event_data
        self.on_session_click_callback = on_session_click_callback
        
        self.setObjectName("RaceCard")
        self.setMinimumSize(220, 180)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(14, 12, 14, 14)
        self.main_layout.setSpacing(4)

        self._setup_header()
        self._setup_subtitle()
        self.main_layout.addSpacing(4)
        self._setup_sessions_ui()

    def _setup_header(self):
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)

        country = self.event_data.get("country", "")
        event_name = self.event_data.get("event_name", "")
        
        flag = get_country_flag(country, event_name) 
        
        flag_label = QLabel(flag)
        flag_label.setFont(QFont("Apple Color Emoji", 14))

        title_label = QLabel(str(event_name))
        title_label.setObjectName("CardTitle")
        title_label.setFont(QFont("Arial", 13, QFont.Bold))
        title_label.setWordWrap(True)

        round_num = str(self.event_data.get("round_number", ""))
        round_label = QLabel(round_num)
        round_label.setObjectName("CardRound")
        round_label.setFont(QFont("Arial", 13, QFont.Bold))
        round_label.setAlignment(Qt.AlignRight | Qt.AlignTop)

        header_layout.addWidget(flag_label, 0)
        header_layout.addWidget(title_label, 1)
        header_layout.addWidget(round_label, 0)
        self.main_layout.addLayout(header_layout)

    def _setup_subtitle(self):
        date_str = str(self.event_data.get("date", ""))
        formatted_date = date_str
        
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = dt.strftime("%b %d, %Y")
            except ValueError:
                # Fallback to raw string if parsing fails
                pass

        country = str(self.event_data.get("country", ""))
        
        # Filter out empty strings to avoid trailing bullets
        parts = [p for p in (country, formatted_date) if p]
        subtitle_text = " • ".join(parts)

        subtitle_label = QLabel(subtitle_text)
        subtitle_label.setObjectName("CardSubtitle")
        subtitle_label.setFont(QFont("Arial", 11))
        self.main_layout.addWidget(subtitle_label)

    def _get_available_sessions(self) -> List[str]:
        ev_type = (self.event_data.get("type") or "").lower()
        session_dates = self.event_data.get("session_dates", {})
        
        sessions_set = {"Qualifying", "Race"}
        
        if session_dates:
            if "Practice 1" in session_dates: sessions_set.add("FP1")
            if "Practice 2" in session_dates: sessions_set.add("FP2")
            if "Practice 3" in session_dates: sessions_set.add("FP3")
            if "Sprint Shootout" in session_dates or "Sprint Qualifying" in session_dates or "sprint" in ev_type:
                sessions_set.add("Sprint Quali")
            if "Sprint" in session_dates or "sprint" in ev_type:
                sessions_set.add("Sprint")
        else:
            if "sprint" in ev_type:
                sessions_set.update(["FP1", "Sprint Quali", "FP2", "Sprint"])
            else:
                sessions_set.update(["FP1", "FP2", "FP3"])

        # Map UI session names to API keys
        date_mapping = {
            "FP1": "Practice 1", "FP2": "Practice 2", "FP3": "Practice 3",
            "Sprint Quali": "Sprint Qualifying" if "Sprint Qualifying" in session_dates else "Sprint Shootout"
        }
        
        sessions_with_dates = []
        now = datetime.now(timezone.utc)
        
        for s_name in sessions_set:
            date_key = date_mapping.get(s_name, s_name)
            date_str = session_dates.get(date_key, "")
            
            session_dt = None
            if date_str:
                date_str = date_str.replace("Z", "+00:00")
                try:
                    session_dt = datetime.fromisoformat(date_str)
                    # Force tz-awareness to prevent crashes during comparison with utcnow()
                    if session_dt.tzinfo is None:
                        session_dt = session_dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

            # Keep sessions that either lack a timestamp or have already occurred
            if not session_dt or session_dt <= now:
                sessions_with_dates.append({
                    "name": s_name, 
                    "dt": session_dt
                })

        # Hardcoded fallback order if timestamps are missing/invalid
        fallback_order = {"FP1": 0, "FP2": 1, "FP3": 2, "Sprint Quali": 3, "Sprint": 4, "Qualifying": 5, "Race": 6}
        
        sessions_with_dates.sort(
            key=lambda x: x["dt"].timestamp() if x["dt"] else fallback_order.get(x["name"], 99)
        )

        return [s["name"] for s in sessions_with_dates]

    def _setup_sessions_ui(self):
        session_hdr = QLabel("Session:")
        session_hdr.setObjectName("SessionHeader")
        session_hdr.setFont(QFont("Arial", 11, QFont.Bold))
        self.main_layout.addWidget(session_hdr)
        self.main_layout.addSpacing(2)

        available_sessions = self._get_available_sessions()

        sessions_layout = QVBoxLayout()
        sessions_layout.setContentsMargins(0, 0, 0, 0)
        sessions_layout.setSpacing(4)

        row1_box = QHBoxLayout()
        row1_box.setContentsMargins(0, 0, 0, 0)
        row1_box.setSpacing(6)

        row2_box = QHBoxLayout()
        row2_box.setContentsMargins(0, 0, 0, 0)
        row2_box.setSpacing(6)

        display_names = {
            "Sprint Qualifying": "Sprint Quali",
            "Qualifying": "Quali"
        }

        for s in available_sessions:
            disp_name = display_names.get(s, s)
            btn = QPushButton(disp_name)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setObjectName("SessionButton")
            
            # Use partial instead of lambda to prevent late-binding scope bugs in the loop
            btn.clicked.connect(functools.partial(self._handle_session_click, s))

            # Distribute buttons logically based on weekend format
            if s in ["FP1", "FP2", "FP3"] or (s == "Sprint Quali" and "FP2" not in available_sessions):
                row1_box.addWidget(btn)
            else:
                row2_box.addWidget(btn)

        # Only add layouts if they actually contain widgets to prevent empty vertical gaps
        if row1_box.count() > 0:
            row1_box.addStretch()
            sessions_layout.addLayout(row1_box)
            
        if row2_box.count() > 0:
            row2_box.addStretch()
            sessions_layout.addLayout(row2_box)

        self.main_layout.addLayout(sessions_layout)

    def _handle_session_click(self, session_name: str, checked=False):
        # Wrapper to pass the correct payload back to the main UI
        self.on_session_click_callback(self.event_data, session_name)

class FetchSessionWorker(QThread):
    """
    Background worker to load heavy session data without freezing the main UI thread.
    Extracted from nested method scope to prevent memory leaks and re-definitions.
    """
    result = Signal(object)
    error = Signal(str)

    def __init__(self, year: int, round_no: int, session_type: str, parent=None):
        super().__init__(parent)
        self.year = year
        self.round_no = round_no
        self.session_type = session_type

    def run(self):
        try:
            # Local import to prevent circular dependencies at module load time
            from src.f1_data import enable_cache, load_session
            
            try:
                enable_cache()
            except Exception as cache_err:
                # Log the error to the terminal for debugging instead of silent failure
                print(f"[WARNING] Cache error: {cache_err}. Proceeding without cache.")

            sess = load_session(self.year, self.round_no, self.session_type)
            self.result.emit(sess)
        except Exception as e:
            self.error.emit(str(e))


class RaceSelectionWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.loading_session = False
        self.selected_session_title = None
        
        self.current_year = get_season()
        self.selected_year = self.current_year
        
        # Keep references to prevent premature garbage collection
        self._schedule_worker = None
        self._session_worker = None
        self._play_proc = None
        self._ready_timer = None
        self._progress_dialog = None

        self.setWindowTitle("F1 Race Replay - Session Selection")
        self.resize(1100, 750)
        self.setMinimumSize(850, 600)
        
        self._apply_stylesheet()
        self._setup_ui()
        self._connect_theme_signals()

    def _is_dark_mode(self) -> bool:
        """Detects system theme. Fallbacks to window background lightness if styleHints fail."""
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() == Qt.ColorScheme.Dark
        
        # Fallback for older Qt versions
        bg_color = QApplication.palette().color(QPalette.Window)
        return bg_color.lightnessF() < 0.5

    def _get_theme_palette(self, is_dark: bool) -> Dict[str, str]:
        if is_dark:
            return {
                "bg_main": "#16161a", "card_bg": "#242429", "card_border": "#2e2e35",
                "card_hover": "#4a4a56", "text_main": "#ffffff", "text_sub": "#a0a0ab",
                "combo_bg": "#242429", "combo_border": "#3a3a42", "btn_bg": "#383842",
                "btn_border": "#4a4a56", "session_bg": "#2c2c34", "session_border": "#42424d"
            }
        return {
            "bg_main": "#f4f4f7", "card_bg": "#ffffff", "card_border": "#d0d0d8",
            "card_hover": "#b0b0bc", "text_main": "#1a1a1e", "text_sub": "#5a5a65",
            "combo_bg": "#ffffff", "combo_border": "#c4c4ce", "btn_bg": "#e2e2e8",
            "btn_border": "#c4c4ce", "session_bg": "#e8e8ee", "session_border": "#ceced8"
        }

    def _apply_stylesheet(self):
        pal = self._get_theme_palette(self._is_dark_mode())
        
        stylesheet = f"""
        QMainWindow, QWidget#CentralWidget {{ background-color: {pal['bg_main']}; }}
        
        QLabel#MainTitle {{
            color: {pal['text_main']}; font-size: 26px; font-weight: bold; font-family: Arial, sans-serif;
        }}
        
        QLabel#FilterLabel {{
            color: {pal['text_main']}; font-size: 14px; font-weight: bold; font-family: Arial, sans-serif;
        }}
        
        /* Base QComboBox styling */
        QComboBox {{
            background-color: {pal['combo_bg']}; color: {pal['text_main']};
            border: 1px solid {pal['combo_border']}; border-radius: 14px;
            padding: 4px 12px; font-size: 13px; font-weight: bold; min-width: 100px;
        }}
        
        /* Fix the square background/border on the native macOS dropdown button */
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: 24px;
            border-left: none;
            border-top-right-radius: 14px;
            border-bottom-right-radius: 14px;
            background: transparent;
        }}

        /* Style the dropdown list menu to match the theme */
        QComboBox QAbstractItemView {{
            background-color: {pal['combo_bg']};
            color: {pal['text_main']};
            
            /* Remove border and border-radius to prevent macOS square background artifacts */
            border: none;
            border-radius: 0px; 
            
            selection-background-color: {pal['card_hover']};
            outline: none;
        }}
        
        QPushButton#SettingsButton {{
            background-color: {pal['btn_bg']}; color: {pal['text_main']};
            border: 1px solid {pal['btn_border']}; border-radius: 12px;
            padding: 5px 14px; font-size: 13px; font-weight: bold;
        }}
        
        QPushButton#SettingsButton:hover {{
            background-color: {pal['card_hover']}; color: #ffffff;
        }}
        
        QScrollArea, QWidget#GridContainer {{ border: none; background-color: transparent; }}
        
        QFrame#RaceCard {{
            background-color: {pal['card_bg']}; border-radius: 8px; border: 1px solid {pal['card_border']};
        }}
        
        QFrame#RaceCard:hover {{ border: 1px solid {pal['card_hover']}; }}
        
        QLabel#CardTitle, QLabel#SessionHeader {{ color: {pal['text_main']}; }}
        QLabel#CardRound, QLabel#CardSubtitle {{ color: {pal['text_sub']}; }}
        
        QPushButton#SessionButton {{
            background-color: {pal['session_bg']}; color: {pal['text_main']};
            border: 1px solid {pal['session_border']}; border-radius: 12px;
            padding: 4px 10px; font-size: 11px; font-weight: bold; min-height: 20px;
        }}
        
        QPushButton#SessionButton:hover {{
            background-color: #e10600; border-color: #e10600; color: #ffffff;
        }}
        """
        self.setStyleSheet(stylesheet)

    def _connect_theme_signals(self):
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            # Signal passes scheme param, so we consume it via lambda/wrapper
            hints.colorSchemeChanged.connect(lambda _: self._apply_stylesheet())

    def _setup_ui(self):
        central_widget = QWidget()
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(28, 20, 28, 24)
        main_layout.setSpacing(16)

        self._setup_header(main_layout)
        self._setup_filters(main_layout)

        # Grid Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.grid_container = QWidget()
        self.grid_container.setObjectName("GridContainer")
        self.cards_grid = QGridLayout(self.grid_container)
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        self.cards_grid.setSpacing(16)

        self.scroll_area.setWidget(self.grid_container)
        main_layout.addWidget(self.scroll_area, 1)

        self.load_schedule(year=self.current_year)

    def _setup_header(self, parent_layout: QVBoxLayout):
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)

        f1_red = QLabel("F1")
        f1_red.setFont(QFont("Arial", 26, QFont.Bold))
        f1_red.setStyleSheet("color: #e10600;")

        title_text = QLabel("Race Replay 🏎️")
        title_text.setObjectName("MainTitle")
        title_text.setFont(QFont("Arial", 26, QFont.Bold))

        title_box = QHBoxLayout()
        title_box.setSpacing(6)
        title_box.addWidget(f1_red)
        title_box.addWidget(title_text)

        settings_btn = QPushButton("Settings ⚙")
        settings_btn.setObjectName("SettingsButton")
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.clicked.connect(self.open_settings)

        header_layout.addStretch(1)
        header_layout.addLayout(title_box)
        header_layout.addStretch(1)
        header_layout.addWidget(settings_btn)
        
        parent_layout.addLayout(header_layout)

    def _setup_filters(self, parent_layout: QVBoxLayout):
        filters_layout = QHBoxLayout()
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.setSpacing(16)

        # Year Combo
        filters_layout.addWidget(self._create_filter_label("Select Year:"))
        self.year_combo = QComboBox()
        self.year_combo.addItem("All Years")
        for year in range(2018, self.current_year + 1):
            self.year_combo.addItem(str(year))
            
        self.year_combo.setCurrentText(str(self.current_year))
        self.year_combo.currentTextChanged.connect(self.load_by_year)
        filters_layout.addWidget(self.year_combo)

        filters_layout.addSpacing(20)

        # Race Place Combo
        filters_layout.addWidget(self._create_filter_label("Select Race:"))
        self.place_combo = QComboBox()
        self.place_combo.addItem("All Races")
        self.place_combo.addItems(get_all_unique_race_names())
        self.place_combo.currentTextChanged.connect(self.load_by_place)
        filters_layout.addWidget(self.place_combo)

        filters_layout.addStretch(1)
        parent_layout.addLayout(filters_layout)

    def _create_filter_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("FilterLabel")
        return lbl

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_cards()

    def load_schedule(self, year: Optional[int] = None, events: Optional[List[dict]] = None):
        if self.loading_session:
            return

        self._clear_grid()

        if events is not None:
            self.current_events = events
            self.populate_schedule(events)
            self.loading_session = False
            return

        if year is not None:
            self.loading_session = True
            self._schedule_worker = FetchScheduleWorker(int(year))
            self._schedule_worker.result.connect(self.populate_schedule)
            self._schedule_worker.error.connect(self.show_error)
            self._schedule_worker.start()
            return

        self.loading_session = False

    def load_by_year(self, year_text: str):
        if self.loading_session:
            return

        if year_text != "All Years":
            # Temporarily block signals to prevent redundant data fetching
            self.place_combo.blockSignals(True)
            self.place_combo.setCurrentText("All Races")
            self.place_combo.blockSignals(False)
            
            self.selected_year = int(year_text)
            self.load_schedule(year=self.selected_year)
        else:
            self.selected_year = None
            self._clear_grid()

    def load_by_place(self, race_name: str):
        if race_name == "All Races":
            if self.selected_year is not None:
                self.load_schedule(year=self.selected_year)
            return

        self.year_combo.blockSignals(True)
        self.year_combo.setCurrentText("All Years")
        self.year_combo.blockSignals(False)
        self.selected_year = None

        self._clear_grid()
        
        events = get_race_weekends_by_place(race_name)
        self.load_schedule(events=events)

    def _clear_grid(self):
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def populate_schedule(self, events: List[dict]):
        self.current_events = events
        self._relayout_cards()
        self.loading_session = False

    def _relayout_cards(self):
        if not getattr(self, "current_events", None):
            return

        self.grid_container.setUpdatesEnabled(False)
        self._clear_grid()

        viewport = self.scroll_area.viewport()
        avail_width = viewport.width() if viewport else self.width()
        col_width = 240
        num_cols = max(1, min(4, avail_width // col_width))

        for idx, event in enumerate(self.current_events):
            row = idx // num_cols
            col = idx % num_cols
            card = RaceCardWidget(event, self._on_session_button_clicked)
            self.cards_grid.addWidget(card, row, col)

        self.grid_container.setUpdatesEnabled(True)

    # --- SESSION PLAYBACK LOGIC ---

    def _get_session_args(self, session_label: str) -> tuple[str, str]:
        """Maps UI session labels to backend API session codes and CLI flags."""
        flag = f"--{session_label.lower()}" # Fallback
        session_code = session_label

        if session_label in ["Qualifying", "Quali"]:
            flag, session_code = "--qualifying", "Q"
        elif session_label in ["Sprint Qualifying", "Sprint Quali"]:
            flag, session_code = "--sprint-qualifying", "SQ"
        elif session_label == "Sprint":
            flag, session_code = "--sprint", "S"
            
        return session_code, flag

    def _on_session_button_clicked(self, ev: dict, session_label: str):
        """Prepares metadata and launches background fetch before playback."""
        year = int(ev.get("year", self.selected_year or self.current_year))
        try:
            round_no = int(ev.get("round_number", 0))
        except (ValueError, TypeError):
            self.show_error("Invalid round number provided in event data.")
            return

        session_code, flag = self._get_session_args(session_label)
        
        # Build base CLI command for subprocess
        main_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "main.py"))
        self._pending_cmd = [sys.executable, main_path, "--viewer", "--year", str(year), "--round", str(round_no), flag]
        
        if "--verbose" in sys.argv:
            self._pending_cmd.append("--verbose")

        self._show_loading_dialog()

        self._session_worker = FetchSessionWorker(year, round_no, session_code)
        self._session_worker.result.connect(self._launch_playback_process)
        self._session_worker.error.connect(self._on_session_load_error)
        self._session_worker.start()

    def _show_loading_dialog(self):
        self._progress_dialog = QProgressDialog("Loading session data...", None, 0, 0, self)
        self._progress_dialog.setWindowTitle("Loading")
        self._progress_dialog.setWindowModality(Qt.ApplicationModal)
        self._progress_dialog.setCancelButton(None)
        self._progress_dialog.setMinimumDuration(0)
        self._progress_dialog.show()
        QApplication.processEvents()

    def _close_loading_dialog(self):
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

    def _on_session_load_error(self, msg: str):
        self._close_loading_dialog()
        QMessageBox.critical(self, "Load error", f"Failed to load session data:\n{msg}")

    def _launch_playback_process(self, session_obj):
        """Called when session data finishes caching. Starts the playback viewer."""
        ready_path = os.path.join(tempfile.gettempdir(), f"f1_ready_{uuid.uuid4().hex}")
        cmd_with_ready = self._pending_cmd + ["--ready-file", ready_path]

        try:
            self._play_proc = subprocess.Popen(cmd_with_ready)
        except OSError as exc:
            self._close_loading_dialog()
            QMessageBox.critical(self, "Playback error", f"Failed to start playback subprocess:\n{exc}")
            return

        # Poll the filesystem to check when the subprocess creates the ready file
        self._ready_timer = QTimer(self)
        self._ready_timer.timeout.connect(lambda: self._poll_ready_file(ready_path))
        self._ready_timer.start(200)

    def _poll_ready_file(self, ready_path: str):
        """Checks if the external viewer process has signaled it is ready."""
        if os.path.exists(ready_path):
            self._close_loading_dialog()
            self._ready_timer.stop()
            try:
                os.remove(ready_path)
            except OSError:
                pass # Non-blocking cleanup failure
            return
            
        if self._play_proc.poll() is not None:
            # Subprocess exited unexpectedly before creating the ready file
            self._close_loading_dialog()
            self._ready_timer.stop()
            QMessageBox.critical(self, "Playback error", "Playback process exited before signaling readiness.")

    def show_error(self, message: str):
        QMessageBox.critical(self, "Error", message)
        self.loading_session = False

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()
