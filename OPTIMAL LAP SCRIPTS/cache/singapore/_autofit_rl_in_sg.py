"""Singapore knob refit on a FIXED raceline: cache/_autofit_2026.py unchanged, sims run through
cache/_sim_singapore.py (GAIN guard) with --raceline-in <line> (mirror frame).
  python cache/singapore/_autofit_rl_in_sg.py <raceline.json>"""
import os, sys
CACHE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, CACHE)
RL = os.path.abspath(sys.argv.pop(1))
import _autofit_2026 as A
A.SIM = os.path.join(CACHE, "_sim_singapore.py")
_run = A.subprocess.run
def run(cmd, *a, **k):
    if isinstance(cmd, list) and cmd[1:2] == [A.SIM]: cmd = cmd + ["--raceline-in", RL]
    return _run(cmd, *a, **k)
A.subprocess.run = run
sys.argv = [A.__file__, "--track", "singapore"]
sys.exit(A.main())
