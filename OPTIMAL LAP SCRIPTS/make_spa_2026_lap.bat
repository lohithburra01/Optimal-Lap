@echo off
setlocal enabledelayedexpansion

rem ============================================================================
rem Belgian GP 2026 optimal lap - PRE-FP1 pipeline (zero 2026-session data).
rem Calibration: track's own 2025 Q lap + empirical 2025->2026 transfer
rem (docs/2026-07-15-prefp1-universal-calibration-design.md). FP1, once it
rem exists, is used only to VERIFY (fetch_openf1_lap.py + cache/_overlay_speed.py).
rem ============================================================================

set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
set "ROOT=%~dp0"
set "SVG=%ROOT%Spa-Francorchamps_of_Belgium.svg"
set "OUTLINE=%ROOT%F1_Pipeline_Assets\tracks\belgian_grand_prix_outline.json"
set "RACELINE=%ROOT%F1_Pipeline_Assets\tracks\belgian_grand_prix_raceline.json"
set "CSV=%ROOT%F1_Pipeline_Assets\exports\spa_2026_synthetic.csv"
set "REF25=%ROOT%F1_Pipeline_Assets\exports\reference_2025_spa_q.csv"
set "OUTMP4=%ROOT%belgian_grand_prix_2026_optimal_lap.mp4"
set "ELEV=%ROOT%F1_Pipeline_Assets\tracks\belgian_grand_prix_elevation.json"

if not exist "%PYTHON%" goto :err_py
if not exist "%SVG%"    goto :err_svg

echo === Stage 0: 2025 Spa Q reference (FastF1 broken upstream; OpenF1) ===
rem non-fatal if offline; the existing CSV is reused (NOR 100.562s)
if not exist "%REF25%" "%PYTHON%" "%ROOT%fetch_openf1_lap.py" --year 2025 --country "Belgium" --session "Qualifying" --out "%REF25%"

echo === Stage 1: SVG -^> outline (7004 m, 14.0 m wide, R_min 9.0) ===
"%PYTHON%" "%ROOT%svg_to_outline.py" --svg "%SVG%" --out "%OUTLINE%" --track-length 7004 --road-width 14.0 --min-corner-radius 9.0
if errorlevel 1 goto :err

echo === Stage 2: predict 2026 targets from 2025 ref + transfer ===
"%PYTHON%" "%ROOT%cache\_predict_track.py" --track spa
if errorlevel 1 goto :err

echo === Stage 3: autofit cda/cl to targets (runs the 2026 sim internally) ===
"%PYTHON%" "%ROOT%cache\_autofit_2026.py" --track spa
if errorlevel 2 goto :err
copy /Y "%ROOT%cache\autofit_spa_sim.csv" "%CSV%" >nul
copy /Y "%ROOT%cache\autofit_spa_rl.json" "%RACELINE%" >nul

echo === Stage 4: realism gate (predicted bands; 2025 pole 100.562) ===
"%PYTHON%" "%ROOT%cache\_gate_2026.py" "%CSV%" 100.562 --targets "%ROOT%cache\predicted_spa.json"
if errorlevel 1 goto :err

echo === Stage 5: render video (honest sim lap time on the HUD) ===
"%PYTHON%" "%ROOT%raceline_video.py" --outline "%OUTLINE%" --raceline "%RACELINE%" --telemetry-csv "%CSV%" --track-name "Belgian Grand Prix" --zoom 30 --elevation-json "%ELEV%" --out "%OUTMP4%"
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
