"""
F1 LAP DELTA ENGINE

One method: F1InsightsHub's alignData, ported exactly (f1ih_port.py, next to this file),
fed from FastF1 car data (lap.get_car_data(interpolate_edges=True), the same data
their backend serves). No position data is used. It reproduces their CSV exports
exactly (checked in the DELTA RECREATION repo, experiments/r25_engine_check.py).

Usage
    from hifi_delta_v2 import get_trace, calculate_delta

    ref = get_trace(session, 'VER')       # first driver = reference (zero line)
    tgt = get_trace(session, 'LEC')
    dist, delta = calculate_delta(ref, tgt)

    dist   their distance grid along the lap, metres
    delta  seconds, + = target slower
"""

import os
import sys
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import f1ih_port as fp

__all__ = ['get_trace', 'calculate_delta']

def _secs(x):
    return x.total_seconds() if pd.notna(x) else None

def get_trace(session, driver, lap=None):
    """Trace dict for the driver's fastest lap (or the given FastF1 Lap)."""
    if lap is None:
        laps = session.laps.pick_drivers(driver)
        if laps.empty: return None
        lap = laps.pick_fastest()
    if lap is None or (hasattr(lap, 'empty') and lap.empty): return None
    if pd.isna(lap['LapTime']): return None
    car = lap.get_car_data(interpolate_edges=True)
    if car.empty: return None

    ms = (session.t0_date + car['SessionTime']).astype('datetime64[ns]').astype('int64') // 10**6
    meta = dict(lapDuration=_secs(lap['LapTime']), lapDurationS1=_secs(lap['Sector1Time']),
                lapDurationS2=_secs(lap['Sector2Time']), lapNumber=int(lap['LapNumber']), position=None)
    samples = [dict(_ms=float(t), speed=float(v), throttle=float(th), brake=int(bool(br)), rpm=float(r),
                    nGear=int(g), drs=int(dr), **meta)
               for t, v, th, br, r, g, dr in zip(ms, car['Speed'], car['Throttle'], car['Brake'],
                                                  car['RPM'], car['nGear'], car['DRS'])]

    full_name = driver
    try:
        full_name = str(session.get_driver(driver)['FullName'])
    except Exception:
        pass

    return {'driver': driver, 'full_name': full_name, 'lap_number': int(lap['LapNumber']),
            'lap_time': lap['LapTime'].total_seconds(), 'samples': samples}

def calculate_delta(ref, tgt, max_points=800):
    """Returns (dist, delta). max_points=800 is their chart/CSV downsampling
    (None keeps every grid point)."""
    aligned = fp.align_data([ref['samples'], tgt['samples']], 0)[0]
    pts = fp.chart_delta(aligned, max_points=max_points or 10**9)[1]
    dist = np.array([x for x, _ in pts], dtype=float)
    delta = np.array([np.nan if y is None else y for _, y in pts], dtype=float)
    return dist, delta
