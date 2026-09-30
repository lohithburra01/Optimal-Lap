@echo off
rem Sepang (Malaysian GP) 2026 optimal lap - NO-REFERENCE method (2026-09-30).
rem Sepang has no 2025 (or any OpenF1-era) lap, so the pre-FP1 transfer/autofit
rem cannot run. Instead: fleet-median car knobs (median of the 7 autofit tracks:
rem cda 0.6139, cl 4.97), ISA rho @ ~40 m. Validated two ways (cache/sepang_2026_noref.md):
rem   A) cache/_noref_backtest.py - fleet-median sim vs real 2026 Q, sd ~2.1%%
rem   B) cache/_era_ratio_2017_2026.py - 2017 pole x 2017->2026 ratio = 1:31.4 +/- 0.8
rem Inset 0.5 m keeps the line on-track at the T9 hairpin (inset 0 cut the apex 0.67 m).
setlocal
set "ROOT=%~dp0"
set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
set "OUTLINE=%ROOT%F1_Pipeline_Assets\tracks\malaysian_grand_prix_outline.json"
set "RACELINE=%ROOT%F1_Pipeline_Assets\tracks\malaysian_grand_prix_raceline.json"
set "CSV=%ROOT%F1_Pipeline_Assets\exports\sepang_2026_synthetic.csv"
set "OUTMP4=%ROOT%malaysian_grand_prix_2026_optimal_lap.mp4"
if not exist "%PYTHON%" (echo ERROR: Python not found at %PYTHON% & exit /b 1)
echo === Stage 1: SVG -^> outline ===
"%PYTHON%" "%ROOT%svg_to_outline.py" --svg "%ROOT%Sepang.svg" --out "%OUTLINE%" --track-length 5543 --road-width 16.0 --min-corner-radius 9.0 || exit /b 1
echo === Stage 2: sim (fleet-median knobs, no reference lap) ===
"%PYTHON%" "%ROOT%sim_2026_lap.py" --outline "%OUTLINE%" --raceline-out "%RACELINE%" --csv-out "%CSV%" --reference-csv NONE --inset 0.5 --cda 0.6139 --cl 4.97 --rho 1.2202 || exit /b 1
echo === Stage 3: gate (t_ref = 2017 pole 90.076; no 2025 lap exists) ===
"%PYTHON%" "%ROOT%cache\_gate_2026.py" "%CSV%" 90.076
"%PYTHON%" "%ROOT%cache\_check_ontrack.py" "%OUTLINE%" "%RACELINE%" sepang
echo === Stage 4: render ===
"%PYTHON%" "%ROOT%raceline_video.py" --outline "%OUTLINE%" --raceline "%RACELINE%" --telemetry-csv "%CSV%" --track-name "Malaysian Grand Prix" --zoom 18 --out "%OUTMP4%" || exit /b 1
echo DONE: %OUTMP4%
