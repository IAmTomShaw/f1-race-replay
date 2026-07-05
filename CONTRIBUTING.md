# Contributing to F1 Race Replay 🏎️

First off — thanks for taking the time to contribute! Whether you're fixing a bug, building a new feature, or improving the docs, every contribution helps make this project better for F1 fans and developers everywhere.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Features](#suggesting-features)
  - [Submitting a Pull Request](#submitting-a-pull-request)
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Coding Guidelines](#coding-guidelines)
- [Roadmap & Feature Ideas](#roadmap--feature-ideas)
- [Recognition](#recognition)

---

## Code of Conduct

Be excellent to each other. This is a community project — respectful and constructive communication is expected from everyone. Harassment, gatekeeping, or dismissive behaviour toward contributors (especially newcomers) won't be tolerated.

---

## Getting Started

1. **Fork** the repository and clone it locally
2. Create a new branch for your work: `git checkout -b feature/your-feature-name`
3. Set up your dev environment (see [Development Setup](#development-setup))
4. Make your changes and test them
5. Push your branch and open a pull request

---

## How to Contribute

### Reporting Bugs

Found something broken? Please [open a Bug Report issue](.github/ISSUE_TEMPLATE/bug_report.md) and include:

- Steps to reproduce the bug
- What you expected vs. what actually happened
- Your Python version, OS, and any relevant package versions
- Screenshots or terminal output if relevant

> **Known issues:** The leaderboard can be temporarily inaccurate in the first few corners and when drivers pit. These are known telemetry limitations — check open issues before filing a duplicate.

---

### Suggesting Features

Got an idea? [Open a Feature Request](.github/ISSUE_TEMPLATE/feature_request.md). Check the [roadmap](roadmap.md) first to see if it's already planned.

Good feature ideas include:
- Telemetry charts (speed, throttle, braking)
- Post-race summary visualisations
- Race control messages display
- Improved qualifying insights
- Multi-driver telemetry comparison

---

### Submitting a Pull Request

1. Make sure your branch is up to date with `main`
2. Keep PRs focused — one feature or fix per PR is ideal
3. Write clear commit messages (e.g. `fix: correct leaderboard position on lap 1`)
4. Reference any related issues in your PR description (e.g. `Closes #42`)
5. Ensure your code runs without errors before submitting
6. Add comments for anything non-obvious

PRs will be reviewed as soon as possible. You may be asked to make changes — that's totally normal and part of the process.

---

## Development Setup

### Requirements

- Python 3.9+
- pip

### Install Dependencies

```bash
git clone https://github.com/thealxlabs/f1-race-replay.git
cd f1-race-replay
pip install -r requirements.txt
```

### Run the Replay

```bash
# Race replay
python main.py --viewer --year 2024 --round 1

# Qualifying session
python main.py --viewer --year 2024 --round 1 --qualifying

# Sprint qualifying (if applicable)
python main.py --viewer --year 2024 --round 1 --qualifying --sprint
```

### Key Dependencies

| Package   | Purpose                                      |
|-----------|----------------------------------------------|
| FastF1    | F1 lap timing, telemetry, and position data  |
| Arcade    | 2D visualisation and GUI rendering           |
| PySide6   | Race selection GUI                           |

---

## Project Structure

```
f1-race-replay/
├── main.py                    # Entry point — loads session, starts replay
├── requirements.txt
├── README.md
├── roadmap.md
├── resources/
│   └── preview.png
├── src/
│   ├── f1_data.py             # Telemetry loading, processing, frame generation
│   ├── arcade_replay.py       # Visualisation and UI logic
│   ├── ui_components.py       # Buttons, leaderboard
│   ├── interfaces/
│   │   ├── qualifying.py      # Qualifying interface
│   │   └── race_replay.py     # Race replay interface + Safety Car rendering
│   ├── cli/
│   │   └── race_selection.py  # CLI argument handling
│   ├── gui/
│   │   └── race_selection.py  # GUI race selector (PySide6)
│   └── lib/
│       └── tyres.py           # Tyre type definitions
```

**Where to look when making changes:**

- Changing track style, colours, or UI layout → `src/arcade_replay.py`
- Modifying telemetry processing → `src/f1_data.py`
- Adding a new UI component → `src/ui_components.py`
- Building a new session type → `src/interfaces/`

---

## Coding Guidelines

- Follow [PEP 8](https://pep8.org/) for Python style
- Use descriptive variable names — clarity beats brevity
- Add docstrings to new functions and classes
- Avoid committing debug `print()` statements
- Don't hard-code values that belong in config or constants
- If you're using the `PitWallWindow` base class for custom telemetry windows, document your window's purpose at the top of the file

---

## Roadmap & Feature Ideas

Check [roadmap.md](roadmap.md) for planned features and current priorities. If you'd like to work on something from the roadmap, comment on the relevant issue so we can assign it and avoid duplicate effort.

---

## Recognition

Contributors are acknowledged in [contributors.md](contributors.md). If you've had a feature or fix merged, you'll be added there. Thank you for helping build something cool. 🏁
