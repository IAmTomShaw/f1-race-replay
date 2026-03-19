"""
YouTube Video Player Widget for F1 Race Replay.
Shows thumbnails and plays videos directly in the app.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QFrame
)
from PySide6.QtCore import Qt, Signal, QThread, QSize
from PySide6.QtGui import QFont, QPixmap, QImage, QPainter, QColor
import urllib.request
import urllib.error
import subprocess
import webbrowser
import tempfile
import os

from src.youtube_api import search_race_replay, get_recommended_channels


class ThumbnailLoader(QThread):
    """Background thread to load thumbnails."""
    
    loaded = Signal(str, QPixmap)
    error = Signal(str)
    
    def __init__(self, url: str, parent=None):
        super().__init__(parent)
        self.url = url
    
    def run(self):
        try:
            req = urllib.request.Request(
                self.url,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                data = response.read()
            
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            
            self.loaded.emit(self.url, pixmap)
        except Exception as e:
            self.error.emit(str(e))


class VideoThumbnailWidget(QWidget):
    """Widget showing video thumbnail with play button overlay."""
    
    clicked = Signal(dict)
    
    def __init__(self, video_data: dict, parent=None):
        super().__init__(parent)
        self.video_data = video_data
        self.pixmap = None
        self._setup_ui()
        self._load_thumbnail()
    
    def _setup_ui(self):
        self.setMinimumHeight(140)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setMinimumHeight(90)
        self.thumbnail_label.setStyleSheet("""
            background-color: #333;
            border-radius: 8px;
        """)
        
        self.play_overlay = QLabel("▶", self.thumbnail_label)
        self.play_overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.play_overlay.setStyleSheet("""
            color: white;
            font-size: 36px;
            font-weight: bold;
            background-color: rgba(0, 0, 0, 0.6);
            border-radius: 30px;
            min-width: 60px;
            max-width: 60px;
            min-height: 60px;
            max-height: 60px;
        """)
        self.play_overlay.move(45, 20)
        self.play_overlay.hide()
        
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        title = self.video_data.get('title', 'Video')
        if len(title) > 50:
            title = title[:47] + "..."
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setWordWrap(True)
        title_label.setStyleSheet("color: #fff; font-size: 12px;")
        
        channel = self.video_data.get('channel', 'Unknown')
        duration = self.video_data.get('duration', 'N/A')
        info_label = QLabel(f"<span style='color: #888;'>{channel}</span> • <span style='color: #aaa;'>{duration}</span>")
        info_label.setStyleSheet("font-size: 11px;")
        
        layout.addWidget(self.thumbnail_label)
        layout.addLayout(info_layout)
        layout.addWidget(title_label)
        layout.addWidget(info_label)
        
        self.setStyleSheet("""
            QWidget {
                background-color: transparent;
            }
            QWidget:hover {
                background-color: #2a2a2a;
                border-radius: 8px;
            }
        """)
    
    def _load_thumbnail(self):
        video_id = self.video_data.get('video_id', '')
        thumbnail_url = self.video_data.get('thumbnail', '')
        
        if not thumbnail_url and video_id:
            thumbnail_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
        
        if not thumbnail_url:
            self.thumbnail_label.setText("📺")
            return
        
        self.loader = ThumbnailLoader(thumbnail_url)
        self.loader.loaded.connect(self._on_thumbnail_loaded)
        self.loader.error.connect(self._on_thumbnail_error)
        self.loader.start()
    
    def _on_thumbnail_loaded(self, url: str, pixmap: QPixmap):
        if pixmap and not pixmap.isNull():
            scaled = pixmap.scaled(
                160, 90,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.thumbnail_label.setPixmap(scaled)
    
    def _on_thumbnail_error(self, error: str):
        self.thumbnail_label.setText("📺")
    
    def enterEvent(self, event):
        self.play_overlay.show()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        self.play_overlay.hide()
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.video_data)
        super().mousePressEvent(event)


class VideoPlayerWidget(QWidget):
    """Embedded video player widget."""
    
    closed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_video = None
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.header = QWidget()
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(10, 5, 10, 5)
        
        self.title_label = QLabel("Now Playing")
        self.title_label.setStyleSheet("color: #fff; font-weight: bold;")
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedSize(30, 30)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: #444;
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 16px;
            }
            QPushButton:hover {
                background-color: #d44;
            }
        """)
        self.close_btn.clicked.connect(self.hide_player)
        
        header_layout.addWidget(self.title_label, 1)
        header_layout.addWidget(self.close_btn)
        
        self.player_container = QWidget()
        self.player_container.setMinimumHeight(200)
        self.player_container.setStyleSheet("background-color: #000;")
        
        self.player_placeholder = QLabel("Loading video...")
        self.player_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.player_placeholder.setStyleSheet("color: #888; background-color: #000;")
        
        player_layout = QVBoxLayout(self.player_container)
        player_layout.setContentsMargins(0, 0, 0, 0)
        player_layout.addWidget(self.player_placeholder)
        
        layout.addWidget(self.header)
        layout.addWidget(self.player_container)
        
        self.hide()
        
        self.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border-radius: 8px;
            }
        """)
    
    def play_video(self, video_data: dict):
        """Play a video using mpv or system player."""
        video_id = video_data.get('video_id', '')
        title = video_data.get('title', 'F1 Race')
        
        self.current_video = video_data
        self.title_label.setText(f"▶ {title[:30]}...")
        self.show()
        
        if video_id:
            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            
            try:
                subprocess.Popen([
                    'mpv',
                    '--fullscreen',
                    '--no-terminal',
                    youtube_url
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                try:
                    subprocess.Popen([
                        'vlc',
                        '--fullscreen',
                        youtube_url
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except FileNotFoundError:
                    webbrowser.open(youtube_url)
    
    def hide_player(self):
        self.hide()
        self.current_video = None
        self.title_label.setText("Now Playing")


class YouTubeSearchResults(QWidget):
    """Widget to display YouTube search results with thumbnails."""
    
    video_selected = Signal(dict)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.results = []
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)
        
        header_layout = QHBoxLayout()
        
        header = QLabel("Race Replays")
        header.setStyleSheet("color: #fff; font-size: 14px; font-weight: bold;")
        
        self.search_btn = QPushButton("🔍 Search")
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff0000;
                color: white;
                border: none;
                padding: 5px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #cc0000;
            }
        """)
        
        header_layout.addWidget(header, 1)
        header_layout.addWidget(self.search_btn)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("border: none; background-color: transparent;")
        
        self.results_container = QWidget()
        self.results_layout = QVBoxLayout(self.results_container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(8)
        
        scroll.setWidget(self.results_container)
        
        self.empty_label = QLabel("Select a race to see\nYouTube replays")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #666; padding: 40px;")
        
        layout.addLayout(header_layout)
        layout.addWidget(self.empty_label)
        layout.addWidget(scroll)
        
        scroll.hide()
    
    def set_results(self, results: list, event_name: str = "", year: int = 0):
        """Display search results."""
        self.results = results
        
        for i in reversed(range(self.results_layout.count())):
            w = self.results_layout.itemAt(i).widget()
            if w:
                w.deleteLater()
        
        if not results:
            self.empty_label.setText(f"No results for {year}\n{event_name}")
            self.empty_label.show()
            self.results_layout.parent().hide()
            return
        
        self.empty_label.hide()
        self.results_layout.parent().show()
        
        for video in results:
            widget = VideoThumbnailWidget(video)
            widget.clicked.connect(self._on_video_clicked)
            self.results_layout.addWidget(widget)
    
    def _on_video_clicked(self, video_data: dict):
        self.video_selected.emit(video_data)
    
    def clear(self):
        for i in reversed(range(self.results_layout.count())):
            w = self.results_layout.itemAt(i).widget()
            if w:
                w.deleteLater()
        
        self.empty_label.setText("Select a race to see\nYouTube replays")
        self.empty_label.show()
        self.results_layout.parent().hide()
        self.results = []


class RecommendedChannels(QWidget):
    """Widget showing recommended F1 YouTube channels."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        header = QLabel("Quick Links")
        header.setStyleSheet("color: #fff; font-size: 12px; font-weight: bold;")
        
        channels = get_recommended_channels()
        
        for ch in channels:
            btn = QPushButton(f"▶ {ch['name']}")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(ch['description'])
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #333;
                    color: white;
                    border: 1px solid #444;
                    padding: 8px;
                    text-align: left;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #444;
                    border-color: #ff0000;
                }
            """)
            btn.clicked.connect(lambda _, url=ch['url']: webbrowser.open(url))
            layout.addWidget(btn)
        
        layout.addStretch()
        
        self.setStyleSheet("background-color: #1a1a1a;")


class YouTubePanel(QWidget):
    """Complete YouTube panel with thumbnails and player."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_event = ""
        self.current_year = 2025
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        
        self.search_results = YouTubeSearchResults()
        self.search_results.video_selected.connect(self._on_video_selected)
        
        channels = RecommendedChannels()
        
        layout.addWidget(self.search_results, 3)
        layout.addWidget(channels, 1)
        
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a;
                border-left: 1px solid #444;
            }
        """)
    
    def search_videos(self, event_name: str, year: int):
        """Search for race videos."""
        self.current_event = event_name
        self.current_year = year
        results = search_race_replay(event_name, year, limit=8)
        self.search_results.set_results(results, event_name, year)
    
    def _on_video_selected(self, video_data: dict):
        """Handle video selection - play in embedded player."""
        video_id = video_data.get('video_id', '')
        
        if video_id:
            youtube_url = f"https://www.youtube.com/watch?v={video_id}"
            webbrowser.open(youtube_url)
        else:
            link = video_data.get('link', '')
            if link:
                webbrowser.open(link)
