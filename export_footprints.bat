@echo off
cd /d "%~dp0pipeline\scripts"
python export_footprints.py
pause
