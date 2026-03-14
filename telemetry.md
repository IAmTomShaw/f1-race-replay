# F1 Race Replay - Telemetry Stream Demo

This document provides instructions on how to use the telemetry stream feature which is currently in early demo stage. This allows you to see the raw telemetry data being streamed from the replay process in real-time, and is intended for developers who want to build custom tools and interfaces on top of the replay data.

![Telemetry Stream Demo](./resources/telemetry-logger.png)

## How to Use

Ensure you have the latest version of the application with telemetry support and have already setup an environment with the required dependencies (see `README.md` for setup instructions).

1. **Start the F1 Race Replay and pass the --telemetry flag:**
   ```bash
   python main.py --telemetry
   ```

2. **Select a race session from the GUI.** The telemetry stream will start automatically when the replay begins.

3. **The demo window will show:**
   - **Raw telemetry stream**: JSON data as it comes from the race replay
   - **Summary tab**: Session overview with message counts and current state
   - **Drivers tab**: Current driver positions, speeds, and lap information  
   - **Events tab**: Track status changes and race events

## Why this feature is huge!

The telemetry stream provides a powerful way to access all the rich data from the race replay enabling you to build custom interfaces on top of the replay data.

The goal of this project is to build a pit wall style tool to replay races and sessions. So being able to access telemetry data in other windows outside of the main replay window is a key to unlocking a lot of potential features and customizations.

We're no longer limited to fitting everything into the replay window - we can build custom dashboards, data analysis tools etc that can run alongside the replay and provide a much richer experience.

## Telemetry Data Format

The stream provides this data structure:

```json
{
  "frame": {
    "drivers": {
      "ALB": {
        "brake": 0.0,
        "dist": 4428.078064476834,
        "drs": 1,
        "gear": 7,
        "lap": 1,
        "position": 8,
        "rel_dist": 0.7588,
        "speed": 282.0,
        "throttle": 100.0,
        "tyre": 3.0,
        "x": 5303.823151332268,
        "y": 554.943926757651
      },
      ... other drivers
    },
    "lap": 1,
    "t": 84.88,
    "weather": {
      "air_temp": 18.34674710038636,
      "humidity": 80.46747100386358,
      "rain_state": "DRY",
      "track_temp": 24.19349420077272,
      "wind_direction": 201.09865351318817,
      "wind_speed": 1.1532528996136413
    }
  },
  "frame_index": 2122,
  "is_paused": true,
  "playback_speed": 64.0,
  "session_data": {
    "lap": 1,
    "leader": "VER",
    "time": "00:01:24",
    "total_laps": 52
  },
  "total_frames": 148011,
  "track_status": "2"
}
```

## Technical Details

- **Protocol**: TCP socket on `localhost:9999`
- **Format**: JSON messages separated by newlines
- **Threading**: Network handling runs in background thread
- **UI Framework**: PySide6 (Qt for Python)