"""Singapore STREET-GRIP factor (2026-10-08): scales only the MECHANICAL (gravity) term of the lateral grip
budget, mu*(k*g + DF/m), in sim_2026_lap's flat-road a_lat_max_banked and v_grip_static (Singapore has no banking;
banked calls fall through to the originals). A TRACK property: measured on the 2025 car against RUS's real pole
lap (cache/singapore/_fit_street_grip.py) and applied unchanged to the 2026 car. Engine file untouched."""
import math, os
def apply(S, k=None):
    k = float(os.environ.get("SG_MECH", "1.0")) if k is None else k
    if k == 1.0 or getattr(S, "_sg_mech", None) == k: return k
    oa, ov = getattr(S, "_sg_orig", (S.a_lat_max_banked, S.v_grip_static)); S._sg_orig = (oa, ov)
    def a_lat_max_banked(v, mode, bank_rad=0.0):
        if bank_rad != 0.0: return oa(v, mode, bank_rad)
        return S.MU_LAT * (k * S.G + S.downforce(v, mode) / S.MASS_KG)
    def v_grip_static(kappa, bank_rad=0.0):
        if bank_rad != 0.0: return ov(kappa, bank_rad)
        kk = abs(kappa)
        if kk < 1e-6: return 300.0
        denom = kk - S.MU_LAT * 0.5 * S.RHO * S.CL_CORNER_M2 / S.MASS_KG
        return 300.0 if denom <= 0.0 else math.sqrt(S.MU_LAT * k * S.G / denom)
    S.a_lat_max_banked, S.v_grip_static, S._sg_mech = a_lat_max_banked, v_grip_static, k
    return k
