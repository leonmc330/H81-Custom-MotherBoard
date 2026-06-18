@echo off
cd /d "%~dp0"
python scripts\cleanup\prune_dangling.py
pause
