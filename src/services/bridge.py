import asyncio
import json
import socket
import pickle
import os
import polars as pl
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

TCP_HOST = "127.0.0.1"
TCP_PORT = 9999
COMPUTED_DIR = "./computed_data"

def load_session_metadata(year, round_num):
    file_path = os.path.join(COMPUTED_DIR, f"{year}_{round_num}_R.pkl")
    if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
            data = pickle.load(f)

            return pl.from_pandas(data) if hasattr(data, 'to_numpy') else pl.DataFrame(data)
    return None

@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # 1. Connect to Engine on Port 9999
    try:
        reader, writer = await asyncio.open_connection('127.0.0.1', 9999)
        while True:
            # 2. Read the raw JSON line from the engine
            line = await reader.readline()
            if not line: break

            # 3. Parse and extract a specific driver (e.g., the lead driver)
            raw_frame = json.loads(line.decode())
            drivers = raw_frame.get("frame", {}).get("drivers", {})

            if drivers:
                # Pick the first driver found or a specific tag
                driver_id = list(drivers.keys())[0]
                telemetry = drivers[driver_id]

                # 4. Map to UI's expected format
                ui_payload = {
                    "speed": telemetry.get("speed", 0),
                    "throttle": telemetry.get("throttle", 0) / 100,
                    "brake": telemetry.get("brake", 0) / 100,
                    "driver": driver_id,
                    "pos": {"x": telemetry.get("x"), "y": telemetry.get("y")}
                }
                await websocket.send_json(ui_payload)

    except Exception as e:
        print(f"Connection lost: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
