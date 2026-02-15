import fastf1
import fastf1.plotting
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import json
import warnings
from scipy.interpolate import interp1d, PchipInterpolator
from scipy.signal import correlate, medfilt, savgol_filter, find_peaks

# Suppress warnings
warnings.simplefilter(action='ignore')

# 1. CONFIGURATION
YEAR = 2025
GP = 'CHINA'
SESSION = 'Q'
DRIVERS = ['VER', 'PIA', 'NOR'] 

# TUNING (The Gold Standard)
FILTER_WINDOW_M = 50   
ANCHOR_STEP_M = 100    

print(f"⏳ Loading {YEAR} {GP}...")
try:
    fastf1.plotting.setup_mpl(misc_mpl_mods=False)
    fastf1.Cache.enable_cache('cache')
except:
    pass

session = fastf1.get_session(YEAR, GP, SESSION)
session.load(telemetry=True, laps=True, weather=False, messages=False)

# 2. DETECT REFERENCE
ref_driver = session.laps.pick_drivers(DRIVERS).pick_fastest()['Driver']
print(f"🔹 Reference Driver: {ref_driver}")

# ══════════════════════════════════════════════════════════════════
# CONSOLIDATED DATA INTEGRITY FRAMEWORK
#
# Two independent metrics:
#
# 1. PIPELINE FIDELITY — "How much did we change the raw data?"
#    Measures total intervention across all 4 steps as % of baseline.
#    Fidelity = 100% - sum(step interventions)
#
# 2. SHAPE INTEGRITY — "Can we trust the delta graph's shape?"
#    S(x) = 100 × exp(−max(0, x − τ)^p / λ)
#    τ=5m, p=1.5, λ=700
#    Validated against 457 qualifying comparisons (2023–2024)
# ══════════════════════════════════════════════════════════════════

INTEGRITY_TAU = 5
INTEGRITY_P = 1.5
INTEGRITY_LAMBDA = 700

def calculate_integrity_score(length_offset_m, shift_offset_m):
    total_offset = length_offset_m + shift_offset_m
    effective = max(0, total_offset - INTEGRITY_TAU)
    score = 100.0 * np.exp(-(effective ** INTEGRITY_P) / INTEGRITY_LAMBDA)
    
    if score >= 95:    grade, color = "Excellent", "#16813D"
    elif score >= 85:  grade, color = "Good", "#0f3460"
    elif score >= 70:  grade, color = "Acceptable", "#CC8800"
    elif score >= 50:  grade, color = "Warning", "#CC0000"
    else:              grade, color = "Critical", "#990000"
    
    return {
        'score': round(score, 1), 'grade': grade, 'grade_color': color,
        'total_offset': round(total_offset, 2),
        'length_offset': round(length_offset_m, 2),
        'shift_offset': round(shift_offset_m, 2),
    }

def calculate_fidelity(scale_factor, local_shifts, track_length,
                       raw_delta, smooth_delta, lap_time,
                       endpoint_correction):
    """
    Pipeline Fidelity — total intervention across all 4 steps.
    Each step normalized as % of its natural baseline.
    """
    # Step 1: Distance Scaling — how far scale_factor deviates from 1.0
    step1 = abs(scale_factor - 1.0) * 100
    
    # Step 2: Shift Warping — RMS of local shifts / track length
    if len(local_shifts) > 0:
        step2 = (np.sqrt(np.mean(np.array(local_shifts)**2)) / track_length) * 100
    else:
        step2 = 0.0
    
    # Step 3: Smoothing — RMS of (smoothed - raw) / lap time
    diff = smooth_delta - raw_delta
    step3 = (np.sqrt(np.mean(diff**2)) / lap_time) * 100
    
    # Step 4: Endpoint Correction — |correction| / lap time
    step4 = (abs(endpoint_correction) / lap_time) * 100
    
    total = step1 + step2 + step3 + step4
    fidelity = 100.0 - total
    
    # Budget: what % of total intervention each step contributed
    if total > 0:
        budget = {
            'scale':    round((step1 / total) * 100, 1),
            'warp':     round((step2 / total) * 100, 1),
            'smooth':   round((step3 / total) * 100, 1),
            'endpoint': round((step4 / total) * 100, 1),
        }
    else:
        budget = {'scale': 0, 'warp': 0, 'smooth': 0, 'endpoint': 0}
    
    return {
        'fidelity': round(fidelity, 3),
        'total_intervention': round(total, 3),
        'steps': {
            'scale':    round(step1, 4),
            'warp':     round(step2, 4),
            'smooth':   round(step3, 4),
            'endpoint': round(step4, 4),
        },
        'budget': budget,
    }


# 3. GET TRACK LAYOUT (Corners & Sectors)
def get_track_layout(session, ref_driver):
    layout = {"corners": [], "sectors": []}
    
    try:
        circuit_info = session.get_circuit_info()
        if circuit_info is not None:
            for _, corner in circuit_info.corners.iterrows():
                layout["corners"].append({
                    "number": int(corner['Number']),
                    "letter": corner['Letter'] if not pd.isna(corner['Letter']) else "",
                    "distance": float(corner['Distance']),
                    "angle": float(corner['Angle'])
                })
    except Exception as e:
        print(f"⚠️ Could not fetch circuit info: {e}")

    try:
        lap = session.laps.pick_driver(ref_driver).pick_fastest()
        tel = lap.get_telemetry()
        
        sec1_time = lap['Sector1Time']
        s1_row = tel[tel['Time'] >= sec1_time].iloc[0]
        layout["sectors"].append({"id": 1, "end_dist": float(s1_row['Distance'])})
        
        sec2_time = sec1_time + lap['Sector2Time']
        s2_row = tel[tel['Time'] >= sec2_time].iloc[0]
        layout["sectors"].append({"id": 2, "end_dist": float(s2_row['Distance'])})
        
        layout["sectors"].append({"id": 3, "end_dist": float(tel['Distance'].max())})
        
    except Exception as e:
        print(f"⚠️ Could not calc sector boundaries: {e}")
        
    return layout

track_layout = get_track_layout(session, ref_driver)

# 4. DATA ENGINE
def get_clean_trace(driver):
    laps = session.laps.pick_drivers(driver)
    if laps.empty: return None
    lap = laps.pick_fastest()
    tel = lap.get_telemetry()
    return {
        'dist': tel['Distance'].values,
        'speed': tel['Speed'].values,
        'throttle': tel['Throttle'].values,
        'brake': tel['Brake'].values,
        'time': tel['Time'].dt.total_seconds().values,
        'driver': driver,
        'lap_time': lap['LapTime'].total_seconds(),
        'full_name': session.get_driver(driver)['FullName']
    }

# 5. HI-FI DELTA ENGINE — returns delta, integrity, AND fidelity
def calculate_hifi_delta(ref, tgt):
    master_len = ref['dist'].max()
    tgt_max_dist = tgt['dist'].max()
    
    # ── STEP 1: Distance Scaling ──
    scale_factor = master_len / tgt_max_dist
    tgt_dist_scaled = tgt['dist'] * scale_factor
    length_offset_m = abs(master_len - tgt_max_dist)
    
    # ── STEP 2: Windowed Cross-Correlation ──
    window_size = 300; step_size = 50 
    grid_len = 10000; common_grid = np.linspace(0, master_len, grid_len)
    v_ref = np.interp(common_grid, ref['dist'], ref['speed'])
    v_tgt = np.interp(common_grid, tgt_dist_scaled, tgt['speed'])
    
    shifts = []; positions = []
    for start_pos in range(0, int(master_len), step_size):
        end_pos = start_pos + window_size
        if end_pos > master_len: break
        idx_start = int((start_pos / master_len) * grid_len)
        idx_end = int((end_pos / master_len) * grid_len)
        corr = correlate(v_ref[idx_start:idx_end], v_tgt[idx_start:idx_end], mode='same')
        if len(corr) == 0: continue
        lag_idx = np.argmax(corr) - (len(corr) // 2)
        shift_m = lag_idx * (master_len / grid_len)
        if abs(shift_m) < 40:
            shifts.append(shift_m); positions.append(start_pos + window_size/2)
    
    # Global shift for integrity score
    v_ref_full = (v_ref - np.mean(v_ref)) / (np.std(v_ref) + 1e-6)
    v_tgt_full = (v_tgt - np.mean(v_tgt)) / (np.std(v_tgt) + 1e-6)
    corr_full = correlate(v_ref_full, v_tgt_full, mode='same')
    global_lag = np.argmax(corr_full) - (len(corr_full) // 2)
    shift_offset_m = abs(global_lag * (master_len / grid_len))
    
    # Shape Integrity (input-based metric)
    integrity = calculate_integrity_score(length_offset_m, shift_offset_m)
    
    # Apply warping — store local shift values for fidelity
    local_shifts_applied = []
    if positions:
        if positions[0] > 0: positions.insert(0, 0); shifts.insert(0, shifts[0])
        if positions[-1] < master_len: positions.append(master_len); shifts.append(shifts[-1])
        sorted_pairs = sorted(zip(positions, shifts))
        positions, shifts = zip(*sorted_pairs)
        shift_interp = interp1d(positions, shifts, kind='linear', fill_value="extrapolate")
        local_shifts_applied = shift_interp(tgt_dist_scaled).tolist()
        tgt_dist_warped = tgt_dist_scaled + shift_interp(tgt_dist_scaled)
    else:
        tgt_dist_warped = tgt_dist_scaled

    # ── STEP 3: Time Mapping + Smoothing ──
    f_tgt_time = interp1d(tgt_dist_warped, tgt['time'], fill_value="extrapolate")
    tgt_time_mapped = f_tgt_time(ref['dist'])
    raw_delta = tgt_time_mapped - ref['time']
    delta_smooth = medfilt(raw_delta, kernel_size=15)
    delta_zeroed = delta_smooth - delta_smooth[0]
    raw_delta_zeroed = raw_delta - raw_delta[0]

    # ── STEP 4: Endpoint Correction ──
    actual_lap_diff = tgt['lap_time'] - ref['lap_time']
    endpoint_correction = delta_zeroed[-1] - actual_lap_diff
    
    ramp = np.linspace(0, 1, len(delta_zeroed))
    final_delta = delta_zeroed - (ramp * endpoint_correction)
    
    # ── Pipeline Fidelity (all-step metric) ──
    fidelity = calculate_fidelity(
        scale_factor=scale_factor,
        local_shifts=local_shifts_applied,
        track_length=master_len,
        raw_delta=raw_delta_zeroed,
        smooth_delta=delta_zeroed,
        lap_time=ref['lap_time'],
        endpoint_correction=endpoint_correction,
    )
    
    return ref['dist'], final_delta, integrity, fidelity


# 6. VISUALIZATION
ref_data = get_clean_trace(ref_driver)
if not ref_data: raise ValueError("Ref data missing")

fig, (ax_speed, ax_input, ax_delta) = plt.subplots(3, 1, figsize=(20, 12), sharex=True, 
                                                   gridspec_kw={'height_ratios': [2, 1, 1.5]})
plt.subplots_adjust(hspace=0.05)

export_grid = np.linspace(0, ref_data['dist'].max(), 2000)

integrity_results = {}
fidelity_results = {}

# A. Plot Speed (Top)
for driver in DRIVERS:
    d_data = get_clean_trace(driver)
    if not d_data: continue
    spd_interp = np.interp(export_grid, d_data['dist'], d_data['speed'])
    col = fastf1.plotting.get_driver_color(driver, session=session)
    ax_speed.plot(export_grid, spd_interp, color=col, label=driver, linewidth=2)

ax_speed.set_ylabel("Speed (km/h)")
ax_speed.legend(loc='lower left')
ax_speed.grid(True, alpha=0.2)

# B. Plot Inputs (Middle)
ref_throttle = np.interp(export_grid, ref_data['dist'], ref_data['throttle'])
ref_brake = np.interp(export_grid, ref_data['dist'], ref_data['brake'])
ax_input.plot(export_grid, ref_throttle, color='green', label='Throttle', alpha=0.8)
ax_input.plot(export_grid, ref_brake * 100, color='red', label='Brake', alpha=0.8)
ax_input.set_ylabel("Input %")
ax_input.legend(loc='center left')
ax_input.grid(True, alpha=0.2)

# C. Plot Delta (Bottom)
for driver in DRIVERS:
    if driver == ref_driver: 
        ax_delta.axhline(0, color=fastf1.plotting.get_driver_color(driver, session=session), linewidth=2)
        continue
    
    d_data = get_clean_trace(driver)
    if not d_data: continue
    
    dist_vals, delta_vals, integrity, fidelity = calculate_hifi_delta(ref_data, d_data)
    integrity_results[driver] = integrity
    fidelity_results[driver] = fidelity
    
    delta_interp = np.interp(export_grid, dist_vals, delta_vals)
    col = fastf1.plotting.get_driver_color(driver, session=session)
    ax_delta.plot(export_grid, delta_interp, color=col, linewidth=2)

ax_delta.set_ylabel("Delta (s)")
ax_delta.grid(True, alpha=0.2)
ax_delta.invert_yaxis()

# D. OVERLAY CORNERS & SECTORS
y_min_speed, y_max_speed = ax_speed.get_ylim()

sec_start = 0
for i, sector in enumerate(track_layout['sectors']):
    end = sector['end_dist']
    for ax in [ax_speed, ax_input, ax_delta]:
        ax.axvline(end, color='white', linestyle='--', alpha=0.3)
    ax_speed.text((sec_start + end)/2, y_min_speed + 10, f"SECTOR {sector['id']}", 
                  color='white', ha='center', fontsize=10, alpha=0.5, weight='bold')
    sec_start = end

for corner in track_layout['corners']:
    dist = corner['distance']
    num = f"{corner['number']}{corner['letter']}"
    for ax in [ax_speed, ax_input, ax_delta]:
        ax.axvline(dist, color='gray', linestyle=':', alpha=0.5, linewidth=1)
    ax_speed.text(dist, y_max_speed - 20, num, color='white', ha='center', 
                  bbox=dict(facecolor='gray', alpha=0.5, edgecolor='none', boxstyle='round,pad=0.2'))

# ══════════════════════════════════════════════════════════════════
# E. INTEGRITY + FIDELITY BADGES
# ══════════════════════════════════════════════════════════════════
y_min_delta, y_max_delta = ax_delta.get_ylim()
badge_x = ref_data['dist'].max() * 0.98
badge_spacing = (y_max_delta - y_min_delta) * 0.14

for i, driver in enumerate(integrity_results):
    integrity = integrity_results[driver]
    fidelity = fidelity_results[driver]
    badge_y = y_min_delta + badge_spacing * (i + 1)
    
    badge_text = f"{driver}: Fidelity {fidelity['fidelity']:.1f}% | Shape {integrity['score']:.1f}% ({integrity['grade']})"
    ax_delta.text(badge_x, badge_y, badge_text,
                  fontsize=8, fontweight='bold', color=integrity['grade_color'],
                  ha='right', va='center',
                  bbox=dict(facecolor='white', alpha=0.85, edgecolor=integrity['grade_color'], 
                            linewidth=1.5, boxstyle='round,pad=0.3'))

# Session-level badges
if integrity_results:
    all_int_scores = [v['score'] for v in integrity_results.values()]
    all_fid_scores = [v['fidelity'] for v in fidelity_results.values()]
    session_integrity = np.mean(all_int_scores)
    session_fidelity = np.mean(all_fid_scores)
    session_min_int = min(all_int_scores)
    
    if session_min_int >= 95:   session_grade, session_color = "Excellent", "#16813D"
    elif session_min_int >= 85: session_grade, session_color = "Good", "#0f3460"
    elif session_min_int >= 70: session_grade, session_color = "Acceptable", "#CC8800"
    elif session_min_int >= 50: session_grade, session_color = "Warning", "#CC0000"
    else:                       session_grade, session_color = "Critical", "#990000"
    
    ax_speed.text(0.99, 0.97, 
                  f"Fidelity: {session_fidelity:.2f}% | Shape Integrity: {session_integrity:.1f}% | {session_grade}",
                  transform=ax_speed.transAxes, fontsize=10, fontweight='bold',
                  color=session_color, ha='right', va='top',
                  bbox=dict(facecolor='white', alpha=0.9, edgecolor=session_color, 
                            linewidth=2, boxstyle='round,pad=0.4'))

plt.suptitle(f"F1 Telemetry Stack | {GP} {YEAR}", fontsize=16)
plt.savefig('f1_full_analysis.png', dpi=150)

# 7. EXPORT JSON
export_data = {
    "track_layout": track_layout,
    "data_integrity": {
        "session": {
            "avg_fidelity": round(session_fidelity, 3) if fidelity_results else None,
            "avg_shape_integrity": round(session_integrity, 1) if integrity_results else None,
            "grade": session_grade if integrity_results else None,
            "comparisons": len(integrity_results)
        },
        "per_driver": {},
        "config": {
            "integrity": {
                "tau": INTEGRITY_TAU, "p": INTEGRITY_P, "lambda": INTEGRITY_LAMBDA,
                "formula": "S(x) = 100 * exp(-max(0, x - tau)^p / lambda)"
            },
            "fidelity": {
                "formula": "Fidelity = 100 - (step1% + step2% + step3% + step4%)",
                "step1": "|scale_factor - 1| * 100",
                "step2": "RMS(local_shifts) / track_length * 100",
                "step3": "RMS(smooth - raw) / lap_time * 100",
                "step4": "|endpoint_correction| / lap_time * 100",
            }
        }
    }
}

for driver in integrity_results:
    export_data["data_integrity"]["per_driver"][driver] = {
        "shape_integrity": integrity_results[driver],
        "pipeline_fidelity": fidelity_results[driver],
    }

with open('f1_track_layout.json', 'w') as f:
    json.dump(export_data, f, indent=4)

# 8. CONSOLE REPORT
print("\n" + "═" * 72)
print("  CONSOLIDATED DATA INTEGRITY REPORT")
print("═" * 72)
print(f"  Session: {GP} {YEAR} {SESSION}")
print(f"  Reference: {ref_driver}")
print("═" * 72)

for driver in integrity_results:
    integrity = integrity_results[driver]
    fidelity = fidelity_results[driver]
    steps = fidelity['steps']
    budget = fidelity['budget']
    
    bar_fid = int(fidelity['fidelity'] / 2.5)
    bar_int = int(integrity['score'] / 2.5)
    
    print(f"\n  {driver} vs {ref_driver}:")
    print(f"  ┌─ Pipeline Fidelity ─────────────────────────────────────────┐")
    print(f"  │  {'█' * bar_fid}{'░' * (40 - bar_fid)} {fidelity['fidelity']:>7.3f}%  │")
    print(f"  │  Total intervention: {fidelity['total_intervention']:.3f}%                              │")
    print(f"  │  ├─ Step 1 (Scale):    {steps['scale']:>7.4f}%  ({budget['scale']:>4.1f}% of budget)    │")
    print(f"  │  ├─ Step 2 (Warp):     {steps['warp']:>7.4f}%  ({budget['warp']:>4.1f}% of budget)    │")
    print(f"  │  ├─ Step 3 (Smooth):   {steps['smooth']:>7.4f}%  ({budget['smooth']:>4.1f}% of budget)    │")
    print(f"  │  └─ Step 4 (Endpoint): {steps['endpoint']:>7.4f}%  ({budget['endpoint']:>4.1f}% of budget)    │")
    print(f"  └─────────────────────────────────────────────────────────────┘")
    print(f"  ┌─ Shape Integrity ───────────────────────────────────────────┐")
    print(f"  │  {'█' * bar_int}{'░' * (40 - bar_int)} {integrity['score']:>7.1f}%  ({integrity['grade']})│")
    print(f"  │  Length: {integrity['length_offset']:>6.1f}m  Shift: {integrity['shift_offset']:>5.1f}m  Total: {integrity['total_offset']:>6.1f}m  │")
    print(f"  └─────────────────────────────────────────────────────────────┘")

if integrity_results:
    print(f"\n{'─' * 72}")
    print(f"  Session Summary:")
    print(f"    Pipeline Fidelity:  {session_fidelity:.3f}% avg")
    print(f"    Shape Integrity:    {session_integrity:.1f}% avg  |  Grade: {session_grade}")
    
    if session_min_int < 70:
        flagged = sum(1 for v in integrity_results.values() if v['score'] < 70)
        print(f"\n  ⚠️  QUALITY GATE: {flagged} comparison(s) below 70% shape integrity")
    else:
        print(f"\n  ✅ All comparisons passed quality gate")

print("═" * 72)
print("✅ Visualization saved to 'f1_full_analysis.png'")
print("✅ Layout + integrity data saved to 'f1_track_layout.json'")