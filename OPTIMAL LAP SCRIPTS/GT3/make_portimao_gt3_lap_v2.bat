@echo off
rem Portimao GT3 v2 (2026-10-14): car = MEASURED real AMG GT3 Evo onboard envelope; track reshaped so the TUM engine line
rem drives the real car's curvature; hills from 2021 FastF1 z. Notes: GT3\portimao\gt3_car_notes.md (v2 section).
rem Track reshape (slow, ~25 min): python GT3\portimao\reshape_track.py 8 0.6   -> picks it 4 (_rs_outline_4 / _rs_rl_4)
set "ROOT=%~dp0..\"
set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
set "PYTHONIOENCODING=utf-8"
cd /d "%ROOT%"
"%PYTHON%" GT3\portimao\_finalize_real.py GT3\portimao\_rs_outline_4.json GT3\portimao\_rs_rl_4.json || exit /b 1
"%PYTHON%" cache\_check_ontrack.py GT3\portimao\assets\portimao_gt3real_outline.json GT3\portimao\assets\portimao_gt3real_raceline.json portimao_gt3real
"%PYTHON%" raceline_video.py --outline GT3\portimao\assets\portimao_gt3real_outline.json --raceline GT3\portimao\assets\portimao_gt3real_raceline.json --telemetry-csv GT3\portimao\assets\portimao_gt3real_synthetic.csv --track-name "Portimão · Mercedes-AMG GT3" --zoom 28 --out GT3\portimao\videos\portimao_gt3_2026_optimal_lap_v2.mp4 || exit /b 1
