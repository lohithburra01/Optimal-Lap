"""Build a self-contained interactive 3D elevation viewer for a track.

Reads the elevation JSON (cache/_fetch_elevation.py), the raceline-lifted 3D
stations inside it, and the track's sim lap CSV, embeds everything into ONE
HTML file (three.js from CDN) with:
  - the track as a 3D ribbon, vertex-coloured by altitude, with a translucent
    curtain dropping to the base plane (reads the hills instantly)
  - the optimal-lap car animating on it (speed-true), glowing trail
  - HUD: speed / altitude (true m ASL) / gradient % / lap clock
  - orbit + follow-cam, play/pause/scrub, playback speed, vertical
    exaggeration slider

  python cache/_build_3d_viewer.py --track spa [--name "Belgian Grand Prix"]
        [--out spa_elevation_3d.html]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _track_registry import REPO_ROOT, TRACKS  # noqa: E402

SIM_CSV = {
    "spa": "F1_Pipeline_Assets/exports/spa_2026_synthetic.csv",
}

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ — 3D elevation</title>
<style>
  html,body{margin:0;height:100%;background:#0b0b0d;color:#ddd;
    font-family:'Segoe UI',system-ui,sans-serif;overflow:hidden}
  #c{position:fixed;inset:0}
  #hud{position:fixed;left:16px;top:14px;pointer-events:none}
  #hud h1{font-size:15px;margin:0 0 2px;font-weight:600;letter-spacing:.12em}
  #hud .sub{font-size:11px;color:#888;letter-spacing:.08em}
  #stats{position:fixed;right:16px;top:14px;text-align:right;pointer-events:none}
  .big{font-size:34px;font-weight:700;color:#fff;line-height:1.05}
  .unit{font-size:11px;color:#999;letter-spacing:.1em}
  .row{margin-top:8px}
  .val{font-size:19px;font-weight:600;color:#f2f2f2}
  #grade.up{color:#ff9d2e}#grade.down{color:#59b7ff}
  #bar{position:fixed;left:0;right:0;bottom:0;padding:10px 16px 14px;
    background:linear-gradient(transparent,rgba(0,0,0,.75));display:flex;
    gap:12px;align-items:center;flex-wrap:wrap}
  button,select{background:#1c1c22;color:#eee;border:1px solid #333;
    border-radius:6px;padding:6px 12px;font-size:13px;cursor:pointer}
  button:hover{background:#2a2a33}
  input[type=range]{accent-color:#e8890c}
  #scrub{flex:1;min-width:160px}
  label{font-size:11px;color:#999;display:flex;gap:6px;align-items:center}
  #legend{position:fixed;left:16px;bottom:64px;font-size:10px;color:#aaa}
  #legend .sw{display:inline-block;width:34px;height:8px;border-radius:2px;
    vertical-align:middle;margin-right:6px}
</style>
</head>
<body>
<canvas id="c"></canvas>
<div id="hud"><h1>__NAME__ · 3D ELEVATION</h1>
  <div class="sub">pre-FP1 optimal lap __LAPTIME__ · real altitude from F1 position telemetry (span __SPAN__ m)</div></div>
<div id="stats">
  <div><span class="big" id="spd">0</span> <span class="unit">KM/H</span></div>
  <div class="row"><span class="val" id="alt">–</span> <span class="unit">M ASL</span></div>
  <div class="row"><span class="val" id="grade">–</span> <span class="unit">GRADE</span></div>
  <div class="row"><span class="val" id="clock">0.0</span> <span class="unit">S</span></div>
</div>
<div id="legend"><span class="sw" style="background:linear-gradient(90deg,#3b4bd8,#25c1a1,#ffd23e,#ff7a1a)"></span>__ALTMIN__ → __ALTMAX__ m ASL</div>
<div id="bar">
  <button id="play">⏸ pause</button>
  <input id="scrub" type="range" min="0" max="1000" value="0">
  <label>speed <select id="pspd"><option>0.5</option><option selected>1</option><option>2</option><option>4</option></select>×</label>
  <label>elevation ×<span id="exv">2.0</span> <input id="ex" type="range" min="10" max="40" value="20"></label>
  <label><input id="follow" type="checkbox"> follow car</label>
</div>
<script type="importmap">{"imports":{
  "three":"https://unpkg.com/three@0.160.0/build/three.module.js",
  "three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/"}}</script>
<script type="module">
import * as THREE from 'three';
import {OrbitControls} from 'three/addons/controls/OrbitControls.js';

const STA = __STATIONS__;          // [x,y,z_true] metres, sim frame, S/F = idx 0
const EF  = __EFRAC__;             // elevation grid: lap fraction
const EM  = __ELEV__;              // elevation grid: altitude m ASL
const LAP = __LAPROWS__;           // [t_s, dist_frac, speed_kmh] @10 Hz
const TOTAL_M = __TOTAL__;
const ALT0 = Math.min(...EM);
const HALF_W = 7.0;

const N = STA.length;
const cx = STA.reduce((s,p)=>s+p[0],0)/N, cy = STA.reduce((s,p)=>s+p[1],0)/N;
let EX = 2.0;

// ---------- geometry ----------
const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0x0b0b0d, 2500, 6000);
const renderer = new THREE.WebGLRenderer({canvas:document.getElementById('c'),antialias:true});
renderer.setPixelRatio(Math.min(devicePixelRatio,2));
const cam = new THREE.PerspectiveCamera(55, innerWidth/innerHeight, 1, 20000);
const controls = new OrbitControls(cam, renderer.domElement);
controls.enableDamping = true;

const ramp = t => new THREE.Color().setHSL(0.65-0.55*t, 0.75, 0.30+0.28*t);
function elevOf(p){ return p[2]; }
function yOf(p){ return (p[2]-ALT0)*EX + 4; }
function v3(p){ return new THREE.Vector3(p[0]-cx, yOf(p), -(p[1]-cy)); }

function normals2d(){
  const out=[];
  for(let i=0;i<N;i++){
    const a=STA[(i-1+N)%N], b=STA[(i+1)%N];
    let dx=b[0]-a[0], dy=b[1]-a[1];
    const l=Math.hypot(dx,dy)||1;
    out.push([-dy/l, dx/l]);
  }
  return out;
}
const NRM = normals2d();
const eMin=Math.min(...EM), eSpan=Math.max(...EM)-eMin;

let ribbon, curtain, edgeL, edgeR, sfGate;
function buildTrack(){
  [ribbon,curtain,edgeL,edgeR,sfGate].forEach(o=>{if(o){scene.remove(o);o.geometry?.dispose();}});
  const pos=[],col=[],idx=[], cpos=[],cidx=[], el=[],er=[];
  for(let i=0;i<N;i++){
    const p=STA[i], n=NRM[i];
    const L=[p[0]+n[0]*HALF_W, p[1]+n[1]*HALF_W, p[2]];
    const R=[p[0]-n[0]*HALF_W, p[1]-n[1]*HALF_W, p[2]];
    const vl=v3(L), vr=v3(R);
    pos.push(vl.x,vl.y,vl.z, vr.x,vr.y,vr.z);
    const c=ramp((elevOf(p)-eMin)/eSpan);
    col.push(c.r,c.g,c.b, c.r,c.g,c.b);
    el.push(vl.x,vl.y+0.4,vl.z); er.push(vr.x,vr.y+0.4,vr.z);
    const j=i*2, k=((i+1)%N)*2;
    idx.push(j,j+1,k, j+1,k+1,k);
    cpos.push(vl.x,vl.y,vl.z, vl.x,0,vl.z);
    const cj=i*2, ck=((i+1)%N)*2;
    cidx.push(cj,cj+1,ck, cj+1,ck+1,ck);
  }
  const g=new THREE.BufferGeometry();
  g.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));
  g.setAttribute('color',new THREE.Float32BufferAttribute(col,3));
  g.setIndex(idx);
  ribbon=new THREE.Mesh(g,new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.DoubleSide}));
  scene.add(ribbon);
  const cg=new THREE.BufferGeometry();
  cg.setAttribute('position',new THREE.Float32BufferAttribute(cpos,3));
  cg.setIndex(cidx);
  curtain=new THREE.Mesh(cg,new THREE.MeshBasicMaterial({color:0x8a5a18,transparent:true,
    opacity:0.14,side:THREE.DoubleSide,depthWrite:false}));
  scene.add(curtain);
  const mkEdge=a=>{const eg=new THREE.BufferGeometry();
    eg.setAttribute('position',new THREE.Float32BufferAttribute([...a, a[0],a[1],a[2]],3));
    return new THREE.Line(eg,new THREE.LineBasicMaterial({color:0xffffff,transparent:true,opacity:0.35}));};
  edgeL=mkEdge(el); edgeR=mkEdge(er); scene.add(edgeL,edgeR);
  const p0=v3(STA[0]), p1=v3([STA[0][0]+NRM[0][0]*HALF_W*1.4, STA[0][1]+NRM[0][1]*HALF_W*1.4, STA[0][2]]),
        p2=v3([STA[0][0]-NRM[0][0]*HALF_W*1.4, STA[0][1]-NRM[0][1]*HALF_W*1.4, STA[0][2]]);
  const sg=new THREE.BufferGeometry().setFromPoints([p1,p2]);
  sfGate=new THREE.Line(sg,new THREE.LineBasicMaterial({color:0xffffff}));
  sfGate.position.y+=1.5; scene.add(sfGate);
}
buildTrack();
scene.add(new THREE.GridHelper(5200, 40, 0x232329, 0x17171b));

// car + trail
const car=new THREE.Mesh(new THREE.SphereGeometry(11,20,20),
  new THREE.MeshBasicMaterial({color:0xffa020}));
const halo=new THREE.Mesh(new THREE.SphereGeometry(16,20,20),
  new THREE.MeshBasicMaterial({color:0xff8800,transparent:true,opacity:0.25}));
scene.add(car,halo);
const TRAIL_N=140;
const tg=new THREE.BufferGeometry();
tg.setAttribute('position',new THREE.Float32BufferAttribute(new Float32Array(TRAIL_N*3),3));
const trail=new THREE.Line(tg,new THREE.LineBasicMaterial({color:0xe8890c,transparent:true,opacity:0.8}));
scene.add(trail);
const tpts=[];

// ---------- animation state ----------
const T_END=LAP[LAP.length-1][0];
let t=0, playing=true, pspd=1;
function lapAt(tq){
  tq=Math.max(0,Math.min(tq,T_END));
  let lo=0,hi=LAP.length-1;
  while(hi-lo>1){const m=(lo+hi)>>1;(LAP[m][0]<=tq?lo=m:hi=m);}
  const a=LAP[lo],b=LAP[hi],u=(tq-a[0])/Math.max(b[0]-a[0],1e-6);
  return {frac:a[1]+(b[1]-a[1])*u, v:a[2]+(b[2]-a[2])*u};
}
function staAt(frac){
  const f=((frac%1)+1)%1, x=f*N, i=Math.floor(x)%N, j=(i+1)%N, u=x-i;
  const a=STA[i],b=STA[j];
  return [a[0]+(b[0]-a[0])*u, a[1]+(b[1]-a[1])*u, a[2]+(b[2]-a[2])*u];
}
function elevAt(frac){
  const f=((frac%1)+1)%1, x=f*EF.length, i=Math.floor(x)%EF.length,
        j=(i+1)%EF.length, u=x-i;
  return EM[i]+(EM[j]-EM[i])*u;
}
function gradeAt(frac){
  const d=15/TOTAL_M;
  return (elevAt(frac+d)-elevAt(frac-d))/(2*15)*100;
}

// camera start: fit + gentle intro orbit
const bb=new THREE.Box3().setFromObject(ribbon);
const ctr=bb.getCenter(new THREE.Vector3()), rad=bb.getSize(new THREE.Vector3()).length()*0.42;
cam.position.set(ctr.x+rad*0.9, rad*0.85, ctr.z+rad*0.9);
controls.target.copy(ctr);
let userMoved=false;
controls.addEventListener('start',()=>userMoved=true);

// ---------- UI ----------
const $=id=>document.getElementById(id);
$('play').onclick=()=>{playing=!playing;$('play').textContent=playing?'⏸ pause':'▶ play';};
$('pspd').onchange=e=>pspd=parseFloat(e.target.value);
$('scrub').oninput=e=>{t=e.target.value/1000*T_END;};
$('ex').oninput=e=>{EX=e.target.value/10;$('exv').textContent=EX.toFixed(1);buildTrack();};
addEventListener('resize',()=>{cam.aspect=innerWidth/innerHeight;
  cam.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);});
renderer.setSize(innerWidth,innerHeight);

let prev=performance.now();
function frame(now){
  const dt=(now-prev)/1000; prev=now;
  if(playing){t+=dt*pspd; if(t>T_END)t=0; $('scrub').value=t/T_END*1000;}
  const s=lapAt(t), p=staAt(s.frac), pv=v3(p);
  car.position.copy(pv); halo.position.copy(pv);
  tpts.push(pv.clone()); if(tpts.length>TRAIL_N)tpts.shift();
  const ta=trail.geometry.attributes.position;
  for(let i=0;i<TRAIL_N;i++){const q=tpts[Math.min(i,tpts.length-1)]||pv;
    ta.setXYZ(i,q.x,q.y+0.6,q.z);}
  ta.needsUpdate=true;
  $('spd').textContent=Math.round(s.v);
  $('alt').textContent=elevAt(s.frac).toFixed(0);
  const g=gradeAt(s.frac), ge=$('grade');
  ge.textContent=(g>0?'+':'')+g.toFixed(1)+'%';
  ge.className=g>0.5?'up':(g<-0.5?'down':'');
  $('clock').textContent=t.toFixed(1);
  if($('follow').checked){
    const ahead=staAt(s.frac+40/TOTAL_M), av=v3(ahead);
    const dir=av.clone().sub(pv).normalize();
    const cpos=pv.clone().sub(dir.multiplyScalar(90)).add(new THREE.Vector3(0,38,0));
    cam.position.lerp(cpos,0.06); controls.target.lerp(pv,0.12);
  } else if(!userMoved){
    const a=now*0.00005;
    cam.position.set(ctr.x+Math.cos(a)*rad*0.95, rad*0.8, ctr.z+Math.sin(a)*rad*0.95);
    controls.target.copy(ctr);
  }
  controls.update();
  renderer.render(scene,cam);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);
</script>
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True, choices=sorted(TRACKS))
    ap.add_argument("--name", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    spec = TRACKS[args.track]

    elev_path = spec["outline"].replace("_outline.json", "_elevation.json")
    with open(elev_path, encoding="utf-8") as f:
        elev = json.load(f)
    if not elev.get("stations"):
        print("[3d] elevation json has no stations — run _fetch_elevation.py "
              "after the raceline exists", file=sys.stderr)
        return 2

    sim_csv = os.path.join(REPO_ROOT, SIM_CSV.get(args.track, ""))
    rows = []
    with open(sim_csv, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append((float(r["time_s"]), float(r["distance"]),
                         float(r["speed"])))
    d_tot = rows[-1][1]
    lap = [[round(t, 3), round(d / d_tot, 5), round(v, 1)]
           for i, (t, d, v) in enumerate(rows) if i % 3 == 0]
    lap_time = rows[-1][0]
    mm, ss = divmod(lap_time, 60.0)

    html = (TEMPLATE
            .replace("__NAME__", args.name or args.track.title())
            .replace("__LAPTIME__", f"{int(mm)}:{ss:06.3f}")
            .replace("__SPAN__", str(elev["span_m"]))
            .replace("__ALTMIN__", str(elev["alt_min_m"]))
            .replace("__ALTMAX__", str(elev["alt_max_m"]))
            .replace("__STATIONS__", json.dumps(elev["stations"],
                                                separators=(",", ":")))
            .replace("__EFRAC__", json.dumps(elev["dist_frac"],
                                             separators=(",", ":")))
            .replace("__ELEV__", json.dumps(elev["elev_m"],
                                            separators=(",", ":")))
            .replace("__LAPROWS__", json.dumps(lap, separators=(",", ":")))
            .replace("__TOTAL__", str(spec["length_m"])))
    out = args.out or os.path.join(REPO_ROOT, f"{args.track}_elevation_3d.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[3d] wrote {out} ({os.path.getsize(out)//1024} KB, "
          f"{len(elev['stations'])} stations, {len(lap)} anim samples, "
          f"lap {lap_time:.3f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
