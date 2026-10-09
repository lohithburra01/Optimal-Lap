# 2025 -> 2026 pattern study (2026-10-09)

Goal (user): find universal 2025->2026 patterns from real data and use them as a robust, reliable predictor of
each coming weekend's optimal-lap speed graph; compare with our physics optimal laps.

## Data
Real fastest-Q laps, OpenF1 car_data on the official clock, for every circuit raced in both 2025 and 2026 so far
(`_fetch_pairs.py` -> raw/). 12 usable pairs: Catalunya, Hungaroring, Melbourne, Miami, Monte Carlo, Montreal, Monza,
Shanghai, Silverstone, Spa, Spielberg, Zandvoort. Suzuka excluded (2026 trace inconsistent: 5388 m, corr 0.41);
Sakhir/Jeddah 2026 not held; Baku 2025 fetch failed (retry). Library: `hlib.py` (laps + corner-anchored alignment).

## Universal patterns (`_patterns.py`, patterns.png)
- Lap growth 2025->2026: median +3.5% (p10 +1.9, p90 +4.3).
- Corner minima: 2026 ~3% slower in slow corners, ~7% from 120 km/h up (scatter +-4%).
- Full-throttle accel: 2026 >= 2025 below ~210 km/h (bigger MGU-K); lower above ~220.
- ENERGY CLIPPING (the 2026 signature): at >=250 km/h, 2026 accel 4.3 m/s^2 in the first 2 s of a run, ~0 by 7 s,
  negative after (car slows at full throttle). On long straights the 2026 car out-accelerates 2025 early, peaks
  EARLIER and HIGHER, then fades to ~the 2025 speed at the braking point. Top speed ~equal (-10..+13).
- Braking decel (as measured from 3.7 Hz data) 10-20% lower in 2026 between 100-240 km/h.
- Note: absolute accel/decel from 3.7 Hz telemetry is biased low (~2.4 g braking) - only DIFFERENCES are usable.

## Model (`rmodel.py`, ratio-field) and the HYBRID
v26(s) = v25(s) * q(s). The 2025 lap is cut into ACCEL (corner min -> next peak) and BRAKE (peak -> next min)
phases; q(u) is the pooled 2026/2025 ratio vs position-fraction u in the phase, per phase-length class
(<250, 250-600, >600 m; one BRAKE class), with corner minima from the speed-dependent ratio R(v25).
HYBRID = that SHAPE, rescaled so the lap = 2025 pole x median growth of the other tracks.
(Rejected on the way: absolute-integration models v1/v2 in `pmodel.py` - +2.4..3 s slow; integration over-pins
high speed and clipping in time-since-corner does not transfer.)

## Validation (leave-one-out, `_loo3.py`, `_vs_physics.py`)
| | lap |err| median | trace RMSE median |
|---|---|---|
| naive (2025 x median growth) | 0.44 s | 15.7 km/h |
| ratio model alone | 1.12 s | 12.0 |
| **HYBRID** | **0.44 s** | **11.8** |
| our PHYSICS optimal laps (9 shipped, vs real 2026 Q) | **1.31 s, too fast on 8/9** | **21.4** |
Pre-FP1 physics only: 1.63 s / 24.1 km/h vs hybrid 0.36 s / 12.2 km/h.

## Singapore (`_singapore_predict.py`, singapore_pattern_vs_physics.png)
Hybrid from RUS 2025 (89.158) x 1.035 = 1:32.274 (p10-p90 1:30.85-1:33.01) - FP1 fastest was 1:32.274 (RUS);
the identical time is a coincidence, but the FP1 TRACE stays within +-0.4 s of the prediction all lap.
Physics optimal 1:33.008 is +0.73 s: T5 +0.56, T7-T9 +0.58, T10-T13 +0.13, final +0.25; gains -0.33 at T1 and
-0.61 on the run to T16 (too much top speed, no clipping fade).

## What the physics pipeline gets wrong (universal)
1. No energy-clipping SHAPE: long straights keep accelerating (Singapore 321 vs 308 real).
2. Braking starts too early / zones too long.
3. Corner speeds inherit track-drawing errors (+-20-40 km/h at single corners).
4. Net: laps too fast by ~1.3 s median, traces ~2x the error of the pattern hybrid.
