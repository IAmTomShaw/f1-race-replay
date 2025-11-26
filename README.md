# F1 Race Replay 🏎️ 🏁

A Python application for visualizing Formula 1 race telemetry and replaying race events with interactive controls and a graphical interface. This fork includes enhanced features and improvements to the original project.

![Race Replay Preview](./resources/preview.png)

## Features

- **Race Replay Visualization:** Watch the race unfold with real-time driver positions on a rendered track.
- **Enhanced Leaderboard:** Live driver positions sorted by actual race distance covered with dynamic position updates.
- **Lap & Time Display:** Track the current lap (based on race leader) and total race time in HH:MM:SS format.
- **Driver Status Tracking:** Drivers who retire or go out are marked as "OUT" on the leaderboard (based on relative distance).
- **Interactive Controls:** Pause, rewind, fast forward, and adjust playback speed using on-screen buttons or keyboard shortcuts.
- **On-Screen Legend:** Comprehensive controls legend displayed in the interface.
- **Data Caching:** Pre-computed telemetry data is saved and reused for faster subsequent loads.
- **Smooth Track Rendering:** Interpolated track boundaries for smoother visual display.

## What's New in This Fork

- **Improved Leaderboard Logic:** Positions now accurately reflect race distance covered rather than just position data.
- **Enhanced Time Display:** Race time shown in hours:minutes:seconds format.
- **Better Driver Status Detection:** Retired/out drivers identified using relative distance metric.
- **Data Persistence:** Computed telemetry data is cached in JSON format for faster reloads.
- **Refresh Data Option:** Added `--refresh-data` flag to force recomputation of telemetry.
- **Lap-by-Lap Distance Tracking:** Race distance calculated cumulatively across laps for accurate positioning.
- **Optimized Track Rendering:** Track lines are pre-interpolated with 2000 points for smooth display.

## Controls

### Keyboard Shortcuts
- **Pause/Resume:** `SPACE`
- **Rewind:** `←` (left arrow) - Jump back 5 frames
- **Fast Forward:** `→` (right arrow) - Jump forward 5 frames
- **Increase Speed:** `↑` (up arrow) - Double playback speed
- **Decrease Speed:** `↓` (down arrow) - Halve playback speed
- **Set Speed Directly:** 
  - `1` - 0.5x speed
  - `2` - 1x speed (normal)
  - `3` - 2x speed
  - `4` - 4x speed

## Requirements

- Python 3.8+
- [FastF1](https://github.com/theOehrly/Fast-F1) - F1 telemetry data access
- [Arcade](https://api.arcade.academy/en/latest/) - 2D graphics and GUI
- numpy - Numerical computations
- json - Data serialization

Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the main script and specify the year and round:
```bash
python main.py --year 2025 --round 12
```

The application will load pre-computed telemetry data if available from a previous run. To force re-computation of telemetry data (useful after rule changes or data updates), use the `--refresh-data` flag:
```bash
python main.py --year 2025 --round 12 --refresh-data
```

### Examples
```bash
# Watch the 2024 Monaco Grand Prix
python main.py --year 2024 --round 8

# Watch the 2023 Japanese Grand Prix with fresh data
python main.py --year 2023 --round 16 --refresh-data
```

## File Structure

```
f1-race-replay/
├── main.py                          # Entry point, handles arguments and starts replay
├── src/
│   ├── f1_data.py                  # Telemetry loading, processing, and frame generation
│   └── arcade_replay.py            # Visualization engine and UI logic
├── resources/
│   ├── preview.png                 # Preview image
│   └── background.png              # Optional background image (if available)
├── computed_data/                   # Cached telemetry data (auto-generated)
├── .fastf1-cache/                  # FastF1 cache directory (auto-generated)
└── requirements.txt                # Python dependencies
```

## Technical Details

### Data Processing (`f1_data.py`)
- Loads race session data using FastF1 API
- Processes lap-by-lap telemetry for all drivers
- Computes cumulative race distance across laps
- Resamples telemetry to 25 FPS timeline
- Caches processed data in JSON format for reuse

### Visualization (`arcade_replay.py`)
- Renders track with interpolated boundaries
- Displays driver positions as colored circles
- Shows live leaderboard sorted by race distance
- Includes lap counter and race time display
- Provides interactive playback controls

## Customization

- **Track Width:** Modify `track_width` parameter in `build_track_from_example_lap()` (default: 500)
- **Screen Resolution:** Adjust `SCREEN_WIDTH` and `SCREEN_HEIGHT` in `arcade_replay.py` (default: 1920x1080)
- **Frame Rate:** Change `FPS` constant in `f1_data.py` (default: 25)
- **Colors:** Driver colors are automatically fetched from FastF1, but can be customized in `driver_colors` dict
- **UI Layout:** Modify text positions and sizes in the `on_draw()` method

## Contributing

Contributions are welcome! Feel free to:
- Open pull requests for UI improvements or new features
- Report issues on GitHub
- Suggest enhancements or optimizations

## Known Issues

- Occasional telemetry data gaps may cause minor accuracy issues with the leaderboard
- Background image must be manually added to `resources/background.png`
- Very long races may generate large cache files

## Credits

**Original Project:** [F1 Race Replay](https://github.com/tomshaw650/f1-race-replay) by [Tom Shaw](https://tomshaw.dev)

This fork builds upon the excellent foundation created by Tom Shaw, adding enhanced data processing, improved leaderboard accuracy, and additional features for a better viewing experience.

## 📝 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

No copyright infringement intended. Formula 1, F1, and related trademarks are the property of Formula One Licensing BV, a Formula 1 company. All data used is sourced from publicly available APIs via the FastF1 library and is used for educational and non-commercial purposes only. This project is not affiliated with, endorsed by, or connected to Formula 1 or its affiliates.

---

**Forked and enhanced with ❤️**  
Original work by [Tom Shaw](https://tomshaw.dev) | [Original Repository](https://github.com/tomshaw650/f1-race-replay)