@echo off
rem Portimao GTWC finale 2026 - Mercedes-AMG GT3 EVO optimal lap (PRE-QUALI, 2026-10-14). Notes: GT3\portimao\gt3_car_notes.md
rem Car: GT3\portimao\sim_gt3_car.py (GT3 on the unchanged engine), cl fitted to GT Open 2025 best AMG Q lap 1:40.051.
rem Line: min-time GT3 line + apex-touch pass (GT3\portimao\opt_gt3_apex_rl.json); _finalize rolls to the real S/F + refits cl.
set "ROOT=%~dp0..\"
set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
cd /d "%ROOT%"
"%PYTHON%" svg_to_outline.py --svg GT3\portimao\assets\Portimao_GP.svg --out GT3\portimao\assets\portimao_outline.json --track-length 4653 --road-width 13.0 --min-corner-radius 9.0 || exit /b 1
"%PYTHON%" GT3\portimao\_finalize.py GT3\portimao\opt_gt3_apex_rl.json 100.051 || exit /b 1
"%PYTHON%" cache\_check_ontrack.py GT3\portimao\assets\portimao_gt3_outline.json GT3\portimao\assets\portimao_gt3_raceline.json portimao_gt3
"%PYTHON%" raceline_video.py --outline GT3\portimao\assets\portimao_gt3_outline.json --raceline GT3\portimao\assets\portimao_gt3_raceline.json --telemetry-csv GT3\portimao\assets\portimao_gt3_synthetic.csv --track-name "Portimão · Mercedes-AMG GT3" --zoom 18 --out GT3\portimao\videos\portimao_gt3_2026_optimal_lap.mp4 || exit /b 1
