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


MODEL = "llama-3.3-70b-versatile"

# ── Base rules appended to every persona prompt ───────────────────────────────
_BASE_RULES = """
Rules that apply regardless of persona:
- Write in plain, natural English. No textbook tone, no news article style.
- Never use em dashes as punctuation.
- Never use phrases like "it is worth noting", "dive into", "certainly", "delve", "it is important to note", "fascinatingly", "it's worth mentioning", "needless to say".
- Always be factual. If something is uncertain, say so clearly.
- Keep responses concise but complete. Do not pad answers with filler sentences.
- If live telemetry context is provided, use it to give specific, data-driven answers.
- The current F1 season is 2026. Use the season reference data provided as ground truth. Do not reference drivers not on the 2026 grid unless specifically asked.
- ONLY use driver positions and names from the live leaderboard provided in the context. Never invent or assume positions from your training data. If asked who is last, find the highest position number in the leaderboard and state that driver."""

# ── Persona definitions ───────────────────────────────────────────────────────
PERSONAS: dict[str, dict] = {
    "Race Engineer": {
        "label": "Race Engineer",
        "prompt": (
            "You are a Formula 1 race engineer embedded in a live race replay tool. "
            "Your communication style is direct, data-led, and technical. "
            "Prioritise actionable information. Mirror how a real pit wall engineer speaks to a driver: "
            "concise and precise. Avoid unnecessary narrative — get to the point immediately."
        ),
    },
    "Analyst": {
        "label": "Analyst",
        "prompt": (
            "You are an F1 strategic analyst embedded in a live race replay tool. "
            "Provide deeper explanations, reference historical context where relevant, "
            "and explain the reasoning behind strategic calls. Help the user understand "
            "the why behind race events, not just the what. You may use a slightly longer form "
            "when the topic warrants it, but remain precise and avoid filler."
        ),
    },
    "Commentator": {
        "label": "Commentator",
        "prompt": (
            "You are an F1 race commentator embedded in a live race replay tool. "
            "Be engaging and descriptive. Narrate the race as it unfolds, making it "
            "compelling for a viewer who wants atmosphere and storytelling alongside facts. "
            "You are still factually grounded — never invent events or outcomes — "
            "but your tone is lively and accessible rather than technical."
        ),
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
                    # First frame — initialise without treating as a pit stop
                    self._tyre_history[code] = {"tyre": raw_tyre, "lap": lap}
                elif prev["tyre"] != raw_tyre and raw_tyre is not None:
                    # Tyre compound changed — driver pitted
                    self._pitted_drivers[code] = lap
                    self._tyre_history[code] = {"tyre": raw_tyre, "lap": lap}

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

        ctx = dict(self._latest_context)
        session_info = dict(self._session_info)
        leaderboard = self._leaderboard
        current_tyres = dict(self._current_tyres)
        pitted_drivers = dict(self._pitted_drivers)
        thread = threading.Thread(
            target=self._call_groq,
            args=(question, ctx, session_info, leaderboard, current_tyres, pitted_drivers, signals),
            daemon=True,
        )
        thread.start()

    def _build_telemetry_context(
        self, ctx, session_info, leaderboard, current_tyres, pitted_drivers, grid: str
    ) -> str:
        if ctx.get("frame_index") is None:
            return "No live telemetry connected yet."
        lines = []
        if session_info.get("event_name"):
            event_line = f"Event: {session_info['event_name']}"
            if session_info.get("circuit_name"):
                event_line += f" — {session_info['circuit_name']}"
            if session_info.get("country"):
                event_line += f", {session_info['country']}"
            if session_info.get("year"):
                event_line += f" ({session_info['year']} Round {session_info.get('round', '?')})"
            lines.append(event_line)
        lines.append(
            f"Live race state: Lap {ctx['lap']}/{ctx['total_laps']}, "
            f"leader: {ctx['leader']}, track status: {ctx['track_status']}, "
            f"conditions: {ctx['rain_state']}"
        )
        if ctx.get("air_temp") is not None:
            lines.append(
                f"Air temp: {ctx['air_temp']:.1f}°C, "
                f"track temp: {ctx['track_temp']:.1f}°C"
            )
        if leaderboard:
            lines.append(f"Live leaderboard: {leaderboard}")
        if current_tyres:
            tyre_str = " | ".join(f"{code}: {compound}" for code, compound in sorted(current_tyres.items()))
            lines.append(f"Current tyres: {tyre_str}")
        if pitted_drivers:
            pit_str = " | ".join(
                f"{code} pitted on lap {lap}"
                for code, lap in sorted(pitted_drivers.items(), key=lambda x: x[1])
            )
            lines.append(f"Pit stops so far: {pit_str}")
        else:
            lines.append("Pit stops so far: No pit stops yet")
        if grid:
            lines.append(grid)
        return "\n".join(lines)

    def _call_groq(self, question, ctx, session_info, leaderboard, current_tyres, pitted_drivers, signals):
        api_key = os.environ.get("GROQ_API_KEY", "")
        if not api_key:
            signals.error.emit("GROQ_API_KEY environment variable is not set.")
            return
        try:
            # Fetch live grid from OpenF1 (cached, runs in this background thread)
            grid = _fetch_openf1_drivers()

            telemetry_ctx = self._build_telemetry_context(ctx, session_info, leaderboard, current_tyres, pitted_drivers, grid)

            question_lower = question.lower()
            is_technical = any(kw in question_lower for kw in TECHNICAL_KEYWORDS)
            needs_live_search = any(kw in question_lower for kw in LIVE_KEYWORDS)

            extra_ctx = ""

            if is_technical:
                # Try Wikipedia first for technical/definitional questions
                topic = _extract_technical_topic(question)
                wiki = _wikipedia_summary(f"Formula One {topic}")
                if not wiki:
                    wiki = _wikipedia_summary(topic)
                if wiki:
                    extra_ctx = wiki
                else:
                    # Fall back to Tavily if Wikipedia has nothing useful
                    extra_ctx = _tavily_search(question)
            elif needs_live_search:
                extra_ctx = _tavily_search(question)

            parts = [telemetry_ctx]
            if extra_ctx:
                parts.append(extra_ctx)
            parts.append(f"The user is asking: {question}")
            if extra_ctx:
                parts.append(
                    "Prioritise the provided context over training knowledge for current season information. "
                    "For historical or technical questions, draw on your training knowledge. "
                    "If you are not certain about something, say so rather than guessing."
                )
            prompt = "\n\n".join(parts)

            messages = self._build_messages(prompt)
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=1024,
            )
            reply = response.choices[0].message.content.strip()
            signals.finished.emit(reply)
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

    def _build_messages(self, prompt: str) -> list[dict]:
        """Construct the messages list for the Groq API using the active persona."""
        persona_prompt = PERSONAS[self._persona]["prompt"]
        system_content = (
            persona_prompt
            + _BASE_RULES
            + self._mom_rule()
            + "\n\n"
            + self._season_context
        )
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user",   "content": prompt},
        ]
        return _trim_messages(messages)

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
