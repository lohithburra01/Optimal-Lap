@echo off
rem Singapore 2025 vs 2026 dual video - v4 (2026-10-08), on the official-geometry track (make_singapore_2026_lap.bat).
rem Car A = George Russell's REAL 2025 pole telemetry on the OFFICIAL CLOCK (0 at the line, 89.158 at the flag;
rem sector lines exact 26.475 / 63.804), placed by his real distance on his 2025-car line (distance-correct track:
rem dot speed == shown speed). 2025 line = same optimiser/corner set, physical 2025 car (2018-fit fleet cl, mass 800,
rem DRS from his channel, cda -> 316) with the measured street grip 0.723. Car B = the 2026 lap 1:33.01 (read-only).
setlocal
set "ROOT=%~dp0"
set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
set "T=%ROOT%F1_Pipeline_Assets\tracks"
set "SG=%ROOT%cache\singapore"
set "SG_MECH=0.7230"
"%PYTHON%" "%SG%\_opt_line_2025.py" --base "%SG%\base_k_rl.json" --outline "%T%\singapore_grand_prix_mirror_outline.json" --car "%SG%\street_grip.json" --margin 0.3 --apex-w 1.5 --steps 1,0.5,0.25 --init-knots "%SG%\k2_knots.npy" --apex-knots "%SG%\zero_k.npy" --out "%SG%\k25" || exit /b 1
rem T8->T9 (user, from RUS 2025 onboard): after the T8 exit the 2025 line must touch the far side before T9.
rem The optimiser alone stays inside; seeded wide + touch constraint -> 88.788 vs 88.792 s (no time cost).
"%PYTHON%" "%SG%\_seed_wide.py" "%SG%\base_k_rl.json" "%T%\singapore_grand_prix_mirror_outline.json" "%SG%\k25_knots.npy" "%SG%\seed25_wide.npy" 2040 2140 0.8 || exit /b 1
"%PYTHON%" "%SG%\_opt_line_2025.py" --base "%SG%\base_k_rl.json" --outline "%T%\singapore_grand_prix_mirror_outline.json" --car "%SG%\street_grip.json" --margin 0.3 --apex-w 1.5 --steps 1,0.5,0.25 --init-knots "%SG%\seed25_wide.npy" --apex-knots "%SG%\zero_k.npy" --touch 2060,2120,1980 --out "%SG%\k25w" || exit /b 1
"%PYTHON%" "%SG%\_finish2025_v4.py" || exit /b 1
"%PYTHON%" "%SG%\_rus2025_exact.py" "%SG%\sim2025_k25.csv" "%SG%\rus2025_exact.csv" || exit /b 1
"%PYTHON%" "%ROOT%cache\era2017\dual_lap_video_v3.py" --outline "%T%\singapore_grand_prix_outline.json" --a-csv "%SG%\rus2025_exact.csv" --a-raceline "%T%\singapore_2025_rus_raceline.json" --a-lap 89.158 --a-label "RUSSELL 2025 POLE" --a-tag 2025 --b-csv "%ROOT%F1_Pipeline_Assets\exports\singapore_2026_synthetic.csv" --b-raceline "%T%\singapore_grand_prix_raceline.json" --b-lap 93.01 --b-label "2026 OPTIMAL LAP" --b-tag 2026 --title "2025 vs 2026" --track-name "Singapore" --zoom 28 --out "%ROOT%singapore_2025_vs_2026.mp4" || exit /b 1
echo DONE
