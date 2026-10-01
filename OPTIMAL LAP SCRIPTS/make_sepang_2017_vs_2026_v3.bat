@echo off
rem Sepang 2017 vs 2026 v3 (2026-10-01, user spec): SVG track, shipped 2026 lap 1:31.772; 2017 on the
rem min-time line (T1 inside, anti-zigzag; build steps in make_sepang_2017_vs_2026_v2.bat) trimmed to HAM 1:30.076
rem (cl -18.1%%). Video: fixed zoom 19 following the 2026 car, speed-heatmap trail+dot (2017 dulled),
rem trailing car's trail on top at 70%% opacity, minimap under the cars, lap times instead of stopwatch.
setlocal
set "ROOT=%~dp0"
set "E=%ROOT%cache\era2017"
set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
"%PYTHON%" "%E%\_sepang_2017_svg_pole.py" || exit /b 1
"%PYTHON%" "%E%\dual_lap_video_v3.py" --outline "%ROOT%F1_Pipeline_Assets\tracks\malaysian_grand_prix_outline.json" --a-csv "%E%\sepang_2017_svg_pole.csv" --a-raceline "%E%\sepang_2017_svg_pole_rl.json" --a-lap 90.076 --b-csv "%ROOT%F1_Pipeline_Assets\exports\sepang_2026_synthetic.csv" --b-raceline "%ROOT%F1_Pipeline_Assets\tracks\malaysian_grand_prix_raceline.json" --b-lap 91.772 --zoom 19 --out "%ROOT%sepang_2017_vs_2026_v3.mp4" || exit /b 1
echo DONE
