"""Run the 20-prompt adversarial suite (+ naive baseline) against the current data and print the pass rate."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import adversarial, db  # noqa: E402
from app.memory import current_mode  # noqa: E402

db.conn()
if not db.one("SELECT id FROM engagements LIMIT 1"):
    sys.exit("No data — run scripts/seed.py first.")
r = adversarial.run_suite()
print(f"[{current_mode().upper()}] isolated architecture: {r['passed']}/{r['total']} passed")
for x in r["results"]:
    print(f"  {'PASS' if x['passed'] else 'FAIL'} {x['test_id']} {x['category']:<24} {x['explanation'][:90]}")
n = adversarial.run_naive()
print(f"naive pooled baseline (simulated): {n['passed']}/{n['total']} passed, {n['leaked_terms']} leaked terms")
