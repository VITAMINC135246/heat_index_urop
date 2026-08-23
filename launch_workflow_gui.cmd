@echo off
setlocal
set "PROJECT_DIR=%~dp0"
set "PYTHONW=%PROJECT_DIR%.venv\Scripts\pythonw.exe"
if not exist "%PYTHONW%" (
  echo Project environment is missing: %PYTHONW%
  echo Install requirements before launching the GUI.
  pause
  exit /b 1
)
start "" /D "%PROJECT_DIR%" "%PYTHONW%" "%PROJECT_DIR%scripts\workflow_gui.py"
