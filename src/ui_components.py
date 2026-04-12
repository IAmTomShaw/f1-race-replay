from .ui import (
    BaseComponent,
    LegendComponent,
    WeatherComponent,
    LeaderboardComponent,
    LapTimeLeaderboardComponent,
    DriverInfoComponent,
    ControlsPopupComponent,
    QualifyingSegmentSelectorComponent,
    SessionInfoComponent,
    RaceProgressBarComponent,
    RaceControlsComponent,
    QualifyingLapTimeComponent,
    extract_race_events,
    build_track_from_example_lap,
    plotDRSzones,
    draw_finish_line
)

# This module is now a wrapper for the modularized src/ui package.
# New code should import directly from src.ui.
