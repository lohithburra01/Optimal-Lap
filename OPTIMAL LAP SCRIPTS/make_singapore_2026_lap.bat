@echo off
rem Singapore (Marina Bay) 2026 optimal lap - v4 (2026-10-08): OFFICIAL-GEOMETRY track.
rem The SVG's corner shapes made the 2025-vs-2026 gap swing (T7/T10/T11/T14/T16 drawn as 11-15 m kinks).
rem Track = official map-matched path (top-10 2025 Q laps) @ FIA 4927 m, 10 m wide, R>=10 (the SVG is used only
rem to fix the frame). Marina Bay is anticlockwise -> sim on the x-mirror (engine drives CW).
rem Singapore STREET GRIP 0.723 (mechanical term only, env SG_MECH): measured on a physical 2025 car vs RUS's real
rem 2025 pole (cache/singapore/_fit_street_grip.py), applied unchanged to the 2026 car. GAIN guard 36.3 wrapper.
rem Line = apex-touch optimiser (margin 0.3, apex-w 1.5, one corner set) + knob refit, 2 rounds -> fixed point.
rem Result (v4b, T8-T9 wide entry) cda 0.558 cl 4.323 -> 93.01 s; gate 9/9; all S-bend crossings >= 0.91. v3: cache/singapore/v3_backup.
setlocal
set "ROOT=%~dp0"
set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
set "T=%ROOT%F1_Pipeline_Assets\tracks"
set "SG=%ROOT%cache\singapore"
set "M=%T%\singapore_grand_prix_mirror_outline.json"
set "REF25=%ROOT%F1_Pipeline_Assets\exports\reference_2025_singapore_q.csv"
set "CSV=%ROOT%F1_Pipeline_Assets\exports\singapore_2026_synthetic.csv"
set "SG_MECH=0.7230"
if not exist "%REF25%" "%PYTHON%" "%ROOT%fetch_openf1_lap.py" --year 2025 --country Singapore --session Qualifying --out "%REF25%"
echo === Stage 1: frame from the SVG, geometry from the official path ===
"%PYTHON%" "%ROOT%svg_to_outline.py" --svg "%ROOT%Marina_Bay_circuit_2023.svg" --out "%ROOT%cache\singapore_outline_autoSF.json" --track-length 4940 --road-width 12.0 --min-corner-radius 10.0 || exit /b 1
"%PYTHON%" "%ROOT%cache\_singapore_prep.py" prep || exit /b 1
copy /Y "%T%\singapore_grand_prix_outline.json" "%T%\singapore_grand_prix_outline_svgraw.json" >nul
if not exist "%SG%\path_samples.json" "%PYTHON%" "%SG%\_fetch_path_multi.py" || exit /b 1
if not exist "%SG%\rus2025_car_data.json" "%PYTHON%" "%SG%\_rus2025_car.py" || exit /b 1
"%PYTHON%" "%SG%\_official_path.py" || exit /b 1
"%PYTHON%" "%SG%\_build_official_outline.py" || exit /b 1
echo === Stage 2-3: predict + autofit (street grip) ===
"%PYTHON%" "%ROOT%cache\_predict_track.py" --track singapore || exit /b 1
"%PYTHON%" "%ROOT%cache\_autofit_singapore.py" || exit /b 1
copy /Y "%ROOT%cache\autofit_singapore_rl.json" "%SG%\base_k_rl.json" >nul
"%PYTHON%" -c "import numpy as np,sys;sys.path.insert(0,r'%ROOT%cache\era2017');import _opt_line_2017 as O;O.setup(r'%SG%\base_k_rl.json',r'%M%',None,None,0.3,12);np.save(r'%SG%\zero_k.npy',np.zeros(len(O.G['kidx'])))" || exit /b 1
echo === Stage 3b: apex-touch line + refit, 2 rounds ===
"%PYTHON%" "%SG%\_opt_line_2026_sg.py" --base "%SG%\base_k_rl.json" --outline "%M%" --cda 0.618 --cl 6.327 --rho 1.2232 --margin 0.3 --apex-w 1.5 --apex-knots "%SG%\zero_k.npy" --out "%SG%\k1" || exit /b 1
"%PYTHON%" "%SG%\_autofit_rl_in_sg.py" "%SG%\k1_rl.json" || exit /b 1
"%PYTHON%" "%SG%\_opt_line_2026_sg.py" --base "%SG%\base_k_rl.json" --outline "%M%" --cda 0.554 --cl 4.348 --rho 1.2232 --margin 0.3 --apex-w 1.5 --steps 1,0.5,0.25 --init-knots "%SG%\k1_knots.npy" --apex-knots "%SG%\zero_k.npy" --out "%SG%\k2" || exit /b 1
"%PYTHON%" "%SG%\_autofit_rl_in_sg.py" "%SG%\k2_rl.json" || exit /b 1
"%PYTHON%" "%SG%\_scan_crossings.py" "%SG%\base_k_rl.json" "%M%" "%SG%\k2_rl.json"
rem v4b (user): T8->T9 wide entry - the line must touch the far side before T9 (RUS 2025 onboard). Costs the
rem 2026 car ~0.08 s (pure lap 92.113 vs 92.034); refit cda 0.558 cl 4.323 -> 93.01 s, gate 9/9.
"%PYTHON%" "%SG%\_seed_wide.py" "%SG%\base_k_rl.json" "%M%" "%SG%\k2_knots.npy" "%SG%\seed26_wide.npy" 2040 2140 0.8 || exit /b 1
"%PYTHON%" "%SG%\_opt_line_2026_sg.py" --base "%SG%\base_k_rl.json" --outline "%M%" --cda 0.559 --cl 4.363 --rho 1.2232 --margin 0.3 --apex-w 1.5 --steps 1,0.5,0.25 --init-knots "%SG%\seed26_wide.npy" --apex-knots "%SG%\zero_k.npy" --touch 2060,2120,1980 --out "%SG%\k3w" || exit /b 1
"%PYTHON%" "%SG%\_autofit_rl_in_sg.py" "%SG%\k3w_rl.json" || exit /b 1
copy /Y "%ROOT%cache\autofit_singapore_sim_best.csv" "%CSV%" >nul
copy /Y "%ROOT%cache\autofit_singapore_rl.json" "%T%\singapore_grand_prix_mirror_raceline.json" >nul
"%PYTHON%" "%ROOT%cache\_singapore_prep.py" unmirror "%T%\singapore_grand_prix_mirror_raceline.json" "%T%\singapore_grand_prix_raceline.json" || exit /b 1
echo === Stage 4: checks ===
"%PYTHON%" "%ROOT%cache\_gate_2026.py" "%CSV%" 89.241 --targets "%ROOT%cache\predicted_singapore.json"
"%PYTHON%" "%ROOT%cache\_check_ontrack.py" "%T%\singapore_grand_prix_outline.json" "%T%\singapore_grand_prix_raceline.json" singapore
"%PYTHON%" "%ROOT%cache\_corner_compare.py" "%CSV%" "%REF25%" 4927
echo === Stage 5: render ===
"%PYTHON%" "%ROOT%raceline_video.py" --outline "%T%\singapore_grand_prix_outline.json" --raceline "%T%\singapore_grand_prix_raceline.json" --telemetry-csv "%CSV%" --track-name "Singapore Grand Prix" --zoom 28 --out "%ROOT%singapore_grand_prix_2026_optimal_lap.mp4" || exit /b 1
echo DONE
