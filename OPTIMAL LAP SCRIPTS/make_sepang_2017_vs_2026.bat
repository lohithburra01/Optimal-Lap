@echo off
rem Sepang: 2017-era car (recreated) vs the shipped 2026 optimal lap, same clock, one map.
rem 2017 car = same physics engine (sim_2026_lap.py imported, untouched) with 2017 regs: passive
rem aero + DRS zones, ICE+120 kW MGU-K full power, 733 kg. Calibrated on REAL 2018 Q telemetry
rem (6 tracks, cache/era2017/_calibrate_2017_v2.py: top speed + lap exact, corr 0.95-0.98), then the
rem Sepang wing (median of high-DF tracks) trimmed -5.6%% CL to Hamilton's 2017 pole 1:30.076
rem (untrimmed 1:29.23 = the 2018 car, ~1%% faster - matches the real 2017->2018 pole ratio).
rem The 2026 lap/csv/raceline are READ ONLY here.
setlocal
set "ROOT=%~dp0"
set "PYTHON=C:\Users\91910\AppData\Local\Programs\Python\Python310\python.exe"
"%PYTHON%" "%ROOT%cache\era2017\_sepang_2017.py" || exit /b 1
"%PYTHON%" "%ROOT%cache\era2017\dual_lap_video.py" --outline "%ROOT%F1_Pipeline_Assets\tracks\malaysian_grand_prix_outline.json" --a-csv "%ROOT%cache\era2017\sepang_2017.csv" --a-raceline "%ROOT%cache\era2017\sepang_2017_rl.json" --a-label "2017 CAR" --a-lap 90.076 --b-csv "%ROOT%F1_Pipeline_Assets\exports\sepang_2026_synthetic.csv" --b-raceline "%ROOT%F1_Pipeline_Assets\tracks\malaysian_grand_prix_raceline.json" --b-label "2026 CAR" --b-lap 91.772 --title "2017 vs 2026" --track-name "Sepang" --zoom 18 --out "%ROOT%sepang_2017_vs_2026.mp4" || exit /b 1
echo DONE: %ROOT%sepang_2017_vs_2026.mp4
