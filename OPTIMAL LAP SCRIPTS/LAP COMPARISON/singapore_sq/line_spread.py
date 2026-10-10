"""Lateral spread between two racing lines: distance from each point of B to the polyline A."""
import json, sys, numpy as np
A = np.array(json.load(open(sys.argv[1]))["raceline"]); B = np.array(json.load(open(sys.argv[2]))["raceline"])
def L(P): return np.linalg.norm(np.roll(P, -1, 0) - P, axis=1).sum()
P0, P1 = A, np.roll(A, -1, 0); d = P1 - P0; dd = (d * d).sum(1)
dist = []
for p in B:
    t = np.clip(((p - P0) * d).sum(1) / dd, 0, 1); dist.append(np.linalg.norm(P0 + t[:, None] * d - p, axis=1).min())
dist = np.array(dist); W = 10.0   # Singapore v4 track = fitted 10 m width
print(f"lateral gap mean {dist.mean():.2f} m  p95 {np.percentile(dist,95):.2f} m  max {dist.max():.2f} m"
      f" | mean = {100*dist.mean()/W:.1f}% of the 10 m width | length A {L(A):.1f} B {L(B):.1f} ({100*(L(B)-L(A))/L(A):+.2f}%)")
