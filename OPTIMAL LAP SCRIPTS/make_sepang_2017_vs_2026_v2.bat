@echo off
rem Sepang 2017 vs 2026 v2 (2026-10-01, user spec): SVG track (shipped outline), shipped 2026 lap 1:31.772,
rem 2017 car UNCHANGED (sepang_2017_report.json car, cl 4.037) on a min-time line: T1 inside attack (HAM 2017
rem onboard), per-corner basin search, anti-zigzag penalty 0.006 -> 1:27.727 (user: keep car, no re-trim).
rem Video: no telemetry graph, all text white except DEPLOY/BRAKING/SUPERCLIP (own colours) and DRS (green).
setlocal
set "ROOT=%~dp0"
set "E=%ROOT%cache\era2017"
set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
set "B=..\..\F1_Pipeline_Assets\tracks\malaysian_grand_prix_raceline.json"
set "OL=..\..\F1_Pipeline_Assets\tracks\malaysian_grand_prix_outline.json"
cd /d "%E%"
rem (svg_t1_inside_init.npy = opt2017_knots.npy with T1 entry knots 330-600 m set to the inside edge)
"%PYTHON%" _opt_line_2017.py --base %B% --outline %OL% --margin 0.5 --every 12 --scale 1.0 --steps 2,1,0.5 --max-sweeps 40 --init-knots svg_t1_inside_init.npy --arc-range 250,800 --out svg_t1in || exit /b 1
"%PYTHON%" _corner_basins.py --base %B% --outline %OL% --margin 0.5 --every 12 --scale 1.0 --init svg_t1in_knots.npy --out svg_basins || exit /b 1
"%PYTHON%" _opt_line_2017.py --base %B% --outline %OL% --margin 0.5 --every 12 --scale 1.0 --steps 1,0.5,0.25 --max-sweeps 40 --smooth-w 0.006 --init-knots svg_basins_knots.npy --out svg_sm0.006 || exit /b 1
"%PYTHON%" _sepang_2017_svg_keepcar.py || exit /b 1
cd /d "%ROOT%"
"%PYTHON%" "%E%\dual_lap_video.py" --outline "%ROOT%F1_Pipeline_Assets\tracks\malaysian_grand_prix_outline.json" --a-csv "%E%\sepang_2017_svg_keepcar.csv" --a-raceline "%E%\sepang_2017_svg_keepcar_rl.json" --a-label "2017 CAR" --a-lap 87.727 --b-csv "%ROOT%F1_Pipeline_Assets\exports\sepang_2026_synthetic.csv" --b-raceline "%ROOT%F1_Pipeline_Assets\tracks\malaysian_grand_prix_raceline.json" --b-label "2026 CAR" --b-lap 91.772 --title "2017 vs 2026" --track-name "Sepang" --zoom 18 --no-graph --white-text --out "%ROOT%sepang_2017_vs_2026_v2.mp4" || exit /b 1
echo DONE
