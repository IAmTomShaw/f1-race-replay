# Contributing to F1 Race Replay 🏎️ 🛠️

First off, thank you for considering to contribute! Any contributions you make are **greatly appreciated**.

Whether you're fixing a bug, improving documentation, or adding a cool new feature, we're glad to have you on board.

## Getting Started

1.  **Fork the repository** on GitHub.
2.  **Clone your fork** locally:
    ```bash
    git clone https://github.com/YOUR-USERNAME/f1-race-replay.git
    cd f1-race-replay
    ```
3.  **Create a virtual environment** (recommended) and install dependencies:
    ```bash
    python -m venv venv
    # Windows
    .\venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    
    pip install -r requirements.txt
    ```

## Development Workflow

1.  **Create a new branch** for your feature or fix:
    ```bash
    git checkout -b feature/amazing-feature
    ```
2.  **Make your changes**. Please try to keep your changes focused and atomic.
3.  **Test your changes**. Run the application to ensure everything works as expected.
    ```bash
    python main.py --year 2024 --round 1
    ```

## Coding Standards

To keep the codebase clean, maintainable, and robust, please adhere to the following guidelines:

### 1. Modular Architecture
We have recently refactored the project into a modular structure. Please respect this organization:
- **`src/data/`**: All data fetching, processing, and session management logic goes here.
- **`src/ui/components/`**: Individual UI widgets (like the Leaderboard, Controls, etc.) should be in their own files here.
- **`src/interfaces/`**: High-level window classes (like `RaceReplayWindow`) reside here.

Avoid adding code to the root `src/` folder if it can be placed in a specific submodule.

### 2. Type Checking
We use Python type hints to ensure code quality and catch errors early.
- **Always add type annotations** to function arguments and return values.
- **Use `typing` module** (e.g., `List`, `Dict`, `Optional`, `Tuple`) for complex types.
- Ensure your code passes static analysis.

**Example:**
```python
# Good
def calculate_speed(distance: float, time: float) -> float:
    return distance / time

# Avoid
def calculate_speed(distance, time):
    return distance / time
```

### 3. Code Style
- Follow **PEP 8** guidelines for Python code.
- Use descriptive variable and function names.
- Add comments for complex logic, but let the code speak for itself where possible.

## Submitting a Pull Request

1.  **Push your branch** to your fork:
    ```bash
    git push origin feature/amazing-feature
    ```
2.  **Open a Pull Request** on the main repository.
3.  **Describe your changes**. Explain *what* you changed and *why*.
4.  **Link to issues**. If your PR fixes a specific issue, please link to it (e.g., "Fixes #123").

## Reporting Issues

Found a bug? Have a feature request? Please open an issue on GitHub!
- **Search existing issues** first to see if it has already been reported.
- **Be specific**. Include steps to reproduce the bug, or a clear description of the feature you'd like to see.

---

Thank you for helping make F1 Race Replay better for everyone!
