@echo off
rem Portimao GT3 quali-pace (2026-10-15, user Option A): v2 measured car/line/track, tyre grip x1.112 (fresh tyres, quali)
rem -> 1:39.850, beats GT Open 2025 pole 1:39.966. Run make_portimao_gt3_lap_v2.bat first (writes the v2 track/line).
set "ROOT=%~dp0..\"
set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
set "PYTHONIOENCODING=utf-8"
cd /d "%ROOT%"
"%PYTHON%" GT3\portimao\_quali_grip.py 99.85 || exit /b 1
"%PYTHON%" GT3\portimao\_build_elevation.py || exit /b 1
"%PYTHON%" raceline_video.py --outline GT3\portimao\assets\portimao_gt3real_outline.json --raceline GT3\portimao\assets\portimao_gt3real_raceline.json --telemetry-csv GT3\portimao\assets\portimao_gt3quali_synthetic.csv --track-name "Portimão · Mercedes-AMG GT3" --zoom 25 --elev-scale 1.7 --elevation-json GT3\portimao\assets\portimao_gt3real_elevation.json --out GT3\portimao\videos\portimao_gt3_2026_optimal_lap_quali_elev_z25.mp4 || exit /b 1
