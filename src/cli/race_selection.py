import sys
import os
import subprocess

from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QComboBox, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from src.f1_data import get_race_weekends_by_year


F1_STYLE = """
QWidget {
    background-color: #0b0b0b;
    color: white;
    font-family: Arial;
}

QLabel#Title {
    font-size: 22px;
    font-weight: bold;
}

QComboBox, QListWidget {
    background-color: #151515;
    border: 1px solid #e10600;
    padding: 6px;
}

QPushButton {
    background-color: #e10600;
    border: none;
    padding: 10px;
    font-weight: bold;
}

QPushButton:hover {
    background-color: #ff1e1e;
}

QListWidget::item {
    padding: 8px;
}

QListWidget::item:selected {
    background-color: #e10600;
}
"""


class CliLikeGui(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("F1 Race Replay")
        self.setMinimumSize(700, 600)
        self.setStyleSheet(F1_STYLE)

        self.data = []
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # ---- Title ----
        title = QLabel("F1 RACE REPLAY")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # ---- Year selector (top) ----
        year_layout = QHBoxLayout()
        year_label = QLabel("Season")
        year_label.setFont(QFont("", 12, QFont.Bold))
        year_layout.addWidget(year_label)

        self.year_box = QComboBox()
        for y in range(2025, 2009, -1):
            self.year_box.addItem(str(y))
        self.year_box.currentIndexChanged.connect(self.load_rounds)
        year_layout.addWidget(self.year_box)

        year_layout.addStretch()
        main_layout.addLayout(year_layout)

        # ---- Race list ----
        races_label = QLabel("Races")
        races_label.setFont(QFont("", 14, QFont.Bold))
        main_layout.addWidget(races_label)

        self.race_list = QListWidget()
        self.race_list.currentItemChanged.connect(self.load_sessions)
        main_layout.addWidget(self.race_list, 1)

        # ---- Session & HUD ----
        options_layout = QHBoxLayout()

        self.session_box = QComboBox()
        options_layout.addWidget(QLabel("Session"))
        options_layout.addWidget(self.session_box)

        self.hud_box = QComboBox()
        self.hud_box.addItem("HUD: Yes", True)
        self.hud_box.addItem("HUD: No", False)
        options_layout.addWidget(self.hud_box)

        main_layout.addLayout(options_layout)

        # ---- Start button ----
        self.run_btn = QPushButton("START REPLAY")
        self.run_btn.clicked.connect(self.run)
        main_layout.addWidget(self.run_btn)

        self.load_rounds()

    def load_rounds(self):
        self.race_list.clear()
        self.session_box.clear()

        year = int(self.year_box.currentText())
        self.data = get_race_weekends_by_year(year)

        for row in self.data:
            item = QListWidgetItem(f"{row['event_name']}  •  {row['date']}")
            item.setData(Qt.UserRole, row)
            self.race_list.addItem(item)

        if self.race_list.count() > 0:
            self.race_list.setCurrentRow(0)

    def load_sessions(self):
        self.session_box.clear()

        item = self.race_list.currentItem()
        if not item:
            return

        row = item.data(Qt.UserRole)

        sessions = ["Qualifying", "Race"]
        if "sprint" in row["type"]:
            sessions = ["Sprint Qualifying", "Sprint"] + sessions

        self.session_box.addItems(sessions)

        session = self.session_box.currentText()
        self.hud_box.setEnabled(session in ("Sprint", "Race"))

    def run(self):
        item = self.race_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Error", "No race selected")
            return

        row = item.data(Qt.UserRole)

        year = int(self.year_box.currentText())
        round_number = row["round_number"]
        session = self.session_box.currentText()
        hud = self.hud_box.currentData()

        flag = None
        match session:
            case "Qualifying":
                flag = "--qualifying"
            case "Sprint Qualifying":
                flag = "--qualifying --sprint"
            case "Sprint":
                flag = "--sprint"

        main_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "main.py")
        )

        cmd = [
            sys.executable,
            main_path,
            "--year", str(year),
            "--round", str(round_number)
        ]

        if flag:
            cmd.append(flag)

        if session in ("Sprint", "Race") and not hud:
            cmd.append("--no-hud")

        subprocess.run(cmd)


def cli_load():
    app = QApplication(sys.argv)
    win = CliLikeGui()
    win.show()
    sys.exit(app.exec())
