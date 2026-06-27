"""2026 realism gate — pass/fail checks that encode the recurring failures:

  1. A 2026 lap must be SLOWER than the 2025 pole (less downforce + deploy cliff).
  2. GAIN median must sit in the real-2026 band (not pinned near the accel ceiling).
  3. GAIN peak must not exceed the real-2026 punch.
  4. BRAKING DROP median must be in band (not uniformly over-braking).
  5. BRAKING DROP peak must show a real sharp initial bite.
  6. SUPERCLIP must be sharp/rare, not a continuous low trickle across the straights.

Real-2026 bands measured from reference_2026_spain_q.csv (Catalunya FP1) and
reference_2026_canada_q.csv via cache/_rates.py (0.5 s windows).

Usage:
  python cache/_gate_2026.py <sim_csv> <t_2025_pole_s>
Exit code 0 = all gates pass, 1 = one or more fail.
"""
import csv, sys
import numpy as np

WIN_S = 0.5

# --- real-2026 bands (km/h/s) -------------------------------------------------
GAIN_MED_LO, GAIN_MED_HI = 14.0, 28.0     # real medians 16.6 / 24.2
GAIN_PEAK_MAX            = 64.0           # real peaks 55 / 61
DROP_MED_LO, DROP_MED_HI = 32.0, 52.0     # real medians 36.5 / 44.2
DROP_PEAK_MIN            = 85.0           # real peaks 104 / 154 — sharp bite
# 2026 is slower than 2025 by ~+1.5-2.5 s; allow a slightly wider accept band
LAP_DELTA_LO, LAP_DELTA_HI = 1.0, 3.5
# superclip must be a sharp event, not a trickle: bleeding frames should be a
# small fraction of near-top-speed throttle frames, with a real peak bleed.
SUPERCLIP_FRAC_MAX = 0.45
SUPERCLIP_PEAK_MIN = 35.0


def load(path):
    t, v, th, br = [], [], [], []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t.append(float(r["time_s"])); v.append(float(r["speed"]))
            th.append(float(r.get("throttle", 0) or 0)); br.append(float(r.get("brake", 0) or 0))
    return np.array(t), np.array(v), np.array(th), np.array(br)


def rate_kmh_s(t, v):
    out = np.full(len(v), np.nan)
    for i in range(len(v)):
        j = i
        while j < len(v) - 1 and (t[j] - t[i]) < WIN_S:
            j += 1
        if t[j] > t[i]:
            out[i] = (v[j] - v[i]) / (t[j] - t[i])
    return out


def main(sim_csv, t_2025):
    t, v, th, br = load(sim_csv)
    r = rate_kmh_s(t, v)
    top = v.max()
    t_lap = t[-1] - t[0]

    gain = np.abs(r[(th > 80) & (br < 5) & (v < 0.88 * top) & (r > 2)])
    drop = np.abs(r[(br > 15) & (r < -2)])
    near_top = (th > 90) & (br < 5) & (v > 0.85 * top)
    clip = np.abs(r[near_top & (r < -1)])
    sc_frac = (len(clip) / max(int(near_top.sum()), 1))

    checks = []

    def gate(name, ok, detail):
        checks.append(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    print(f"\n=== 2026 GATE: {sim_csv} ===   lap={t_lap:.2f}s  top={top:.0f} km/h")
    delta = t_lap - t_2025
    gate("lap slower than 2025 pole",
         LAP_DELTA_LO <= delta <= LAP_DELTA_HI,
         f"{t_lap:.2f}s = {delta:+.2f}s vs 2025 ({t_2025:.2f}s); want +{LAP_DELTA_LO}..+{LAP_DELTA_HI}s")
    gm = np.median(gain) if len(gain) else 0
    gate("GAIN median in real band", GAIN_MED_LO <= gm <= GAIN_MED_HI,
         f"{gm:.1f} km/h/s; want {GAIN_MED_LO}-{GAIN_MED_HI}")
    gp = np.max(gain) if len(gain) else 0
    gate("GAIN peak not excessive", gp <= GAIN_PEAK_MAX,
         f"{gp:.1f} km/h/s; want <= {GAIN_PEAK_MAX}")
    dm = np.median(drop) if len(drop) else 0
    gate("DROP median in real band", DROP_MED_LO <= dm <= DROP_MED_HI,
         f"{dm:.1f} km/h/s; want {DROP_MED_LO}-{DROP_MED_HI}")
    dp = np.max(drop) if len(drop) else 0
    gate("DROP peak shows sharp bite", dp >= DROP_PEAK_MIN,
         f"{dp:.1f} km/h/s; want >= {DROP_PEAK_MIN}")
    cp = np.max(clip) if len(clip) else 0
    gate("SUPERCLIP sharp not trickle", sc_frac <= SUPERCLIP_FRAC_MAX and cp >= SUPERCLIP_PEAK_MIN,
         f"frac={sc_frac:.2f} (want <= {SUPERCLIP_FRAC_MAX}), peak={cp:.1f} (want >= {SUPERCLIP_PEAK_MIN})")

    ok = all(checks)
    print(f"  => {'ALL GATES PASS' if ok else 'GATES FAILED'} ({sum(checks)}/{len(checks)})")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], float(sys.argv[2])))
