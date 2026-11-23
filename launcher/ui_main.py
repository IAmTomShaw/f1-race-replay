import sys
import os
import subprocess
from datetime import datetime
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QLabel, QComboBox, QScrollArea, 
                               QGridLayout, QFrame, QPushButton, QDialog, QGraphicsDropShadowEffect, QListView)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor, QFontDatabase, QCursor

# Ensure we can import from the launcher module
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from launcher.data_handler import SeasonSchedule

# --- THEME: VELOCITY (NFS Style) ---
COLOR_BG_MAIN = "#050505"      # Pure Black
COLOR_BG_CARD = "#111111"      # Dark Grey
COLOR_BG_CARD_HOVER = "#000000"
COLOR_ACCENT = "#eb4034"       # Racing Red
COLOR_ACCENT_SEC = "#ffffff"   # White
COLOR_TEXT_MAIN = "#ffffff"
COLOR_TEXT_DIM = "#666666"
FONT_FAMILY = "Formula1"

# --- GLOBAL STYLES ---
STYLE_BUTTON_PRIMARY = f"""
    QPushButton {{
        background-color: {COLOR_ACCENT};
        color: #ffffff;
        border: none;
        border-radius: 2px; /* Sharp corners */
        padding: 12px 24px;
        font-family: '{FONT_FAMILY}';
        font-weight: bold;
        font-style: italic;
        font-size: 16px;
        text-transform: uppercase;
    }}
    QPushButton:hover {{
        background-color: #f06257; /* Brighter shade of #eb4034 */
        margin-top: -2px; /* Slight lift */
    }}
    QPushButton:pressed {{
        background-color: #a32c24; /* Darker shade of #eb4034 */
        margin-top: 2px;
    }}
"""

STYLE_BUTTON_SECONDARY = f"""
    QPushButton {{
        background-color: transparent;
        color: {COLOR_ACCENT_SEC};
        border: 2px solid {COLOR_ACCENT_SEC};
        border-radius: 2px;
        padding: 10px 22px;
        font-family: '{FONT_FAMILY}';
        font-size: 14px;
        font-weight: bold;
        font-style: italic;
        text-transform: uppercase;
    }}
    QPushButton:hover {{
        border-color: {COLOR_ACCENT};
        color: {COLOR_ACCENT};
        background-color: rgba(235, 64, 52, 0.1);
    }}
    QPushButton:pressed {{
        background-color: rgba(235, 64, 52, 0.2);
    }}
"""

class SessionDialog(QDialog):
    def __init__(self, event_data, parent=None):
        super().__init__(parent)
        self.event_data = event_data
        self.selected_session = None
        self.setWindowTitle("SELECT EVENT")
        self.setFixedWidth(450)
        
        # Dialog Style
        self.setStyleSheet(f"""
            QDialog {{
                background-color: rgba(10, 10, 10, 0.95);
                border: 2px solid {COLOR_ACCENT};
            }}
            QLabel {{
                color: {COLOR_TEXT_MAIN};
                font-family: '{FONT_FAMILY}';
            }}
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(40, 40, 40, 40)
        
        # Header Group
        header_layout = QVBoxLayout()
        header_layout.setSpacing(5)
        
        lbl_round = QLabel(f"ROUND {event_data['RoundNumber']}")
        lbl_round.setStyleSheet(f"color: {COLOR_ACCENT}; font-size: 14px; font-weight: bold; font-style: italic; letter-spacing: 2px;")
        lbl_round.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(lbl_round)
        
        lbl_title = QLabel(f"{event_data['Country'].upper()}")
        lbl_title.setStyleSheet("font-size: 32px; font-weight: bold; font-style: italic;")
        lbl_title.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(lbl_title)
        
        layout.addLayout(header_layout)
        
        # Line Separator
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        line.setStyleSheet(f"background-color: {COLOR_TEXT_DIM}; max-height: 1px; border: none;")
        layout.addWidget(line)
        
        layout.addSpacing(10)
        
        # Session Buttons
        self.create_session_btn(layout, "RACE REPLAY", "R", primary=True)
        self.create_session_btn(layout, "QUALIFYING HIGHLIGHTS", "Q")
        
        # Check for Sprint
        fmt = str(event_data.get('EventFormat', '')).lower()
        if 'sprint' in fmt:
             self.create_session_btn(layout, "SPRINT REPLAY", "S")
             self.create_session_btn(layout, "SPRINT QUALI", "SQ")

        layout.addStretch()

        # Cancel Button
        btn_cancel = QPushButton("CLOSE MENU")
        btn_cancel.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {COLOR_TEXT_DIM};
                border: none;
                font-family: '{FONT_FAMILY}';
                font-size: 12px;
                font-weight: bold;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                color: {COLOR_ACCENT_SEC};
            }}
        """)
        btn_cancel.setCursor(QCursor(Qt.PointingHandCursor))
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_cancel)
        
    def create_session_btn(self, layout, label, code, primary=False):
        btn = QPushButton(label)
        btn.setStyleSheet(STYLE_BUTTON_PRIMARY if primary else STYLE_BUTTON_SECONDARY)
        btn.setCursor(QCursor(Qt.PointingHandCursor))
        btn.clicked.connect(lambda: self.confirm_selection(code))
        layout.addWidget(btn)
        
    def confirm_selection(self, code):
        self.selected_session = code
        self.accept()

class RaceCard(QFrame):
    def __init__(self, event_data, parent=None):
        super().__init__(parent)
        self.event_data = event_data
        
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(180)
        self.setFixedWidth(320)
        
        # Shadow effect for depth
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setXOffset(0)
        shadow.setYOffset(10)
        shadow.setColor(QColor(0, 0, 0, 150))
        self.setGraphicsEffect(shadow)
        
        # Initial Style
        self.update_style(hover=False)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(25, 25, 25, 25)
        layout.setSpacing(0)
        
        # Top: Date & Round
        top_layout = QHBoxLayout()
        
        lbl_date = QLabel(event_data['EventDate'].replace('🏁 ', '').upper())
        lbl_date.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 10px; font-weight: bold; letter-spacing: 1px;")
        top_layout.addWidget(lbl_date)
        
        top_layout.addStretch()
        
        lbl_round = QLabel(f"RD {event_data['RoundNumber']}")
        lbl_round.setStyleSheet(f"color: {COLOR_ACCENT}; font-size: 12px; font-weight: bold; font-style: italic;")
        top_layout.addWidget(lbl_round)
        
        layout.addLayout(top_layout)
        layout.addSpacing(15)
        
        # Middle: Country Big
        lbl_country = QLabel(event_data['Country'].upper())
        lbl_country.setStyleSheet(f"color: {COLOR_TEXT_MAIN}; font-size: 28px; font-weight: bold; font-style: italic;")
        lbl_country.setWordWrap(True)
        layout.addWidget(lbl_country)
        
        # Subtitle: Official Name
        lbl_name = QLabel(event_data['OfficialName'].upper())
        lbl_name.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 9px; font-weight: bold;")
        lbl_name.setWordWrap(True)
        layout.addWidget(lbl_name)
        
        layout.addStretch()
        
        # Bottom: Flag & Status
        bottom_layout = QHBoxLayout()
        lbl_flag = QLabel(event_data['Flag'])
        lbl_flag.setStyleSheet("font-size: 24px;")
        bottom_layout.addWidget(lbl_flag)
        
        bottom_layout.addStretch()
        
        fmt = str(event_data.get('EventFormat', '')).lower()
        if 'sprint' in fmt:
            lbl_tag = QLabel("SPRINT")
            lbl_tag.setStyleSheet(f"color: #ffffff; background-color: {COLOR_ACCENT}; padding: 2px 6px; font-size: 10px; font-weight: bold; border-radius: 2px;")
            bottom_layout.addWidget(lbl_tag)
            
        layout.addLayout(bottom_layout)

    def update_style(self, hover):
        if hover:
            self.setStyleSheet(f"""
                RaceCard {{
                    background-color: {COLOR_BG_CARD_HOVER};
                    border: 2px solid {COLOR_ACCENT};
                    border-radius: 0px; /* Sharp edges */
                }}
                QLabel {{ background-color: transparent; font-family: '{FONT_FAMILY}'; }}
            """)
        else:
            self.setStyleSheet(f"""
                RaceCard {{
                    background-color: {COLOR_BG_CARD};
                    border: 1px solid #333;
                    border-radius: 0px;
                }}
                QLabel {{ background-color: transparent; font-family: '{FONT_FAMILY}'; }}
            """)

    def enterEvent(self, event):
        self.update_style(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.update_style(hover=False)
        super().leaveEvent(event)
        
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_session_selector()
            
    def open_session_selector(self):
        dialog = SessionDialog(self.event_data, self.window())
        if dialog.exec() == QDialog.Accepted:
            self.launch_session(dialog.selected_session)

    def launch_session(self, session_code):
        year = self.event_data.get('year')
        round_num = self.event_data['RoundNumber']
        
        print(f"Launching: Year {year}, Round {round_num}, Session {session_code}")
        
        self.window().close()
        
        cmd = [sys.executable, 'main.py', '--year', str(year), '--round', str(round_num)]
        if session_code == 'Q': cmd.append('--qualifying')
        elif session_code == 'S': cmd.append('--sprint')
        elif session_code == 'SQ': cmd.append('--sprint-qualifying')
        
        subprocess.Popen(cmd)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("F1 RACE REPLAY // LAUNCHER")
        self.resize(1200, 850)
        
        self.schedule_loader = SeasonSchedule()
        
        # Central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(50, 40, 50, 40)
        main_layout.setSpacing(30)
        
        # Header
        header_layout = QHBoxLayout()
        
        # Title Stack
        title_stack = QVBoxLayout()
        title_stack.setSpacing(0)
        lbl_app = QLabel("F1 RACE REPLAY")
        lbl_app.setStyleSheet(f"color: {COLOR_ACCENT_SEC}; font-size: 48px; font-weight: 900; font-style: italic; letter-spacing: -2px;")
        
        lbl_sub = QLabel("ARCHIVE & TELEMETRY SYSTEM")
        lbl_sub.setStyleSheet(f"color: {COLOR_ACCENT}; font-size: 14px; font-weight: bold; letter-spacing: 4px; margin-left: 4px;")
        
        title_stack.addWidget(lbl_app)
        title_stack.addWidget(lbl_sub)
        header_layout.addLayout(title_stack)
        
        header_layout.addStretch()
        
        # Year Selector
        self.year_combo = QComboBox()
        
        # Force QListView
        combo_view = QListView()
        self.year_combo.setView(combo_view)
        
        current_year = datetime.now().year
        years = [str(y) for y in range(current_year + 1, 2017, -1)]
        self.year_combo.addItems(years)
        
        default_year = "2025"
        self.year_combo.setCurrentText(default_year if default_year in years else str(current_year))

        self.year_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLOR_BG_CARD};
                color: {COLOR_ACCENT};
                padding: 12px 30px;
                border: 2px solid {COLOR_BG_CARD};
                border-radius: 0px;
                font-family: '{FONT_FAMILY}';
                font-weight: bold;
                font-size: 20px;
                min-width: 150px;
            }}
            QComboBox:hover {{
                border: 2px solid {COLOR_ACCENT};
                color: {COLOR_ACCENT_SEC};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 40px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border: none;
                width: 0; 
                height: 0;
                border-left: 6px solid transparent;
                border-right: 6px solid transparent;
                border-top: 8px solid {COLOR_ACCENT};
                margin-right: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #000000;
                color: #ffffff;
                selection-background-color: #000000;
                selection-color: {COLOR_ACCENT};
                border: 2px solid {COLOR_ACCENT};
                outline: none;
                padding: 5px;
            }}
            QComboBox QAbstractItemView::item {{
                min-height: 50px;
                padding-left: 20px;
                border-bottom: 1px solid #222;
                color: #ffffff;
            }}
            QComboBox QAbstractItemView::item:hover {{
                background-color: #111111; /* Keep background dark */
                color: {COLOR_ACCENT};    /* Highlight text instead */
                font-weight: bold;
            }}
        """)
        self.year_combo.currentTextChanged.connect(self.load_season)
        header_layout.addWidget(self.year_combo)
        
        main_layout.addLayout(header_layout)
        
        # Scroll Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background-color: transparent;
            }}
            QScrollBar:vertical {{
                background: #111;
                width: 12px;
            }}
            QScrollBar::handle:vertical {{
                background: #333;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {COLOR_ACCENT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
        """)
        
        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: transparent;")
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setSpacing(30)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        
        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area)
        
        # Initial Load
        self.load_season(self.year_combo.currentText())
        
    def load_season(self, year):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget: widget.deleteLater()
                
        try:
            year_int = int(year)
            events = self.schedule_loader.get_schedule(year_int)
        except ValueError: return
            
        if not events:
            lbl = QLabel("NO EVENT DATA AVAILABLE")
            lbl.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 24px; font-weight: bold;")
            self.grid_layout.addWidget(lbl, 0, 0)
            return
            
        columns = 3
        for i, event in enumerate(events):
            event['year'] = year_int
            card = RaceCard(event)
            self.grid_layout.addWidget(card, i // columns, i % columns)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    launcher_dir = os.path.dirname(os.path.abspath(__file__))
    font_dir = os.path.join(launcher_dir, "..", "fonts")
    
    font_files = ["Formula1-Regular-1.ttf", "Formula1-Bold_web.ttf", "Formula1-Wide.ttf"]
    for font_file in font_files:
        QFontDatabase.addApplicationFont(os.path.join(font_dir, font_file))

    app.setStyleSheet(f"""
        QMainWindow, QWidget {{
            background-color: {COLOR_BG_MAIN};
            color: {COLOR_TEXT_MAIN};
            font-family: '{FONT_FAMILY}';
        }}
    """)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())