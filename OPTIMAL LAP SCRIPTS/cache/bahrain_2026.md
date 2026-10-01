# Bahrain (Sakhir) 2026 optimal lap - 2026-10-01

Standard pre-FP1 pipeline (2025 Q ref PIA 1:29.841). Real 2026 race at Sakhir does not exist
(the 2026 "Bahrain GP" meeting ran at Sepang) -> no post-weekend verification pair.

SVG screening (cache/_corner_compare.py probe, cda .6139 cl 4.97, vs 2025 x r(v25)):
- Circuit_Bahrain.svg REJECTED: 2.5 seg/turn, worst corner 37 km/h, 6/8 >10, T1 +19, drawn R~6 m apex.
- ..._Grand_Prix_Layout_with_DRS.svg: 5.9 seg/turn, worst 17, T1 -2. T10 drawn as sharp V
  (centre R~9 m, inside edge folds to a cusp) -> line 1.1 m off at T10 apex.
  Candidates: inset 0.5 (0.70 m off), minR 12 (0.86, worse corners), local T10 rounding
  sigma 12/18 (+inset 0.5/0.7), inset 1.0 (0.42) -> CHOSEN inset 1.2 on the unmodified map:
  0/2682 off (worst 0.29 m), worst corner 12, 2/8 >10, corr 0.975.
Autofit: cda 0.8005, cl 4.4693, rho 1.2242 -> 1:32.186 (+2.34 s vs 2025 pole), top 316.7.
Gate 8/9: GAIN median 30.5 > fixed 28 cap. Not a physics fault: sim/real-2025 gain ratio on
shipped tracks = 1.26-1.52 (canada 1.28, hungary 1.42, zandvoort 1.30, spa 1.26, austria 1.52);
bahrain 30.5/21.2 = 1.44 -> inside. Fixed cap is Catalunya/Canada-derived (see playbook).
Fitted corners: worst 15 km/h (esses -15, T11 -12), 2/8 >10, trace corr 0.973.
Elevation: OpenF1 z, 2025 Q PIA lap 14: span 16.4 m, closure +0.0. Absolute datum (-16..0 m
"ASL") looks offset - relative profile only. Video zoom 18 with elevation flyover.
