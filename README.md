# 🏎️ F1 REPLAY: The DSA-Powered Telemetry Engine

**F1 REPLAY** is a high-performance Python and React application that brings Formula 1 race telemetry to life. It combines real-world F1 data extraction with an **Advanced Data Structures & Algorithms (DSA)** engine to track, analyze, and visualize driver telemetry in real-time.

---

## ✨ Legendary Features

- **🌲 Quad-Tree Spatial Tracking**: Under the hood, a custom Quad Tree algorithm (`dsa_engine.py`) dynamically partitions the track geometry, allowing lightning-fast spatial queries to detect driver proximity and battling zones.
- **🛡️ Dynamic Buffer Zones & DRS Trains**: Implements Disjoint Set Union (DSU) and Interval Trees to calculate buffer zones between cars. If drivers are within striking distance, the engine draws real-time telemetry lines connecting the cars to visualize the battle for position!
- **🎯 Interactive Driver Tracking**: Click on any driver on the live leaderboard to lock onto them! A tracking circle will instantly lock onto their car, following their exact coordinates on the track geometry in real-time.
- **📊 Real-Time Telemetry Processing**: Uses the `fastf1` library to automatically download, parse, and cache official Formula 1 race data, lap times, and track statuses.
- **⚡ Modern Tech Stack**: A Python backend seamlessly connected to a React frontend (built with Vite) using [Eel](https://github.com/python-eel/Eel) for lightning-fast Desktop UI rendering.

---

## 🏗️ Architecture & Tech Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| **Data Structures**| Quad Trees, DSU, Interval Trees | Spatial proximity, DRS train clustering, and buffer zone calculations. |
| **Data Engine** | `fastf1`, `pandas`, `numpy` | Fetches and computes race telemetry and lap data. |
| **Frontend UI** | React, Vite, HTML/CSS | Renders the dashboard and AI strategy overlays. |
| **Integration** | Eel | Bridges Python logic with the JavaScript frontend. |

### 📂 Project Structure
```text
F1 REPLAY/
├── main.py              # Main entry point and Eel server initialization
├── src/
│   ├── f1_data.py       # fastf1 telemetry downloader and processor
│   ├── arcade_replay.py # 2D Race simulation engine with DSA visualizations
│   ├── track_geometry.py# Track plotting calculations
│   └── backend/
│       ├── ai_engine.py # Telemetry evaluation and strategy AI
│       └── dsa_engine.py# Quad Trees, DSU, and Interval Tree algorithms
├── web/                 # React frontend
│   ├── src/             # Frontend source code
│   ├── package.json
│   └── vite.config.js
├── computed_data/       # Cached processed JSON data
└── .fastf1-cache/       # Raw fastf1 API cache
```

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.9+**
- **Node.js 16+**

### 1. Backend Setup (Python)

1. **Clone the repository:**
   ```bash
   git clone https://github.com/your-username/F1-REPLAY.git
   cd F1-REPLAY
   ```

2. **Set up a Virtual Environment (Recommended):**
   ```bash
   python -m venv .venv
   # Windows
   .venv\Scripts\activate
   # macOS/Linux
   source .venv/bin/activate
   ```

3. **Install Python Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### 2. Frontend Setup (React/Vite)

You need to compile the frontend before running the Eel application.

```bash
cd web
npm install
npm run build
```

### 3. Running the Application

Return to the root directory and start the main application:

```bash
cd ..
python main.py
```
The application will launch a native desktop window via Eel.

---

## 🏎️ How the DSA Engine Works

The true power of this project lies in `dsa_engine.py`. Instead of iterating through every driver to check if they are battling (an O(N^2) operation), the engine inserts driver coordinates into a **Quad Tree**. When a driver's "Buffer Zone" is queried, the Quad Tree returns nearby cars in O(log N) time. 

Additionally, **Disjoint Set Union (DSU)** is used to dynamically cluster drivers into DRS trains, allowing the visualizer to draw striking lines between connected cars on the track.

---

## 📜 License

This project is licensed under the MIT License.
