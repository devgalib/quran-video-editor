@echo off
rem Opens the Quran Video Editor. The first run creates .venv and installs Pillow + PySide6.
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  py -3 -m venv .venv || python -m venv .venv
  .venv\Scripts\pip install -r requirements.txt
)
start "" .venv\Scripts\pythonw.exe -m qve gui
