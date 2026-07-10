import subprocess
import atexit
import os
import time
import multiprocessing
import sys

# Global holders for the processes
fastapi_process = None
tauri_process = None

# 1. MOVE THIS TO THE TOP LEVEL
# Python cannot "pickle" functions defined inside other functions
def run_uvicorn_server():
    try:
        from uvicorn import Server, Config
        # Ensure the path points to your new src/services/bridge.py
        config = Config("src.services.bridge:app", host="127.0.0.1", port=8000, log_level="info")
        server = Server(config=config)
        server.run()
    except ImportError:
        print("❌ Error: uvicorn not found. Are you sure the venv is active?")
    except Exception as e:
        print(f"❌ Bridge failed to start: {e}")

def start_fastapi_sidecar():
    global fastapi_process
    print("🏎️ Starting Bridge Service...")

    # Create the process targeting the top-level function
    fastapi_process = multiprocessing.Process(target=run_uvicorn_server)
    fastapi_process.daemon = True # Closes if the main script dies
    fastapi_process.start()

    print(f"📡 Bridge Service PID: {fastapi_process.pid}")

def start_tauri_frontend():
    global tauri_process
    print("🎨 Launching Tauri frontend...")
    # Tauri still uses subprocess because it's an external Node.js/Rust process
    tauri_process = subprocess.Popen(
        ["npm", "run", "tauri", "dev"],
        cwd="ui-v2",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid if os.name != 'nt' else None
    )
    print(f"🖼️ Tauri frontend PID: {tauri_process.pid}")

def cleanup_processes():
    print("\nCleaning up background processes...")

    # Multiprocessing cleanup
    if fastapi_process and fastapi_process.is_alive():
        print(f"Terminating Bridge Service (PID: {fastapi_process.pid})...")
        fastapi_process.terminate()
        fastapi_process.join()

    # Subprocess cleanup
    if tauri_process and tauri_process.poll() is None:
        print(f"Terminating Tauri frontend (PID: {tauri_process.pid})...")
        try:
            os.killpg(os.getpgid(tauri_process.pid), 15) # SIGTERM
        except:
            tauri_process.terminate()

    print("Background processes cleaned up.")

if __name__ == "__main__":
    # Ensure multiprocessing works correctly on all OS types
    multiprocessing.freeze_support()

    atexit.register(cleanup_processes)

    start_fastapi_sidecar()
    time.sleep(2) # Give the bridge a head start
    start_tauri_frontend()

    print("\n✅ Proof of Concept application started.")
    print("🔗 Bridge: http://127.0.0.1:8000")
    print("🛑 Press Ctrl+C to stop everything.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        sys.exit(0)
