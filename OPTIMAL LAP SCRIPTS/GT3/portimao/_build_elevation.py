"""3D flyover data for the Portimao GT3 video: stations = shipped v2 raceline (driving order, idx 0 = real S/F),
z = 2021 FastF1 pole-lap height by lap fraction (the SAME z the GT3 sim uses), relative to the lap low point."""
import json, os, sys, numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); sys.path.insert(0, HERE)
import sim_gt3_car as G
rl = np.array(json.load(open(os.path.join(HERE, "assets", "portimao_gt3real_raceline.json")))["raceline"])[:, :2]
arc, _, L = G.S._arc_kappa_closed(rl)
z = G.elevation_for(arc, L); z0 = float(z.min()); h = z - z0
out = dict(track="portimao", source="FastF1 2021 Portuguese GP Q, HAM pole lap Z (m), smoothed; mapped by lap fraction",
           altitude_reference="metres above the lap low point (FastF1 Z datum unverified)",
           removed_raw_datum_m=z0, alt_min_m=0.0, alt_max_m=round(float(h.max()), 2), span_m=round(float(h.max()), 2),
           dist_frac=(arc / L).round(5).tolist(), elev_m=h.round(3).tolist(),
           stations=np.c_[rl, h].round(3).tolist(), sf_source="v2 raceline idx 0 = real S/F")
json.dump(out, open(os.path.join(HERE, "assets", "portimao_gt3real_elevation.json"), "w"))
print(f"[elev] {len(h)} stations, span {h.max():.1f} m, high at {arc[h.argmax()]/L*100:.0f}% lap, low at {arc[h.argmin()]/L*100:.0f}%")
