"""Run cache/_autofit_2026.py for Singapore through cache/_sim_singapore.py (GAIN guard, see there)."""
import os, sys
here = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, here)
import _autofit_2026 as af
af.SIM = os.path.join(here, "_sim_singapore.py")
sys.argv = [sys.argv[0], "--track", "singapore"] + sys.argv[1:]
sys.exit(af.main())
