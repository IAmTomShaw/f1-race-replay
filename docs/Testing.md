# Testing

This project uses `pytest` for automated tests.

## Install test dependencies

For local development, create and activate a virtual environment first:

    python3 -m venv .venv
    source .venv/bin/activate

Then install the development requirements:

    python -m pip install --upgrade pip
    python -m pip install -r requirements-dev.txt

## Run the test suite

Run all tests with:

    python -m pytest

Run only the lightweight unit tests with:

    python -m pytest tests/lib

## Test strategy

The initial test suite focuses on lightweight modules that do not require:

- live FastF1 data downloads
- opening GUI windows
- an OpenGL context
- a running race replay session

The current suite includes:

- unit tests for time formatting and parsing
- unit tests for tyre compound mapping
- unit tests for season detection
- unit tests for settings persistence with temporary files
- smoke import tests for project modules
- unit tests for Pit Wall Dashboard dock initialization and preset views
- unit tests for practice session telemetry extraction and stint analysis

Some import smoke tests may be skipped locally when optional runtime dependencies are not installed.

### GUI tests (`tests/gui/`)

Tests for PySide6-based components. These require the `PySide6` package to be installed and will be automatically skipped otherwise.

| File | What it covers |
|------|---------------|
| `test_pit_wall_dashboard.py` | Dashboard initialization with all 5 dock panels, preset view toggling (Full Pit Wall, Quad View, Driver Focus) |

### Feature tests

| File | What it covers |
|------|---------------|
| `test_practice.py` | Practice session telemetry extraction (`get_practice_telemetry`), best lap leaderboard structure, stint analysis output format |

## Running all tests

Run the full suite:

    python -m pytest

Run only lightweight unit tests:

    python -m pytest tests/lib

<<<<<<< HEAD
Run GUI-specific tests:

    python -m pytest tests/gui -v

=======
Run feature tests individually:

    python -m pytest tests/test_practice.py -v
>>>>>>> feat/practice-session
