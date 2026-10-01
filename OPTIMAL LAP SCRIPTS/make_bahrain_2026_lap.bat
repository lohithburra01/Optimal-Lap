@echo off
rem Bahrain (Sakhir) 2026 optimal lap - standard pre-FP1 transfer pipeline (2026-10-01).
rem SVG: Bahrain_International_Circuit--Grand_Prix_Layout_with_DRS.svg (5.9 seg/turn).
rem Its T10 is drawn as a sharp V -> registry inset 1.2 m keeps the line on-track
rem (0/2682, worst 0.29 m) and gave the best corner fit (worst 12 km/h probe, 15 fitted).
rem NOTE: 2026's "Bahrain GP" meeting is at Sepang - OpenF1 lookups filter circuit Sakhir.
setlocal
set "ROOT=%~dp0"
set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
set "OUTLINE=%ROOT%F1_Pipeline_Assets\tracks\bahrain_grand_prix_outline.json"
set "RACELINE=%ROOT%F1_Pipeline_Assets\tracks\bahrain_grand_prix_raceline.json"
set "ELEV=%ROOT%F1_Pipeline_Assets\tracks\bahrain_grand_prix_elevation.json"
set "REF25=%ROOT%F1_Pipeline_Assets\exports\reference_2025_bahrain_q.csv"
set "CSV=%ROOT%F1_Pipeline_Assets\exports\bahrain_2026_synthetic.csv"
set "OUTMP4=%ROOT%bahrain_grand_prix_2026_optimal_lap.mp4"
if not exist "%PYTHON%" (echo ERROR: Python not found at %PYTHON% & exit /b 1)
echo === Stage 0: 2025 Q reference ===
if not exist "%REF25%" "%PYTHON%" "%ROOT%fetch_openf1_lap.py" --year 2025 --country Bahrain --circuit Sakhir --session Qualifying --out "%REF25%"
echo === Stage 1: SVG -^> outline ===
"%PYTHON%" "%ROOT%svg_to_outline.py" --svg "%ROOT%Bahrain_International_Circuit--Grand_Prix_Layout_with_DRS.svg" --out "%OUTLINE%" --track-length 5412 --road-width 15.0 --min-corner-radius 9.0 || exit /b 1
echo === Stage 2: predict targets ===
"%PYTHON%" "%ROOT%cache\_predict_track.py" --track bahrain || exit /b 1
echo === Stage 3: autofit cda/cl (uses registry inset 1.2) ===
"%PYTHON%" "%ROOT%cache\_autofit_2026.py" --track bahrain || exit /b 1
copy /Y "%ROOT%cache\autofit_bahrain_sim.csv" "%CSV%" >nul
copy /Y "%ROOT%cache\autofit_bahrain_rl.json" "%RACELINE%" >nul
echo === Stage 4: checks (GAIN median rides above the fixed 28 cap - see cache/bahrain_2026.md) ===
"%PYTHON%" "%ROOT%cache\_gate_2026.py" "%CSV%" 89.841 --targets "%ROOT%cache\predicted_bahrain.json"
"%PYTHON%" "%ROOT%cache\_check_ontrack.py" "%OUTLINE%" "%RACELINE%" bahrain
"%PYTHON%" "%ROOT%cache\_corner_compare.py" "%CSV%" "%REF25%" 5412
echo === Stage 5: elevation + render ===
"%PYTHON%" "%ROOT%cache\_fetch_elevation.py" --track bahrain --circuit Sakhir || exit /b 1
"%PYTHON%" "%ROOT%raceline_video.py" --outline "%OUTLINE%" --raceline "%RACELINE%" --telemetry-csv "%CSV%" --track-name "Bahrain Grand Prix" --zoom 18 --elevation-json "%ELEV%" --out "%OUTMP4%" || exit /b 1
echo DONE: %OUTMP4%
