"""Rate-of-change AS A FUNCTION OF SPEED — the analytical view.
Bins throttle-on GAIN rate and braking DROP rate by speed so we can see exactly
where the sim's a(v) curve diverges from real, instead of arguing about an
aggregate median."""
import csv, sys
import numpy as np

WIN_S = 0.5
BINS = [(60,100),(100,140),(140,180),(180,220),(220,260),(260,300),(300,340)]

def load(path):
    t,v,th,br=[],[],[],[]
    with open(path,encoding="utf-8") as f:
        for r in csv.DictReader(f):
            t.append(float(r["time_s"])); v.append(float(r["speed"]))
            th.append(float(r.get("throttle",0) or 0)); br.append(float(r.get("brake",0) or 0))
    return map(np.array,(t,v,th,br))

def rate(t,v):
    out=np.full(len(v),np.nan)
    for i in range(len(v)):
        j=i
        while j<len(v)-1 and (t[j]-t[i])<WIN_S: j+=1
        if t[j]>t[i]: out[i]=(v[j]-v[i])/(t[j]-t[i])
    return out

def analyze(path,label):
    t,v,th,br=load(path); r=rate(t,v)
    print(f"\n=== {label} ===")
    print("  speed bin    GAIN med (n)     DROP med (n)")
    for lo,hi in BINS:
        inb=(v>=lo)&(v<hi)
        g=r[inb&(th>80)&(br<5)&(r>2)]
        d=r[inb&(br>15)&(r<-2)]
        gs=f"{np.median(g):5.1f} ({len(g):3d})" if len(g) else "   -  (  0)"
        ds=f"{np.median(np.abs(d)):5.1f} ({len(d):3d})" if len(d) else "   -  (  0)"
        print(f"  {lo:3d}-{hi:3d}    {gs}     {ds}")

if __name__=="__main__":
    for a in sys.argv[1:]:
        p,l=a.split("::"); analyze(p,l)
