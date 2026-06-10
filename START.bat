@echo off
echo ================================================
echo  Rwanda MCI Surveillance System
echo ================================================

:: Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Install from https://python.org
    pause
    exit /b
)

:: Install dependencies
echo Installing dependencies...
pip install flask flask-cors requests beautifulsoup4 ntscraper -q

:: Create folders
if not exist data mkdir data
if not exist logs mkdir logs

:: Run
echo Starting server on http://localhost:5050
echo Press Ctrl+C to stop.
echo.
python app.py
pause
