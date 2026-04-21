import os
import time
import threading
import urllib.parse
import urllib.request
import json

from groq import Groq
from tavily import TavilyClient
from PySide6.QtCore import Qt, Signal, QObject, QTimer
from PySide6.QtGui import QFont, QColor, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QLabel, QScrollArea, QFrame, QSizePolicy,
    QComboBox,
)

from src.gui.pit_wall_window import PitWallWindow
from src.data.f1_season_data import build_season_context, uses_mom

# ── Colours ───────────────────────────────────────────────────────────────────
BG          = "#0f0f1a"
SURFACE     = "#1e1e2e"
USER_RED    = "#e8002d"
TEXT_LIGHT  = "#e0e0e0"
TEXT_DIM    = "#888899"
BORDER      = "#2a2a3e"

# ── Search config ─────────────────────────────────────────────────────────────
TAVILY_DOMAINS = [
    "formula1.com", "fia.com", "autosport.com", "motorsport.com",
    "the-race.com", "racefans.net", "pitpass.com", "f1technical.net",
    "motorsportweek.com", "gpfans.com", "planetf1.com", "f1i.com",
    "grandprix247.com", "statsf1.com", "somersf1.com",
]

# Questions that need a live web search
LIVE_KEYWORDS = [
    "latest", "recent", "now", "current", "today", "this week", "this season",
    "2024", "2025", "2026", "news", "rumour", "rumor", "update", "just",
    "announce", "signed", "confirmed", "breaking",
    "driver", "drivers", "grid", "fantasy", "team", "worst", "best", "pick",
    "season", "lineup", "constructor", "standings", "championship", "points",
    "who is leading", "who's leading", "results", "last race", "winner", "who won",
]

# Questions that are better answered by Wikipedia first
TECHNICAL_KEYWORDS = [
    "what is", "what are", "how does", "how do", "explain", "define",
    "drs", "kers", "ers", "mgu", "power unit", "diffuser", "undercut",
    "overcut", "tyre", "tire", "compound", "pit stop", "safety car",
    "virtual safety car", "parc fermé", "parc ferme", "bop", "balance of performance",
    "dirty air", "wake", "downforce", "drag", "drs zone", "flexi wing",
    "porpoising", "ground effect", "floor", "diffuser", "sidepod",
]

# ── OpenF1 driver cache ───────────────────────────────────────────────────────
_openf1_cache: dict = {"data": None, "fetched_at": 0.0}
_OPENF1_TTL = 600  # 10 minutes


def _fetch_openf1_drivers() -> str:
    """Return a formatted driver-team list from OpenF1, cached for 10 minutes."""
    now = time.monotonic()
    if _openf1_cache["data"] and now - _openf1_cache["fetched_at"] < _OPENF1_TTL:
        return _openf1_cache["data"]
    try:
        url = "https://api.openf1.org/v1/drivers?session_key=latest"
        req = urllib.request.Request(url, headers={"User-Agent": "f1-race-replay/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            drivers = json.loads(resp.read().decode())
        if not drivers:
            return ""
        # De-duplicate by driver_number (API sometimes returns multiple entries)
        seen: set = set()
        lines = []
        for d in drivers:
            num = d.get("driver_number") or d.get("name_acronym")
            if num in seen:
                continue
            seen.add(num)
            code = d.get("name_acronym", "???")
            name = d.get("full_name", "")
            team = d.get("team_name", "")
            lines.append(f"  {code}: {name} ({team})")
        result = "2026 F1 grid (from OpenF1):\n" + "\n".join(lines)
        _openf1_cache["data"] = result
        _openf1_cache["fetched_at"] = now
        return result
    except Exception:
        return _openf1_cache["data"] or ""  # serve stale on error


# ── Wikipedia summary ─────────────────────────────────────────────────────────

def _wikipedia_summary(topic: str) -> str:
    """Fetch the Wikipedia summary for a topic. Returns '' if nothing useful found."""
    try:
        slug = urllib.parse.quote(topic.replace(" ", "_"))
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}"
        req = urllib.request.Request(url, headers={"User-Agent": "f1-race-replay/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        extract = data.get("extract", "")
        title = data.get("title", "")
        # Discard disambiguation pages and very short extracts
        if data.get("type") == "disambiguation" or len(extract) < 80:
            return ""
        return f"Wikipedia — {title}:\n{extract}"
    except Exception:
        return ""


def _extract_technical_topic(question: str) -> str:
    """Strip question words to get the core term for a Wikipedia lookup."""
    q = question.lower()
    for prefix in ("what is ", "what are ", "how does ", "how do ", "explain ", "define "):
        if q.startswith(prefix):
            return question[len(prefix):].strip(" ?")
    return question.strip(" ?")


# ── Tavily search ─────────────────────────────────────────────────────────────

def _tavily_search(question: str, max_results: int = 8) -> str:
    """Search F1 news sources using a focused query derived from the question."""
    api_key = os.environ.get("TAVILY_API_KEY", "")
    if not api_key:
        return ""
    try:
        # Build a tighter query rather than sending the raw question
        topic = _extract_technical_topic(question)
        query = (
            f"{topic} Formula 1 "
            f"site:motorsport.com OR site:racefans.net OR site:formula1.com"
        )
        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            search_depth="advanced",
            include_domains=TAVILY_DOMAINS,
            max_results=max_results,
        )
        results = response.get("results", [])
        if not results:
            return ""
        lines = []
        for r in results:
            lines.append(f"Source: {r.get('url', 'unknown')}")
            lines.append(f"Title: {r.get('title', '')}")
            lines.append(f"Content: {r.get('content', '')}")
            lines.append("")
        return "Recent information from F1 sources:\n" + "\n".join(lines)
    except Exception:
        return ""


# ── Provider / model chain ────────────────────────────────────────────────────
# Tried in order on each request. On Groq 429, we fall to Cerebras, then to
# the smaller Groq model. The caller never sees a rate-limit error.

_GROQ_PRIMARY   = "llama-3.3-70b-versatile"
_CEREBRAS_MODEL = "qwen-3-235b-a22b-instruct-2507"
_GROQ_FALLBACK  = "llama-3.1-8b-instant"

MODEL = _GROQ_PRIMARY  # legacy alias kept for any external references

# ── Base rules appended to every persona prompt ───────────────────────────────
_BASE_RULES = (
    " RULE 0: If the question is about strategy, pit stops, tyres, or gaps —"
    " your FIRST sentence must be one of: 'Box this lap.' | 'Stay out — pit on lap [X].'"
    " | 'Undercut now — box this lap.' | 'Cover [DRIVER] — box this lap.'"
    " If the question is factual or informational (who is P6, what tyre, is it raining) —"
    " answer the fact directly in one sentence, no pit call needed."
    " Rules: plain English only; no em dashes; no filler phrases (\"worth noting\","
    " \"dive into\", \"certainly\", \"delve\"); be factual; if uncertain say so;"
    " use live leaderboard data for positions — never invent them;"
    " season is 2026, MOM replaces DRS."
)

# ── Persona definitions ───────────────────────────────────────────────────────
PERSONAS: dict[str, dict] = {
    "Race Engineer": {
        "label": "Race Engineer",
        "prompt": "You are an F1 race engineer in a live replay tool. Be direct, technical, concise.",
    },
    "Analyst": {
        "label": "Analyst",
        "prompt": "You are an F1 strategic analyst in a live replay tool. Explain strategy reasoning clearly.",
    },
    "Commentator": {
        "label": "Commentator",
        "prompt": "You are an F1 commentator in a live replay tool. Be engaging and factual.",
    },
}

# Legacy constant kept for any code that imports it directly
SYSTEM_PROMPT = PERSONAS["Race Engineer"]["prompt"] + _BASE_RULES


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _trim_messages(messages: list, token_limit: int = 8000) -> list:
    total = sum(_estimate_tokens(m["content"]) for m in messages)
    if total <= token_limit or len(messages) <= 2:
        return messages

    system_msg = messages[0]
    user_msg = messages[-1]
    reserved = _estimate_tokens(system_msg["content"]) + _estimate_tokens(user_msg["content"])
    budget = token_limit - reserved

    trimmed = []
    for msg in messages[1:-1]:
        content = msg["content"]
        allowed_chars = budget * 4
        if allowed_chars <= 0:
            break
        trimmed.append({**msg, "content": content[:allowed_chars]})
        budget -= _estimate_tokens(content[:allowed_chars])

    return [system_msg] + trimmed + [user_msg]


# ── Tyre age tracker ──────────────────────────────────────────────────────────

class TyreAgeTracker:
    """
    Tracks tyre age for a single driver, lap-delta aware.

    Handles high-speed fast-forward correctly: if the replay jumps from
    lap 1 to lap 9 in one frame, tyre_age is incremented by 8, not 1.
    On compound change, age is reset to lap_delta (the driver pitted
    somewhere in the skipped window; worst-case they just fitted the tyre
    at the start of that window, so they've already done lap_delta laps).
    """

    def __init__(self):
        self.tyre_age: int      = 0
        self.compound: int | None = None
        self._last_lap: int     = 0

    def update(self, driver_frame: dict) -> None:
        lap      = int(driver_frame.get("lap") or 0)
        raw_tyre = driver_frame.get("tyre")

        lap_delta = max(0, lap - self._last_lap)

        if self.compound is None:
            # First frame — start the stint clock.
            self.compound = raw_tyre
            self.tyre_age = 0
        elif raw_tyre is not None and raw_tyre != self.compound:
            # Compound changed — pit happened somewhere in the skipped window.
            self.compound = raw_tyre
            self.tyre_age = lap_delta  # conservative: pitted at start of window
        else:
            self.tyre_age += lap_delta

        self._last_lap = lap


# def _test_tyre_age_fastforward():
#     """Simulates fast-forward from lap 1 to lap 18 in 3 frames"""
#     tracker = TyreAgeTracker()
#     frames = [
#         {"lap": 1,  "tyre": 2},
#         {"lap": 9,  "tyre": 2},
#         {"lap": 18, "tyre": 2},
#     ]
#     for f in frames:
#         tracker.update(f)
#     assert tracker.tyre_age == 17, f"Expected 17, got {tracker.tyre_age}"
#     print("PASS")


class _GroqWorkerSignals(QObject):
    finished = Signal(str)
    error = Signal(str)


# ── Small circular initials badge ─────────────────────────────────────────────

class _Badge(QWidget):
    def __init__(self, letter: str, bg: str, parent=None):
        super().__init__(parent)
        self._letter = letter
        self._bg = QColor(bg)
        size = 28
        self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, self.width(), self.height())
        p.fillPath(path, self._bg)
        p.setPen(QColor("#ffffff"))
        p.setFont(QFont("Arial", 11, QFont.Bold))
        p.drawText(self.rect(), Qt.AlignCenter, self._letter)


# ── Single chat bubble ─────────────────────────────────────────────────────────

class _Bubble(QWidget):
    """A right-aligned (user) or left-aligned (engineer/error) chat bubble."""

    def __init__(self, sender: str, text: str, parent=None):
        super().__init__(parent)
        is_user = sender == "user"
        is_error = sender == "error"

        bubble_color = USER_RED if is_user else ("#3a1a1a" if is_error else SURFACE)
        badge_letter = "Y" if is_user else ("!" if is_error else "E")
        badge_color  = USER_RED if is_user else ("#aa2222" if is_error else "#333355")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 2, 6, 2)
        outer.setSpacing(8)

        badge = _Badge(badge_letter, badge_color)
        badge.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        bubble = QFrame()
        bubble.setStyleSheet(
            f"background-color: {bubble_color};"
            f"border-radius: 12px;"
        )
        b_layout = QVBoxLayout(bubble)
        b_layout.setContentsMargins(12, 8, 12, 8)
        b_layout.setSpacing(0)

        msg = QLabel(text)
        msg.setFont(QFont("Arial", 12))
        msg.setStyleSheet(f"color: {TEXT_LIGHT}; background: transparent;")
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
        msg.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        b_layout.addWidget(msg)

        if is_user:
            outer.addStretch()
            outer.addWidget(bubble, stretch=1)
            outer.addWidget(badge)
        else:
            outer.addWidget(badge)
            outer.addWidget(bubble, stretch=1)
            outer.addStretch()


# ── Main window ────────────────────────────────────────────────────────────────

class EngineerChatWindow(PitWallWindow):
    """AI race engineer chat powered by Groq."""

    def __init__(self):
        self._latest_context = {}
        self._session_info = {}
        self._leaderboard = ""
        self._tyre_history: dict[str, dict] = {}   # code -> {tyre, lap}
        self._pitted_drivers: dict[str, int] = {}  # code -> lap number of most recent pit
        self._current_tyres: dict[str, str] = {}   # code -> compound name
        self._persona: str = "Race Engineer"
        self._session_year: int = 2026
        self._season_context: str = build_season_context(2026)
        self.latest_telemetry: dict | None = None  # full raw frame, used by build_race_context()
        super().__init__()
        self.setWindowTitle("BoxBox - Race Engineer")
        self.setGeometry(100, 100, 520, 720)

    def setup_ui(self):
        self.setStyleSheet(f"background-color: {BG};")

        central = QWidget()
        central.setStyleSheet(f"background-color: {BG};")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Header ────────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet(f"background-color: {SURFACE}; border-bottom: 1px solid {BORDER};")
        header.setFixedHeight(54)
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 0, 16, 0)

        icon = QLabel("⬡")
        icon.setStyleSheet(f"color: {USER_RED}; background: transparent;")
        icon.setFont(QFont("Arial", 20, QFont.Bold))

        title = QLabel("BoxBox - Race Engineer")
        title.setStyleSheet(f"color: {TEXT_LIGHT}; background: transparent;")
        title.setFont(QFont("Arial", 14, QFont.Bold))

        # Persona selector
        self._persona_combo = QComboBox()
        self._persona_combo.setFont(QFont("Arial", 10))
        self._persona_combo.setFixedWidth(130)
        self._persona_combo.setStyleSheet(
            f"QComboBox {{"
            f"  background-color: {BG}; color: {TEXT_LIGHT};"
            f"  border: 1px solid {BORDER}; border-radius: 4px; padding: 2px 6px;"
            f"}}"
            f"QComboBox::drop-down {{ border: none; }}"
            f"QComboBox QAbstractItemView {{"
            f"  background-color: {SURFACE}; color: {TEXT_LIGHT};"
            f"  selection-background-color: {BORDER};"
            f"}}"
        )
        for name in PERSONAS:
            self._persona_combo.addItem(name)
        self._persona_combo.setCurrentText(self._persona)
        self._persona_combo.currentTextChanged.connect(self._on_persona_changed)

        h_layout.addWidget(icon)
        h_layout.addSpacing(8)
        h_layout.addWidget(title)
        h_layout.addStretch()
        h_layout.addWidget(self._persona_combo)
        layout.addWidget(header)

        # ── Message area ──────────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet(
            f"QScrollArea {{ background: {BG}; border: none; }}"
            f"QScrollBar:vertical {{ background: {BG}; width: 6px; border-radius: 3px; }}"
            f"QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 3px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
        )

        self._msg_container = QWidget()
        self._msg_container.setStyleSheet(f"background-color: {BG};")
        self._msg_layout = QVBoxLayout(self._msg_container)
        self._msg_layout.setSpacing(6)
        self._msg_layout.setContentsMargins(8, 12, 8, 12)
        self._msg_layout.addStretch()

        self._scroll.setWidget(self._msg_container)
        layout.addWidget(self._scroll, stretch=1)

        # ── Input bar ─────────────────────────────────────────────────────
        input_bar = QWidget()
        input_bar.setStyleSheet(
            f"background-color: {SURFACE}; border-top: 1px solid {BORDER};"
        )
        input_bar.setFixedHeight(60)
        i_layout = QHBoxLayout(input_bar)
        i_layout.setContentsMargins(12, 10, 12, 10)
        i_layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask the engineer something...")
        self._input.setFont(QFont("Arial", 12))
        self._input.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {BG};"
            f"  color: {TEXT_LIGHT};"
            f"  border: 1px solid {BORDER};"
            f"  border-radius: 8px;"
            f"  padding: 6px 12px;"
            f"}}"
            f"QLineEdit:focus {{ border: 1px solid {USER_RED}; }}"
        )
        self._input.returnPressed.connect(self._send)

        self._send_btn = QPushButton("Send")
        self._send_btn.setFixedSize(68, 36)
        self._send_btn.setFont(QFont("Arial", 12, QFont.Bold))
        self._send_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {USER_RED};"
            f"  color: #ffffff;"
            f"  border: none;"
            f"  border-radius: 8px;"
            f"}}"
            f"QPushButton:hover {{ background-color: #ff1a3e; }}"
            f"QPushButton:pressed {{ background-color: #c0001f; }}"
            f"QPushButton:disabled {{ background-color: #5a001a; color: #888; }}"
        )
        self._send_btn.clicked.connect(self._send)

        i_layout.addWidget(self._input, stretch=1)
        i_layout.addWidget(self._send_btn)
        layout.addWidget(input_bar)

        # ── Custom status bar ─────────────────────────────────────────────
        status_bar = QWidget()
        status_bar.setStyleSheet(
            f"background-color: {BG}; border-top: 1px solid {BORDER};"
        )
        status_bar.setFixedHeight(28)
        s_layout = QHBoxLayout(status_bar)
        s_layout.setContentsMargins(12, 0, 12, 0)

        self._conn_dot = QLabel("●")
        self._conn_dot.setStyleSheet(f"color: #cc3333; background: transparent;")
        self._conn_dot.setFont(QFont("Arial", 10))

        self._conn_label = QLabel("Disconnected")
        self._conn_label.setStyleSheet(f"color: {TEXT_DIM}; background: transparent;")
        self._conn_label.setFont(QFont("Arial", 10))

        self._msg_count = QLabel("Messages: 0")
        self._msg_count.setStyleSheet(f"color: {TEXT_DIM}; background: transparent;")
        self._msg_count.setFont(QFont("Arial", 10))

        s_layout.addWidget(self._conn_dot)
        s_layout.addSpacing(4)
        s_layout.addWidget(self._conn_label)
        s_layout.addStretch()
        s_layout.addWidget(self._msg_count)
        layout.addWidget(status_bar)

        # Hide the PitWallWindow default status bar — we draw our own
        if hasattr(self, "status_bar"):
            self.status_bar.hide()

    # ── PitWallWindow overrides ────────────────────────────────────────────────

    def on_connection_status_changed(self, status: str):
        connected = status == "Connected"
        dot_color = "#22cc66" if connected else ("#ffaa00" if status == "Connecting..." else "#cc3333")
        self._conn_dot.setStyleSheet(f"color: {dot_color}; background: transparent;")
        self._conn_label.setText(status)

    def on_telemetry_data(self, data):
        self.latest_telemetry = data  # full snapshot for build_race_context()

        frame = data.get("frame", {})
        session = data.get("session_data", {})
        weather = frame.get("weather", {})

        self._latest_context = {
            "lap": session.get("lap", frame.get("lap", "?")),
            "total_laps": session.get("total_laps", "?"),
            "leader": session.get("leader", "?"),
            "track_status": data.get("track_status", "?"),
            "rain_state": weather.get("rain_state", "?"),
            "air_temp": weather.get("air_temp"),
            "track_temp": weather.get("track_temp"),
            "is_paused": data.get("is_paused", False),
            "frame_index": data.get("frame_index"),
        }

        if data.get("session_info"):
            self._session_info = data["session_info"]
            year = int(self._session_info.get("year") or 2026)
            if year != self._session_year:
                self._session_year = year
                self._season_context = build_season_context(year)

        # Tyre compound lookup (matches src/lib/tyres.py)
        _COMPOUND = {0: "Soft", 1: "Medium", 2: "Hard", 3: "Inter", 4: "Wet"}

        # Build ranked leaderboard, track tyre history, detect pit stops
        drivers = frame.get("drivers", {})
        if drivers:
            ranked = sorted(
                drivers.items(),
                key=lambda item: int(item[1].get("position") or 99),
            )

            for code, d in drivers.items():
                raw_tyre = d.get("tyre")
                compound = _COMPOUND.get(int(raw_tyre), "Unknown") if raw_tyre is not None else "Unknown"
                lap = int(d.get("lap") or 0)

                self._current_tyres[code] = compound

                prev = self._tyre_history.get(code)
                if prev is None:
                    # First frame — record the stint start lap as this lap.
                    # age_start_lap is the lap this tyre was fitted (or the lap
                    # we first saw the driver, whichever is earlier).
                    self._tyre_history[code] = {
                        "tyre": raw_tyre,
                        "age_start_lap": lap,
                    }
                else:
                    lap_delta = lap - prev.get("last_seen_lap", lap)

                    if raw_tyre is not None and prev["tyre"] != raw_tyre:
                        # Compound changed — driver pitted somewhere in this
                        # frame window.  Record the pit on the current lap and
                        # reset age_start_lap.  At high speed we can't know
                        # exactly when they pitted, so we use the most
                        # conservative estimate: they pitted at the START of
                        # the skipped window, giving them the maximum possible
                        # age on the new tyre (lap_delta laps already done).
                        self._pitted_drivers[code] = lap
                        self._tyre_history[code] = {
                            "tyre": raw_tyre,
                            "age_start_lap": lap - lap_delta,
                            "last_seen_lap": lap,
                        }
                    else:
                        # Same compound — just refresh last_seen_lap so the
                        # next frame can compute an accurate lap_delta.
                        prev["last_seen_lap"] = lap

            self._leaderboard = " | ".join(
                f"P{int(d.get('position', i + 1))}: {code} ({self._current_tyres.get(code, '?')}, lap {int(d.get('lap') or 0)})"
                for i, (code, d) in enumerate(ranked)
            )

        # Update message count in our custom status bar
        self._msg_count.setText(f"Messages: {self.message_count}")

    # ── Sending & AI ──────────────────────────────────────────────────────────

    def _send(self):
        question = self._input.text().strip()
        if not question:
            return

        self._input.clear()
        self._input.setEnabled(False)
        self._send_btn.setEnabled(False)

        self._append_message("user", question)

        signals = _GroqWorkerSignals()
        signals.finished.connect(self._on_reply)
        signals.error.connect(self._on_error)

        # Snapshot mutable state for the background thread
        race_context = self.build_race_context()
        thread = threading.Thread(
            target=self._call_groq,
            args=(question, race_context, signals),
            daemon=True,
        )
        thread.start()

    # ── Race context builder ───────────────────────────────────────────────────

    def build_race_context(self, max_drivers: int = 20) -> str:
        """
        Compact race state block (~300 tokens for 20 drivers).
        Each driver line is one row: P1  PIA  | Med  | Age 17 | Leader
        """
        _CMP = {0: "Sft", 1: "Med", 2: "Hrd", 3: "Int", 4: "Wet"}
        _TS  = {"1": "None", "2": "YEL", "4": "SC", "5": "RED", "6": "VSC", "7": "VSC-end"}

        if self.latest_telemetry is None:
            return "No live telemetry. Answer from general F1 knowledge."

        data         = self.latest_telemetry
        frame        = data.get("frame", {}) or {}
        session      = data.get("session_data", {}) or {}
        session_info = data.get("session_info", {}) or {}
        weather      = frame.get("weather", {}) or {}
        drivers      = frame.get("drivers", {}) or {}

        lap        = session.get("lap", "?")
        total_laps = session.get("total_laps", "?")
        ts_raw     = str(data.get("track_status", "1"))
        sc_state   = _TS.get(ts_raw, ts_raw)
        rain       = weather.get("rain_state", "DRY")
        track_temp = weather.get("track_temp")
        circuit    = session_info.get("circuit_name") or session_info.get("event_name") or "?"
        temp_str   = f" {track_temp:.1f}°C" if track_temp is not None else ""

        header = f"=== RACE STATE: Lap {lap}/{total_laps} | {circuit} | {rain}{temp_str} | SC:{sc_state} ==="

        if not drivers:
            return f"{header}\n(No driver data)\n=== END ==="

        ranked = sorted(
            drivers.items(),
            key=lambda kv: int(kv[1].get("position") or 99),
        )[:max_drivers]

        leader_rel = float(ranked[0][1].get("rel_dist") or 0.0) if ranked else 0.0
        speeds = [float(d.get("speed") or 0) for _, d in ranked if float(d.get("speed") or 0) > 10]
        avg_speed_ms = (sum(speeds) / len(speeds) / 3.6) if speeds else (150 / 3.6)
        circuit_len  = 5000.0

        rows = []
        for i, (code, d) in enumerate(ranked):
            pos      = int(d.get("position") or i + 1)
            tyre_raw = d.get("tyre")
            cmp      = _CMP.get(int(tyre_raw), "?") if tyre_raw is not None else "?"
            drv_lap  = int(d.get("lap") or 0)
            rel      = float(d.get("rel_dist") or 0.0)

            hist      = self._tyre_history.get(code)
            age_start = hist.get("age_start_lap") if hist is not None else None
            age       = max(0, drv_lap - age_start) if age_start is not None else drv_lap

            if i == 0:
                gap = "Leader"
            else:
                dist_diff = (leader_rel - rel) % 1.0
                gap_s     = dist_diff * circuit_len / max(avg_speed_ms, 1.0)
                gap       = f"+{gap_s:.1f}s"

            rows.append(f"P{pos:<2} {code:<3} | {cmp:<3} | Age {age:<2} | {gap}")

        # Pit summary (compact)
        if self._pitted_drivers:
            pit_entries = sorted(self._pitted_drivers.items(), key=lambda x: x[1])
            pit_line = "Pits: " + " ".join(f"{c}(L{l})" for c, l in pit_entries)
        else:
            pit_line = "Pits: none"

        context = "\n".join([header] + rows + [pit_line, "=== END ==="])


        return context

    def _call_groq(self, question: str, race_context: str, signals):
        """
        Send a question through the provider fallback chain:
          1. Groq  llama-3.3-70b-versatile  (primary)
          2. Cerebras  llama-3.3-70b         (on Groq 429)
          3. Groq  llama-3.1-8b-instant      (if Cerebras also fails)
             — reply prefixed with "[Reduced Quality Mode]"
        """
        groq_key      = os.environ.get("GROQ_API_KEY", "")
        cerebras_key  = os.environ.get("CEREBRAS_API_KEY", "")

        if not groq_key:
            signals.error.emit("GROQ_API_KEY environment variable is not set.")
            return

        try:
            question_lower    = question.lower()
            is_technical      = any(kw in question_lower for kw in TECHNICAL_KEYWORDS)
            needs_live_search = any(kw in question_lower for kw in LIVE_KEYWORDS)

            extra_ctx = ""
            if is_technical:
                topic     = _extract_technical_topic(question)
                wiki      = _wikipedia_summary(f"Formula One {topic}") or _wikipedia_summary(topic)
                extra_ctx = wiki or _tavily_search(question)
            elif needs_live_search:
                extra_ctx = _tavily_search(question)

            def _make_messages(ctx: str, q: str) -> list[dict]:
                """Build messages, assert token budget, fall back to P1-P3 if needed."""
                parts = [ctx]
                if extra_ctx:
                    parts.append(extra_ctx)
                parts.append(f"Engineer question: {q}")
                prompt = "\n\n".join(parts)

                msgs = self._build_messages(prompt, race_context=ctx, question=q)

                sys_tok = len(msgs[0]["content"]) // 4
                ctx_tok = len(ctx) // 4
                q_tok   = len(q) // 4
                total   = sys_tok + ctx_tok + q_tok

                if total >= 4000:
                    # Hard budget exceeded — shrink to P1-P10 and rebuild
                    ctx10 = self.build_race_context(max_drivers=10)
                    parts10 = [ctx10]
                    if extra_ctx:
                        parts10.append(extra_ctx)
                    parts10.append(f"Engineer question: {q}")
                    msgs = self._build_messages(
                        "\n\n".join(parts10), race_context=ctx10, question=q
                    )
                return msgs

            # Truncate question to 300-token budget
            max_q_chars = 300 * 4
            q = question[:max_q_chars]

            # Full leaderboard context: all drivers (22 × ~10 tok = ~220 tok)
            ctx_full = self.build_race_context(max_drivers=22)
            messages = _make_messages(ctx_full, q)

            # ── Step 1: Groq primary ──────────────────────────────────────────
            try:
                client   = Groq(api_key=groq_key)
                response = client.chat.completions.create(
                    model=_GROQ_PRIMARY,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=512,
                )
                signals.finished.emit(response.choices[0].message.content.strip())
                return
            except Exception as groq_err:
                # Only fall through on rate-limit (429); re-raise anything else
                err_str = str(groq_err).lower()
                if "429" not in err_str and "rate" not in err_str and "rate_limit" not in err_str:
                    raise

            # ── Step 2: Cerebras fallback ─────────────────────────────────────
            if cerebras_key:
                try:
                    from cerebras.cloud.sdk import Cerebras  # optional dependency
                    cb_client = Cerebras(
                        api_key=cerebras_key,
                        base_url="https://api.cerebras.ai/v1",
                    )
                    response  = cb_client.chat.completions.create(
                        model=_CEREBRAS_MODEL,
                        messages=messages,
                        temperature=0.7,
                        max_tokens=512,
                    )
                    reply = response.choices[0].message.content.strip()
                    signals.finished.emit(f"[Cerebras Mode]\n{reply}")
                    return
                except Exception:
                    pass  # fall through to reduced-quality Groq

            # ── Step 3: Groq reduced-quality fallback ─────────────────────────
            fallback_messages = _make_messages(self.build_race_context(max_drivers=22), q)
            client   = Groq(api_key=groq_key)
            response = client.chat.completions.create(
                model=_GROQ_FALLBACK,
                messages=fallback_messages,
                temperature=0.7,
                max_tokens=512,
            )
            reply = response.choices[0].message.content.strip()
            signals.finished.emit(f"[Reduced Quality Mode]\n{reply}")

        except Exception as exc:
            signals.error.emit(str(exc))

    def _on_reply(self, text):
        self._append_message("engineer", text)
        self._re_enable_input()

    def _on_error(self, text):
        self._append_message("error", text)
        self._re_enable_input()

    def _on_persona_changed(self, name: str):
        if name not in PERSONAS:
            return
        self._persona = name
        # Clear chat history and confirm switch
        for i in reversed(range(self._msg_layout.count() - 1)):
            widget = self._msg_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
        self._append_message("engineer", f"Switched to {name} mode.")

    def _mom_rule(self) -> str:
        """Return the session-appropriate DRS/MOM instruction for the system prompt."""
        if uses_mom(self._session_year):
            return (
                "\n- DRS does not exist in 2026 and later seasons. "
                "The overtaking aid is MOM (Manual Override Mode). "
                "When a driver is described as having DRS available, correct this — "
                "in 2026+ they have MOM. "
                "MOM is an electrical power boost from the MGU-K, not a wing-opening mechanism."
            )
        return (
            "\n- This session uses DRS (Drag Reduction System) as the overtaking aid. "
            "Reference it as DRS, not MOM."
        )

    def _build_messages(self, prompt: str, race_context: str = "", question: str = "") -> list[dict]:
        """
        Construct a token-budgeted messages list.
        Budget: system ≤300 + context ≤800 + question ≤300 = 1,400 (100 buffer to 1,500).
        """
        system_content = PERSONAS[self._persona]["prompt"] + _BASE_RULES

        # Truncate question if oversized
        max_q_chars = 300 * 4
        if len(question) > max_q_chars:
            question = question[:max_q_chars]

        # Debug token log
        sys_tok  = len(system_content) // 4
        ctx_tok  = len(race_context) // 4
        q_tok    = len(question) // 4
        total    = sys_tok + ctx_tok + q_tok
        print(f"[EngineerChat] Tokens — system: {sys_tok}, context: {ctx_tok}, question: {q_tok}, total: {total}")

        return [
            {"role": "system", "content": system_content},
            {"role": "user",   "content": prompt},
        ]

    def _re_enable_input(self):
        self._input.setEnabled(True)
        self._send_btn.setEnabled(True)
        self._input.setFocus()

    def _append_message(self, sender: str, text: str):
        bubble = _Bubble(sender, text)
        self._msg_layout.insertWidget(self._msg_layout.count() - 1, bubble)
        # Defer scroll so the layout has time to expand the widget
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))
