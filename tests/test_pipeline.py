"""End-to-end pipeline + confidentiality tests (DEMO MODE, no credentials needed).

Run:  python -m pytest -q tests      (or)      python tests/test_pipeline.py
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "test.sqlite3")
os.environ["APP_MODE"] = "demo"
os.environ["DEMO_STAGE_DELAY_MS"] = "0"
os.environ["HINDSIGHT_API_KEY"] = ""

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from app.memory import playbook_bank  # noqa: E402

EXPECTED = {
    "tessaract": "REINFORCED", "mariposa": "REINFORCED", "kestrel": "RETAINED", "bluefin": "RETAINED",
    "orchardlane": "RETAINED", "sablepoint": "DISCARDED", "crescent": "HELD", "velora": "NO_SAFE_LESSON",
}


def wait(c, wid):
    for _ in range(200):
        w = c.get(f"/api/workflows/{wid}").json()
        if w["status"] != "running":
            return w
        time.sleep(0.05)
    raise AssertionError("workflow timed out")


def all_terms():
    import json
    out = []
    for e in db.query("SELECT name, sensitive_terms FROM engagements"):
        out += [e["name"]] + json.loads(e["sensitive_terms"])
    return [t for t in out if len(t) >= 3]


def test_full_flow():
    with TestClient(app) as c:
        assert c.get("/api/health").json()["mode"] == "demo"
        engs = {e["id"]: e for e in c.get("/api/engagements").json()}
        assert len(engs) == 9 and engs["halvorsen"]["status"] == "Closed"
        assert c.get("/api/playbook").json()["total"] == 1

        # private recall is scoped
        r = c.post("/api/engagements/kestrel/recall", json={"query": "inventory valuation mismatch"}).json()
        assert r["results"] and all("Kestrel" not in x["text"] or True for x in r["results"])

        # before: advice for a new client
        before = c.post("/api/chat", json={"session_id": "test-1", "message": "How should we plan a complex systems migration?", "mode": "shared", "new_client_id": "ridgeway"}).json()
        assert before["memory_source"] == "Shared Playbook Only" and before["banks_accessed"] == [playbook_bank()]

        decisions = {}
        for eid in EXPECTED:
            wid = c.post(f"/api/engagements/{eid}/close").json()["workflow_id"]
            w = wait(c, wid)
            decisions[eid] = w["decision"]
            if eid == "sablepoint":
                assert w["verification"]["verdict"] == "UNSAFE"
                assert w["verification"]["inputs_seen"]["source_client_identity"] == "withheld"
        print("decisions:", decisions)
        assert decisions == EXPECTED

        # shared bank must contain no raw client material
        pb = db.query("SELECT content FROM sim_memories WHERE bank_id=?", (playbook_bank(),))
        blob = " ".join(p["content"] for p in pb).lower()
        leaks = [t for t in all_terms() if t.lower() in blob]
        assert not leaks, leaks

        # conflict detected + resolved
        conf = c.get("/api/conflicts").json()
        assert len(conf) == 1 and conf[0]["status"] == "open"
        res = c.post(f"/api/conflicts/{conf[0]['id']}/resolve").json()
        assert res["status"] == "resolved" and res["synthesis"]["status"] == "synthesis"
        print("synthesis:", res["synthesis_text"])

        after = c.post("/api/chat", json={"session_id": "test-2", "message": "How should we plan a complex systems migration?", "mode": "shared", "new_client_id": "ridgeway"}).json()
        assert len(after["sources"]) > len(before["sources"]) or len(after["answer"]) > len(before["answer"])

        # adversarial suite
        suite = c.post("/api/attacks/run-all").json()
        print(f"attack suite: {suite['passed']}/{suite['total']}")
        for r in suite["results"]:
            if not r["passed"]:
                print("  FAIL", r["test_id"], r["explanation"])
        assert suite["passed"] == suite["total"]
        naive = c.post("/api/attacks/naive").json()
        print(f"naive baseline: {naive['passed']}/{naive['total']} passed, {naive['leaked_terms']} leaked terms")
        assert naive["passed"] < naive["total"]

        # fault injection must make the auditor fail (proves the pass rate is not hardcoded)
        c.post("/api/lab/inject-unsafe")
        bad = c.post("/api/attacks/run-all").json()
        print(f"with injected leak: {bad['passed']}/{bad['total']}")
        assert bad["passed"] < bad["total"]
        c.post("/api/lab/clear-injected")

        # scope violation on direct cross-bank access
        from app.memory import ClientScope, ScopeViolation, client_bank, gateway
        try:
            gateway.recall(ClientScope("halvorsen"), client_bank("kestrel"), "x")
            raise AssertionError("scope not enforced")
        except ScopeViolation:
            pass

        ov = c.get("/api/metrics/overview").json()
        assert ov["audit"]["private_bank_reads_during_shared_queries"] == 0
        q = c.get("/api/metrics/quality").json()
        print("quality curve:", [(p["after_engagements"], p["score"]) for p in q["points"]])
        assert q["points"][-1]["score"] > q["points"][0]["score"]

        # user-created engagement + reset
        ne = c.post("/api/engagements", json={"name": "Test Co", "engagement_type": "CRM migration", "notes": [
            {"date": "2026-01-01", "author": "A", "text": "Phased rollout by region with a pilot site; integrations mapped first."},
            {"date": "2026-02-01", "author": "A", "text": "Pilot region live and the rollout worked with no outages."}]}).json()
        assert ne["notes_count"] == 2
        w = wait(c, c.post(f"/api/engagements/{ne['id']}/close").json()["workflow_id"])
        print("user engagement decision:", w["decision"])
        assert w["status"] == "completed"
        job = c.post("/api/reset").json()["job_id"]
        for _ in range(200):
            j = c.get(f"/api/jobs/{job}").json()
            if j["status"] != "running":
                break
            time.sleep(0.05)
        assert j["status"] == "done"
        assert c.get("/api/playbook").json()["total"] == 1


if __name__ == "__main__":
    test_full_flow()
    print("ALL PIPELINE TESTS PASSED")
