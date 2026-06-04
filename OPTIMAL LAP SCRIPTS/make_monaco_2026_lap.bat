@echo off
setlocal enabledelayedexpansion

set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
set "ROOT=%~dp0"
set "SVG=%ROOT%Circuit_Monaco.svg"
set "OUTLINE=%ROOT%F1_Pipeline_Assets\tracks\monaco_grand_prix_outline.json"
set "RACELINE=%ROOT%F1_Pipeline_Assets\tracks\monaco_grand_prix_raceline.json"
set "CSV=%ROOT%F1_Pipeline_Assets\exports\monaco_2026_synthetic.csv"
set "OUTMP4=%ROOT%monaco_grand_prix_2026_optimal_lap.mp4"

if not exist "%PYTHON%" goto :err_py
if not exist "%SVG%"    goto :err_svg

echo === Stage 1: SVG -^> outline (Monaco 3337 m, 9.0 m wide) ===
"%PYTHON%" "%ROOT%svg_to_outline.py" --svg "%SVG%" --out "%OUTLINE%" --track-length 3337 --road-width 9.0
if errorlevel 1 goto :err

echo === Stage 2: raceline + Monaco 2026 physics sim (Rev1 + locked Z-mode) ===
"%PYTHON%" "%ROOT%sim_monaco_2026_lap.py" --outline "%OUTLINE%" --raceline-out "%RACELINE%" --csv-out "%CSV%"
if errorlevel 1 goto :err

echo === Stage 3: render video ===
"%PYTHON%" "%ROOT%raceline_video.py" --outline "%OUTLINE%" --raceline "%RACELINE%" --telemetry-csv "%CSV%" --track-name "Monaco Grand Prix" --out "%OUTMP4%"
if errorlevel 1 goto :err

echo.
echo Done. -^> %OUTMP4%
pause & exit /b 0

:err_py
echo ERROR: Python not found at %PYTHON%
pause & exit /b 1

:err_svg
echo ERROR: SVG not found at %SVG%
pause & exit /b 1

:err
echo FAILED with errorlevel %errorlevel%
pause & exit /b 1
