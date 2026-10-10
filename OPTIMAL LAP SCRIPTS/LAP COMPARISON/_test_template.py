"""Headless test of OPTIMAL_X_QUALI.ipynb: runs its cell (UI built, not shown), then bakes directly."""
import json, sys, subprocess
code = "".join(json.load(open("OPTIMAL_X_QUALI.ipynb", encoding="utf-8"))["cells"][0]["source"])
code = code.replace("display(ui)", "pass")
g = {"__name__": "nbtest"}
exec(compile(code, "OPTIMAL_X_QUALI", "exec"), g)
real_render = g["LCO"].render
g["LCO"].render = lambda *a, **k: real_render(*a, **dict(k, max_seconds=float(sys.argv[2])))
g["subprocess"].run = lambda *a, **k: None
drivers = sys.argv[1].split(",")
cfgs = [{"driver": d, "year": 2026, "session": "SQ"} for d in drivers]
g["F1VideoBaker"](track="Singapore Grand Prix", configs=cfgs, is_same_race=True, zoom_factor=1.0, trail_frames=60).bake()
