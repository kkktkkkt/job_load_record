@echo off
chcp 65001 > nul
cd /d "%~dp0"

echo Installing libraries...
pip install -r requirements.txt -q

echo Starting Activity Tracker...
start "" pythonw tracker.py

echo.
echo Tracker started in system tray.
echo Right-click the tray icon to open dashboard or quit.
echo.
pause
