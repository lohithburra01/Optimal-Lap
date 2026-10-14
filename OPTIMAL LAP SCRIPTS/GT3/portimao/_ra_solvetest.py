import sys, os, json, time, numpy as np
sys.argv = ["x", "0", "0.6", "40", "t"]
src = open("reshape_anchored.py").read().split("d = np.zeros(N)")[0]; exec(src)
X = (np.array(json.load(open("_raa_outline_3.json"))["outer"]) + np.array(json.load(open("_raa_outline_3.json"))["inner"])) / 2
d0 = np.sum((X - C0) * n0, axis=1)
rl = np.array(json.load(open("_raa_rl_3.json"))["raceline"])[:, :2]
import io, contextlib
kr, kl, rmse, lap, corr = evaluate(rl, X)
kx = signed_k(X, ST); sg = np.sign(np.corrcoef(kx, kl)[0, 1])
e = uniform_filter1d(kr - kl, 9, mode="wrap") * sg; kt = kx + 0.6 * e
print("target change rms /km", np.sqrt(np.mean((kt-kx)**2))*1e3)
for nfev in (60, 300):
    t0 = time.time()
    res = lambda dd: np.r_[(signed_k(C0 + n0 * dd[:, None], ST) - kt) / 2e-3, dd / ANCHOR]
    r = least_squares(res, d0, jac_sparsity=J, bounds=(-60, 60), max_nfev=nfev, x_scale=5.0)
    k2 = signed_k(C0 + n0 * r.x[:, None], ST)
    print(nfev, "achieved rms err to target /km", np.sqrt(np.mean((k2-kt)**2))*1e3, "status", r.status, "nfev", r.nfev, f"{time.time()-t0:.0f}s")
# where in the lap is the sweeper? print kt vs kx around biggest e
i = np.argsort(-np.abs(e))[:5]; print("largest e at stations", i, (e[i]*1e3).round(2))
