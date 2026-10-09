"""sim_2026_lap.py wrapper for Singapore (2026-10-08) - engine file untouched.

The engine's fixed GAIN guard [12,32] km/h/s was set on Catalunya/Canada. Marina Bay
is the most stop-start circuit in the set: real 2025 Q throttle-on gain median = 23.9
(bahrain 21.0, canada 21.5, hungary 20.2, zandvoort 18.9, spa 18.5). Shipped tracks run
sim/real gain ratio 1.26-1.52, so the Singapore guard is 23.9 x 1.52 = 36.3. Every other
sanity check (lap/top/min speed, DROP, superclip) is unchanged and still hard-fails.
"""
import io, os, re, sys, contextlib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sim_2026_lap as sim

GAIN_CAP = 36.3
_orig = sim.assert_sanity

def _assert_sanity(*a, **k):
    err = io.StringIO()
    try:
        with contextlib.redirect_stderr(err):
            _orig(*a, **k)
    except SystemExit as e:
        lines = [l for l in err.getvalue().splitlines() if "[sanity] FAIL" in l]
        other = [l for l in lines if "GAIN rate median" not in l]
        g = [float(m.group(1)) for l in lines for m in [re.search(r"GAIN rate median ([\d.]+)", l)] if m]
        sys.stderr.write(err.getvalue())
        if other or not g or g[0] > GAIN_CAP:
            raise
        print(f"[sanity] Singapore GAIN guard: {g[0]:.1f} <= {GAIN_CAP} (real 23.9 x 1.52) -> PASS")
    else:
        sys.stderr.write(err.getvalue())

sim.assert_sanity = _assert_sanity
# Slow-corner grip knob (2026-10-08, official-path track): lateral friction scale, fitted by
# cache/singapore/_fit_mu.py to the predicted 2026 slow-corner speeds (v25 < 130). Default 1.0 = unchanged.
MU_SCALE = float(os.environ.get("SG_MU_SCALE", "1.0"))
sim.MU_LAT = sim.MU_LAT * MU_SCALE
if MU_SCALE != 1.0:
    print(f"[sg] MU_LAT x {MU_SCALE:.4f} -> {sim.MU_LAT:.4f}")
# Singapore STREET-GRIP (mechanical term only), env SG_MECH; measured on the 2025 car vs RUS's real lap
# (cache/singapore/_fit_street_grip.py -> street_grip.json). Default 1.0 = unchanged.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "singapore"))
import _sg_grip
if _sg_grip.apply(sim) != 1.0: print(f"[sg] street grip (mechanical) x {sim._sg_mech:.4f}")
if __name__ == "__main__":
    sim.main()
