

## Backtest v1 — leave-one-out, 4 tracks

| track | ref | cda | cl | rho | lap sim | real | corr | top err | corner med | worst | fails |
|---|---|---|---|---|---|---|---|---|---|---|---|
| canada | Q | 0.619 | 5.20 | 1.224 | 71.54 | 72.58 | 0.968 | +2.2 | +13.2 | +24.4 | **2** |
| catalunya | Q | 0.731 | 6.50 | 1.210 | 68.48 | 75.04 | 0.979 | -10.0 | +10.6 | +35.0 | **4** |
| austria | FP1 | 0.572 | 4.05 | 1.147 | 66.07 | 67.84 | 0.971 | +1.9 | +10.4 | -20.8 | **0** |
| silverstone | FP1 | 0.747 | 5.18 | 1.208 | 83.68 | 89.64 | 0.931 | +13.6 | +8.6 | +42.4 | **3** |

### canada (v1)
- PASS `corr`: 0.968 (>= 0.94)
- FAIL `lap_rail`: 71.54s > 71.70s
- PASS `lap_band`: 71.54s in [71.08,72.58] (Q ref)
- PASS `top`: +2.2 km/h (band +-11.8)
- FAIL `corners`: median +13.2, worst +24.4
- corners (sim vs real 2026): 0.073:+17, 0.165:-11, 0.285:+24, 0.460:-19, 0.614:+17, 0.900:+10

### catalunya (v1)
- PASS `corr`: 0.979 (>= 0.94)
- FAIL `lap_rail`: 68.48s > 72.35s
- FAIL `lap_band`: 68.48s in [73.54,75.04] (Q ref)
- FAIL `top`: -10.0 km/h (band +-5.0)
- FAIL `corners`: median +10.6, worst +35.0
- corners (sim vs real 2026): 0.186:+2, 0.376:+17, 0.461:+4, 0.551:+1, 0.626:+35, 0.756:-1, 0.816:+32, 0.934:+30

### austria (v1)
- PASS `corr`: 0.971 (>= 0.94)
- PASS `lap_rail`: 66.07s > 64.77s
- PASS `lap_band`: 66.07s in [64.34,66.84] (FP1 ref)
- INFO `top`: +1.9 km/h (band +-11.8, informational: FP1 ref)
- PASS `corners`: median +10.4, worst -20.8 (FP1 rule [-5,+15] on median)
- corners (sim vs real 2026): 0.106:-21, 0.323:+18, 0.511:+10, 0.633:+10, 0.705:-19, 0.880:+12, 0.927:+11

### silverstone (v1)
- FAIL `corr`: 0.931 (>= 0.94)
- FAIL `lap_rail`: 83.68s > 85.69s
- FAIL `lap_band`: 83.68s in [86.14,88.64] (FP1 ref)
- INFO `top`: +13.6 km/h (band +-11.8, informational: FP1 ref)
- PASS `corners`: median +8.6, worst +42.4 (FP1 rule [-5,+15] on median)
- corners (sim vs real 2026): 0.156:+4, 0.179:-6, 0.342:-24, 0.371:+22, 0.538:+42, 0.683:-14, 0.860:+18, 0.938:+13
