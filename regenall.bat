@echo off
cd /d "%~dp0"
echo === Generating footprints ===
python scripts\source_to_footprint\gen_footprints.py
echo.
echo === Generating PCB ===
python scripts\source_to_pcb\pintokicad.py
echo.
echo === Generating schematic ===
python scripts\source_to_sch\pintokicad_sch.py
echo.
pause
