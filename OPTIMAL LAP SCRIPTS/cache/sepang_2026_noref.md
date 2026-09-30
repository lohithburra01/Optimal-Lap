# Sepang 2026 (Bahrain GP relocated to Sepang) - no-reference optimal lap, 2026-09-30

Engine: clean = committed HEAD (Spa, 74f0d94) + banking physics. Proven bit-identical to the
shipped Zandvoort csv (2141/2141 rows, max |dv| 0.0). GPT Baku versions in
_quarantine_gpt_baku_2026-09-25/ (not deleted).

Method (Sepang has no OpenF1-era lap; last raced 2017):
- A) fleet-median knobs (median of 7 autofit tracks): cda 0.6139, cl 4.97, rho ISA@40m 1.2202.
  LOO backtest (cache/_noref_backtest.py, cache/noref_backtest/summary.json) vs real 2026 Q:
  canada +2.38%, catalunya -1.90, hungary -2.11, spa -2.51, zandvoort +0.54 -> mean -0.72%, sd ~2.1%.
- B) 2017 pole x 2017->2026 Q ratio over 9 unchanged dry circuits (cache/_era_ratio_2017_2026.py):
  ratio 1.0145 sd 0.0089 -> Sepang 2026 pole est 91.38 +/- 0.80 s.
- A at inset 0 = 91.31 (agrees with B within 0.07 s, no fitting).
- SHIPPED inset 0.5 (inset 0 cut the T9 hairpin apex by 0.67 m, 2 pts): 91.838 s jerk-limited,
  top 327, min 83; gate 6/6 vs 2017 pole; on-track 0/2736 (worst 0.17 m);
  a(v) gain peaks 140-220 (~40) and collapses >300 (7) like real 2026 Q.
- Road width 16 m assumed (real Sepang 16 m corners, wider straights) - biggest geometry unknown.
- S/F provisional = svg_to_outline origin on main straight; re-pin after FP1.

After FP1 (Fri 2026-10-02): OpenF1 lists it as country "Bahrain", circuit "Kuala Lumpur".
  python fetch_openf1_lap.py --year 2026 --country Bahrain --circuit "Kuala Lumpur" --session "Practice 1" --out F1_Pipeline_Assets/exports/reference_2026_sepang_fp1.csv
  then _overlay_speed.py (corr >= 0.95), expect FP1 ~ +3% over eventual Q. VERIFY only; add elevation
  (cache/_fetch_elevation.py) + re-pin S/F from that data, re-render with --elevation-json.

T1 line fix (2026-09-30, user spotted the car running wide at T1): optimiser line never reached the
T1 inside kerb (closest 3.8 m centre). cache/_sepang_t1_apex.py pulls the late apex to 1.2 m with a
60 m raised-cosine taper (sweep: H30 92.006, H45 91.913, H60 91.772, asym 90/55 91.808); simulated
via the new opt-in `sim_2026_lap.py --raceline-in` (default path re-proved bit-identical on
Zandvoort). SHIPPED 1:31.772: T1 apex 121->122, T2 min 88->91 km/h, gate 6/6, 0 off-track.
Engine-wide fix (optimiser is min-curvature, not min-time, at hairpin combos) deferred: needs backtest.
