import sys, json, io, contextlib, numpy as np
import trace_fit as T, sim_gt3_car as G
rl = np.array(json.load(open(sys.argv[1]))["raceline"]); car = dict(G.GT3_CAR); car.update(json.load(open(sys.argv[2])))
with contextlib.redirect_stdout(io.StringIO()):
    rmse, r, pairs, svr, sh = T.compare(rl, car)
E = np.load("_env.npz"); z = r["z"]; sd = (r["arc"] - sh) % r["L"]
zr = np.interp(T.rd * r["L"] / T.REAL_LEN, np.sort(sd), z[np.argsort(sd)])
print(f"lap {r['lap']:.2f}  rmse {rmse:.1f}")
for x in range(0, 4600, 100):
    k = np.argmin(np.abs(T.rd - x)); j = np.argmin(np.abs(E["d"] - x))
    print(f"{x:5d} real {T.rv[k]:4.0f} sim {svr[k]:4.0f} d {svr[k]-T.rv[k]:+4.0f} | z_sim {zr[k]:5.1f} z_env {E['z'][j]:5.1f} glat {E['gl'][j]:.2f}")
