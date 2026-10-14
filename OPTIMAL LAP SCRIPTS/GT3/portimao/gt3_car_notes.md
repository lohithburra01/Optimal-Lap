# Portimao GT3 optimal lap (Mercedes-AMG GT3 EVO) - build notes, 2026-10-14

Event: GTWC Europe Endurance finale, Portimao 16-18 Oct 2026; Verstappen Racing #3 (Verstappen/Barnicoat/Lulham).
Pre-qualifying version (user: ship pre-quali first, verify with Friday FP/Q).

## Track
- SVG: Portimao_GP.svg = Commons "Autodromo do Algarve alt.svg" (identical geometry to "... F1 Sectors.svg").
  Procrustes vs real 2021 F1 Q telemetry (FastF1, HAM): 8.0 m rms, not mirrored (other SVG: 11.0 m, different final corners).
- 4653 m, road width 13.0 m (pipeline default; NOT verified), min radius 9 m. Engine drives the real (clockwise) direction.
- Real S/F is 162 m before the sim's index 0 -> roll before render (GT3/portimao/_sf_check.py).
- Elevation (29 m span in 2021 FastF1 Z) NOT modelled in the sim (engine is flat).

## Reference lap
- International GT Open 2025 Portimao Q (27 Apr 2025, racingsportscars.com): pole 1:39.966 Porsche 992 GT3 R;
  best Mercedes-AMG GT3 Evo 1:40.051 (#9 GetSpeed, Bartone/Schiller). TARGET = 100.051 s.
  Caveat: GT Open BoP/tyres differ from GTWC (SRO BoP, Pirelli). Friday GTWC times will re-anchor.

## Car (GT3/portimao/sim_gt3_car.py, on the unchanged engine via cache/era2017/sim_2017_car.py)
Priors (assumptions, documented):
- mass 1420 kg = BoP ~1320 + driver 75 + quali fuel 25 (team sheet says 1285 kg base; SRO BoP sets per event)
- tractive power 365 kW (~550 hp BoP-restricted NA 6.2 V8 x 0.89 driveline)
- CdA 0.85 (Cd ~0.42 x 2.0 m^2) -> sim top 285 km/h at Portimao (only hint found: FastestLaps 283 km/h McLaren 720S, unverified)
- mu 1.70 lat/long, drive 1.20, accel cap 0.95 g, ABS-style flatter trail braking
- FITTED: cl 2.53 (-> 477 kg downforce @200 km/h, 746 kg @250) to hit 100.051 s on the base line.
Degeneracy: lap time alone cannot split mu vs downforce (mu 1.65 -> 588 kg@200, 1.75 -> 376 kg@200).
Friday speed traps / sector times should pin cda and the mu/cl split.
Sim-racing setup sheets were NOT used: they are setup settings, not physical constants.

## SHIPPED pre-quali (2026-10-14): portimao_gt3_2026_optimal_lap.mp4 (make_portimao_gt3_lap.bat)
- Line: min-time GT3 line (margin 0.9) -> apex-touch pass (_opt_line_gt3_apex.py, margin 0.3, apex-w 0.05):
  all 17 apex gaps <= 1.43 m; 0/2306 off-track. Rolled to real S/F (2021 FastF1).
- FINAL CAR: mu 1.60, cl 2.696 (509 kg @200, ~795 kg @250 = 56% of weight), cda 0.85, 365 kW, 1420 kg.
  Sim 1:40.051 (HUD 1:40.018), top 283.8, min 63.3 km/h.
- Mu/cl split chosen so downforce ~half the weight at 250 km/h (mu 1.70 gave 298 kg@200 = too little for GT3).
- raceline_video.py: added "BRAKING" HUD label colour (GT3 CSV writes BRAKING instead of REGEN).
- NEXT (Fri 16 Oct): GTWC FP/Q times + speed traps -> re-anchor target (SRO BoP/Pirelli), pin cda + mu/cl split.

## v2 (2026-10-14) - REPLACES v1 (user rejected v1: line from my pattern search + apex penalty, car fitted to a lap time)
Source: real AMG GT3 Evo onboard, Portimao trackday 2021 (YouTube WT6IaGKG9Ic, Race Navigator overlay), ~1:43.0.
Speed OCR + lateral g -> real_amg_gt3_trackday.json; kinematic accel = dv/dt (slope removed with 2021 FastF1 z).
CAR = measured envelope only (gt3_car_measured.json):
- power/drag: least squares on 4 sustained full-throttle runs -> 319 kW, CdA 1.09 (resid 0.04 g). (p95 binning gave
  324 kW / 0.78 -> 276 km/h top; dv/dt noise inflates percentiles - don't use percentiles for power.)
- lateral: g_lat at the 7 corner apices -> mu_lat 1.67, cl 0.39 (readout quantised 0.1 g; slow corners only).
- braking: decel p95 per bin 60-180 km/h -> mu_long 1.42, trail_v 135, trail_min 0.10, trail_exp 0.86. traction 0.85 g.
HILLS: sim_gt3_car.simulate(elev=True default) adds g*sin(slope) fwd/back; z from 2021 FastF1 by lap fraction.
TRACK: the SVG's radii are wrong both ways (slow corners too open; fast kinks too sharp: 75 m kink at km 2.4 that the real
car drives at R~210 m / 205 km/h). reshape_track.py: centreline curvature += 0.6*(k_real - k_engine_line), rebuild by
heading integration, TUM line rebuilt each pass (no add-ons). it 4 chosen: RMSE 6.3 km/h, lap 103.61, top 263 (real 259),
sections >= 62 m apart. Shape drifts from the SVG (user: track accuracy doesn't matter). Line runs opposite to outline
index order -> curvature sign must be matched (first run diverged on that).
Corner mins (real / sim km/h): 141/126, 61/61, 55/65, 80/82, 96/90, 74/78, 87/94.
