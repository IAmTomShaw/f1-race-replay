@echo off
REM Initialize variable
set "VENV_EXISTS=false"
set "VENV_FOLDER=X"

REM Check if .venv or venv folder exists
IF EXIST ".venv" (
    set "VENV_EXISTS=true"
    set "VENV_FOLDER=.venv"
) ELSE IF EXIST "venv" (
    set "VENV_EXISTS=true"
    set "VENV_FOLDER=venv"
)

IF "%VENV_EXISTS%"=="true" (
    echo Python virtual environment found.
) ELSE (
    REM Neither exists, create Python virtual environment called .venv
    python -m venv .venv
    set "VENV_EXISTS=true"
    echo Python virtual environment created.
    set "VENV_FOLDER=.venv"
)

REM Activate virtual environment
call "%VENV_FOLDER%\Scripts\activate.bat"

REM Install dependencies
pip install -r requirements.txt

REM Change directory to GUI folder and install Node.js dependencies
cd gui
call npm install

REM Start the GUI
cls
call npm run dev