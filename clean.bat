@echo off
cd /d "%~dp0src"

echo Cleaning src/ (keeping .csv files)...
for %%f in (*.*) do (
    if /i not "%%~xf"==".csv" del /q "%%f"
)

echo Cleaning footprint.pretty/...
if exist "..\footprint.pretty" rd /s /q "..\footprint.pretty"

echo Cleaning __pycache__/...
if exist "__pycache__" rd /s /q "__pycache__"

echo Clean complete.
pause
