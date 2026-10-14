import sys, json, numpy as np
sys.argv = ["x", "0"]
src = open("reshape_track.py").read().split("o = json.load(open(os.path.join(TR")[0]
exec(src)
o = json.load(open(os.path.join(TR, "portimao_gt3_outline.json")))
A0, B0 = np.array(o["outer"], float), np.array(o["inner"], float)
C, Lc = resample_closed((A0 + B0) / 2, N); ds = Lc / N
rl = np.array(json.load(open("_rs_rl_0.json"))["raceline"])[:, :2]
kr, kl, rmse, lap, corr = evaluate(rl, C)
th = np.unwrap(np.arctan2(*np.diff(np.vstack([C, C[:1]]), axis=0)[:, ::-1].T))
dth = np.diff(np.r_[th, th[0]]); dth = (dth + np.pi) % (2*np.pi) - np.pi; kc = dth / ds
print("corr kc vs signed_k(C)", np.corrcoef(kc, signed_k(C, 6))[0,1], "corr kc vs kl", np.corrcoef(kc, kl)[0,1], "kr vs kl", np.corrcoef(kr, kl)[0,1])
for lag in range(-30, 31, 5): print("lag", lag, "corr kr(shift) vs kl", round(np.corrcoef(np.roll(kr, lag), kl)[0,1], 3))
print("sum turning", kc.sum()*ds, "kr total", kr.sum()*ds, "kl total", kl.sum()*ds)
