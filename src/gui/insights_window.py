from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QPushButton, QTabWidget, QComboBox, QLabel, QScrollArea)
from PySide6.QtCore import Qt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from src.insights.chart_generator import RaceInsightCharts
import matplotlib.pyplot as plt


class InsightsWindow(QMainWindow):
    """Window for displaying race insights and charts."""
    
    def __init__(self, session, driver_colors, parent=None):
        super().__init__(parent)
        self.session = session
        self.driver_colors = driver_colors
        self.chart_generator = RaceInsightCharts(session, driver_colors)
        
        self.setWindowTitle(f"Race Insights - {session.event['EventName']}")
        self.setGeometry(100, 100, 1400, 900)
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # Header
        header_layout = QHBoxLayout()
        title_label = QLabel(f"📊 Race Insights - {self.session.event['EventName']}")
        title_label.setStyleSheet("font-size: 18px; font-weight: bold; padding: 10px;")
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        header_layout.addWidget(close_btn)
        
        main_layout.addLayout(header_layout)
        
        # Tab widget for different charts
        self.tab_widget = QTabWidget()
        main_layout.addWidget(self.tab_widget)
        
        # Add tabs for each chart type
        self.add_track_evolution_tab()
        self.add_tyre_strategy_tab()
        self.add_pitstop_analysis_tab()
        self.add_driver_performance_tab()
        self.add_sector_comparison_tab()
        self.add_gap_analysis_tab()
        
    def add_track_evolution_tab(self):
        """Add track evolution chart tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Generate chart
        fig = self.chart_generator.get_track_evolution()
        canvas = FigureCanvasQTAgg(fig)
        toolbar = NavigationToolbar2QT(canvas, widget)
        
        layout.addWidget(toolbar)
        layout.addWidget(canvas)
        
        self.tab_widget.addTab(widget, "Track Evolution")
        
    def add_tyre_strategy_tab(self):
        """Add tyre strategy chart tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        fig = self.chart_generator.get_tyre_strategy()
        canvas = FigureCanvasQTAgg(fig)
        toolbar = NavigationToolbar2QT(canvas, widget)
        
        layout.addWidget(toolbar)
        layout.addWidget(canvas)
        
        self.tab_widget.addTab(widget, "Tyre Strategy")
        
    def add_pitstop_analysis_tab(self):
        """Add pit stop analysis chart tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        fig = self.chart_generator.get_pitstop_analysis()
        canvas = FigureCanvasQTAgg(fig)
        toolbar = NavigationToolbar2QT(canvas, widget)
        
        layout.addWidget(toolbar)
        layout.addWidget(canvas)
        
        self.tab_widget.addTab(widget, "Pit Stop Analysis")
        
    def add_driver_performance_tab(self):
        """Add driver performance chart tab with driver selection."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Driver selection
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("Select Drivers (Top 5 by default):"))
        
        self.driver_combo = QComboBox()
        self.driver_combo.addItem("Top 5 Finishers", None)
        for driver in self.session.drivers:
            self.driver_combo.addItem(driver, driver)
        
        control_layout.addWidget(self.driver_combo)
        
        refresh_btn = QPushButton("Refresh Chart")
        refresh_btn.clicked.connect(lambda: self.refresh_driver_performance(layout))
        control_layout.addWidget(refresh_btn)
        control_layout.addStretch()
        
        layout.addLayout(control_layout)
        
        # Initial chart
        fig = self.chart_generator.get_driver_performance()
        self.driver_perf_canvas = FigureCanvasQTAgg(fig)
        toolbar = NavigationToolbar2QT(self.driver_perf_canvas, widget)
        
        layout.addWidget(toolbar)
        layout.addWidget(self.driver_perf_canvas)
        
        self.tab_widget.addTab(widget, "Driver Performance")
        
    def refresh_driver_performance(self, layout):
        """Refresh driver performance chart with selected drivers."""
        selected = self.driver_combo.currentData()
        drivers = None if selected is None else [selected]
        
        # Remove old canvas
        layout.removeWidget(self.driver_perf_canvas)
        self.driver_perf_canvas.deleteLater()
        
        # Create new chart
        fig = self.chart_generator.get_driver_performance(drivers)
        self.driver_perf_canvas = FigureCanvasQTAgg(fig)
        layout.addWidget(self.driver_perf_canvas)
        
    def add_sector_comparison_tab(self):
        """Add sector comparison chart tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        fig = self.chart_generator.get_sector_comparison()
        canvas = FigureCanvasQTAgg(fig)
        toolbar = NavigationToolbar2QT(canvas, widget)
        
        layout.addWidget(toolbar)
        layout.addWidget(canvas)
        
        self.tab_widget.addTab(widget, "Sector Comparison")
        
    def add_gap_analysis_tab(self):
        """Add gap analysis chart tab with reference driver selection."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Reference driver selection
        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("Reference Driver:"))
        
        self.ref_driver_combo = QComboBox()
        self.ref_driver_combo.addItem("Race Winner", None)
        for driver in self.session.drivers:
            self.ref_driver_combo.addItem(driver, driver)
        
        control_layout.addWidget(self.ref_driver_combo)
        
        refresh_btn = QPushButton("Refresh Chart")
        refresh_btn.clicked.connect(lambda: self.refresh_gap_analysis(layout))
        control_layout.addWidget(refresh_btn)
        control_layout.addStretch()
        
        layout.addLayout(control_layout)
        
        # Initial chart
        fig = self.chart_generator.get_gap_analysis()
        self.gap_canvas = FigureCanvasQTAgg(fig)
        toolbar = NavigationToolbar2QT(self.gap_canvas, widget)
        
        layout.addWidget(toolbar)
        layout.addWidget(self.gap_canvas)
        
        self.tab_widget.addTab(widget, "Gap Analysis")
        
    def refresh_gap_analysis(self, layout):
        """Refresh gap analysis with selected reference driver."""
        ref_driver = self.ref_driver_combo.currentData()
        
        # Remove old canvas
        layout.removeWidget(self.gap_canvas)
        self.gap_canvas.deleteLater()
        
        # Create new chart
        fig = self.chart_generator.get_gap_analysis(ref_driver)
        self.gap_canvas = FigureCanvasQTAgg(fig)
        layout.addWidget(self.gap_canvas)
