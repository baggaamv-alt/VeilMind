"""Reset all banks + app data and seed the 9 synthetic engagements into the ACTIVE mode's backend.

    python scripts/seed.py            # uses APP_MODE from .env
    python scripts/seed.py --demo     # force DEMO MODE for this run
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if "--demo" in sys.argv:
    os.environ["APP_MODE"] = "demo"
from app import seed  # noqa: E402
from app.memory import current_mode  # noqa: E402

print(f"Seeding in {current_mode().upper()} MODE...")
res = seed.reset_and_seed(progress=lambda m: print("  -", m))
print("Done:", res)
