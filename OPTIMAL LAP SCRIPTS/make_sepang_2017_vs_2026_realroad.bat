@echo off
rem Sepang 2017 vs 2026 on the REAL road (2026-10-01). Road edges from Esri z19 satellite imagery
rem (the SVG outline was 2-5 m off the tarmac in long stretches). 2017 line = min-time, per-corner
rem basin search (T1 inside attack, as HAM 2017 pole onboard); car trimmed (cl only) to 1:30.076.
rem 2026 = same fleet-median knobs + builder on the real road (inside T1 tested: +0.10 s, rejected) -> 1:32.001.
rem Imagery steps (tiles cached in cache\era2017\sat\tiles): _sat_sepang.py, _sat_align.py, _sat_edges.py, _sat_outline.py.
setlocal
set "ROOT=%~dp0"
set "E=%ROOT%cache\era2017"
set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
cd /d "%E%"
"%PYTHON%" _sat_base.py || exit /b 1
"%PYTHON%" _opt_line_2017.py --base sepang_sat_base_rl.json --outline sepang_sat_outline.json --margin 0.3 --every 10 --scale 1.0074 --max-sweeps 60 --steps 2,1,0.5,0.25 --init-knots sat_init_knots.npy --out sat_optB || exit /b 1
"%PYTHON%" _opt_line_2017.py --base sepang_sat_base_rl.json --outline sepang_sat_outline.json --margin 0.3 --every 10 --scale 1.0074 --steps 2,1,0.5 --max-sweeps 40 --init-knots t1_inside_init.npy --arc-range 250,800 --out t1in_p2 || exit /b 1
"%PYTHON%" _corner_basins.py --init t1in_p2_knots.npy --out basins || exit /b 1
"%PYTHON%" _sepang_2017_sat.py || exit /b 1
cd /d "%ROOT%"
rem 2026: true-scale copy of the satellite outline, builder line, S/F-aligned (rl_builder_sf.json), sim
"%PYTHON%" sim_2026_lap.py --outline "%E%\sat2026\sepang_sat_outline_true.json" --raceline-in "%E%\sat2026\rl_builder_sf.json" --raceline-out "%E%\sat2026\rl_2026_final.json" --csv-out "%E%\sat2026\sepang_2026_sat.csv" --reference-csv NONE --inset 0.5 --cda 0.6139 --cl 4.97 --rho 1.2202 || exit /b 1
"%PYTHON%" "%E%\dual_lap_video.py" --outline "%E%\sepang_sat_outline.json" --a-csv "%E%\sepang_2017_sat.csv" --a-raceline "%E%\sepang_2017_sat_rl.json" --a-label "2017 CAR" --a-lap 90.076 --b-csv "%E%\sat2026\sepang_2026_sat.csv" --b-raceline "%E%\sat2026\rl_2026_final_frame.json" --b-label "2026 CAR" --b-lap 92.001 --title "2017 vs 2026" --track-name "Sepang" --zoom 18 --out "%ROOT%sepang_2017_vs_2026_realroad.mp4" || exit /b 1
echo DONE
