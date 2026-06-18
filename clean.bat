@echo off
cd /d "%~dp0reforming"

echo Cleaning reforming/ (keeping .csv files)...
for %%f in (*.*) do (
    if /i not "%%~xf"==".csv" del /q "%%f"
)

echo Cleaning reforming.pretty/...
if exist "..\reforming.pretty" rd /s /q "..\reforming.pretty"

echo Cleaning __pycache__/...
if exist "__pycache__" rd /s /q "__pycache__"

echo Clean complete.
pause
