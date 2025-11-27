import sys
from src.arcade_replay import run_arcade_replay

def main():
    print("Starting F1 Replay App (Custom UI)...")
    run_arcade_replay()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)