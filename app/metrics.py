"""Dashboard metrics — all computed from stored records, nothing hardcoded."""
from __future__ import annotations

import re

from . import adversarial, db, pipeline, simulator
from .memory import current_mode, playbook_bank

HELD_OUT_CLIENT = "Ridgeway Freight Rail (held-out new client)"
HELD_OUT_QUESTION = ("We're replacing a legacy dispatch system used across many depots with dozens of integrations. "
                     "Should we cut over all at once or in phases, and how do we de-risk it?")
RUBRIC = [
    ("Recommends a phased / wave approach where appropriate", r"phased|wave"),
    ("Calls out integration / dependency mapping", r"integration|dependenc"),
    ("Parallel run or reconciliation gate", r"parallel|reconcil"),
    ("Pilot on a small first site", r"pilot"),
    ("Validation sign-off / go-live gate", r"sign-off|gate|validation"),
    ("Conditional: when a single cutover is better", r"single.{0,25}cutover|tightly|interdependent"),
    ("Rehearsal and rollback criterion", r"rehears|rollback"),
    ("Frontline adoption (champions / super-users)", r"champion|super-user|frontline"),
    ("States evidence strength from ≥2 engagements", r"\b([2-9]|two|three|four|five) (independent|verified)|Moderate|Strong"),
]


def score_advice(text: str) -> dict:
    hits = [{"item": label, "hit": bool(re.search(pat, text, re.I))} for label, pat in RUBRIC]
    n = sum(h["hit"] for h in hits)
    return {"score": round(100 * n / len(RUBRIC)), "hits": hits, "points": n, "max": len(RUBRIC)}


def overview() -> dict:
    e = db.one("SELECT COUNT(*) total, SUM(status='Active') active, SUM(status='Closed') closed FROM engagements")
    notes = db.one("SELECT COUNT(*) n FROM notes")["n"]
    lessons = db.one("SELECT COUNT(*) n, COALESCE(SUM(evidence_count),0) ev FROM lessons WHERE status IN ('retained','synthesis')")
    held = db.one("SELECT COUNT(*) n FROM lessons WHERE status='held'")["n"]
    injected = db.one("SELECT COUNT(*) n FROM lessons WHERE status='injected'")["n"]
    dec = {r["decision"]: r["n"] for r in db.query("SELECT decision, COUNT(*) n FROM workflows WHERE status='completed' GROUP BY decision")}
    conflicts = db.one("SELECT COUNT(*) total, SUM(status='open') open FROM conflicts")
    last = adversarial.latest()
    shared_callers = ("advisor.shared", "attack-lab.shared")
    qs = ",".join("?" * len(shared_callers))
    private_reads = db.one(f"SELECT COUNT(*) n FROM access_log WHERE caller IN ({qs}) AND bank_id<>? AND allowed=1",
                           (*shared_callers, playbook_bank()))["n"]
    shared_queries = db.one(f"SELECT COUNT(*) n FROM access_log WHERE caller IN ({qs}) AND operation='recall'", shared_callers)["n"]
    refused = db.one("SELECT COUNT(*) n FROM access_log WHERE allowed=0")["n"]
    return {
        "mode": current_mode(),
        "engagements": {"total": e["total"] or 0, "active": e["active"] or 0, "closed": e["closed"] or 0},
        "private_memories": notes,
        "verified_lessons": lessons["n"],
        "evidence_total": lessons["ev"],
        "held_lessons": held,
        "injected_unverified": injected,
        "blocked_lessons": dec.get("DISCARDED", 0) + dec.get("NO_SAFE_LESSON", 0),
        "decisions": dec,
        "conflicts": {"total": conflicts["total"] or 0, "open": conflicts["open"] or 0},
        "audit": {
            "last_run": last and {"run_id": last["run_id"], "passed": last["passed"], "total": last["total"], "ts": last["ts"]},
            "shared_queries": shared_queries,
            "private_bank_reads_during_shared_queries": private_reads,
            "refused_cross_bank_attempts": refused,
        },
    }


def evolution() -> list[dict]:
    return db.query("SELECT ts, lesson_count, evidence_total, event FROM playbook_snapshots ORDER BY id")


def quality() -> dict:
    """Advice for a held-out client, recomputed with the playbook as it stood after each contributing engagement.

    Always uses the deterministic composer so the curve is reproducible; in LIVE mode the current Hindsight
    answer is scored separately by the /api/metrics/quality?live=1 path in main.py.
    """
    wfs = db.query("SELECT * FROM workflows WHERE status='completed' AND decision IN ('RETAINED','REINFORCED') ORDER BY finished_at")
    all_lessons = {l["id"]: l for l in pipeline.list_lessons(("retained", "synthesis"))}
    state: dict[str, dict] = {}
    points = []
    for i, wf in enumerate(wfs, start=1):
        lid = wf["lesson_id"]
        if lid not in all_lessons:
            continue
        cand_cond = (db.jload(wf["candidate"], {}) or {}).get("conditions") or ""
        if lid in state:
            state[lid]["evidence_count"] += 1
            if cand_cond and cand_cond.lower() not in state[lid]["conditions"].lower():
                state[lid]["conditions"] = (state[lid]["conditions"].rstrip(". ") + "; " + cand_cond) if state[lid]["conditions"] else cand_cond
        else:
            # conditions as they stood at this point in time (not the later, accumulated version)
            state[lid] = dict(all_lessons[lid], evidence_count=1, conditions=cand_cond or (all_lessons[lid].get("conditions") or ""))
        # only the reinforcements that had happened by this point in time
        reinf = [h for h in all_lessons[lid]["history"] if h.get("event") == "reinforced"]
        state[lid]["history"] = reinf[: state[lid]["evidence_count"] - 1]
        syn = [dict(l) for l in all_lessons.values() if l["status"] == "synthesis" and (l["created_at"] or "") <= (wf["finished_at"] or "")]
        advice = simulator.compose_advice(HELD_OUT_QUESTION, list(state.values()) + syn, [])
        s = score_advice(advice["text"])
        points.append({"after_engagements": i, "lessons": len(state) + len(syn), "score": s["score"], "hits": s["hits"], "advice": advice["text"]})
    syn_all = [l for l in all_lessons.values() if l["status"] == "synthesis"]
    if points and syn_all and points[-1]["lessons"] < len(state) + len(syn_all):
        advice = simulator.compose_advice(HELD_OUT_QUESTION, list(state.values()) + syn_all, [])
        s = score_advice(advice["text"])
        points.append({"after_engagements": len(wfs), "lessons": len(state) + len(syn_all), "score": s["score"], "hits": s["hits"],
                       "advice": advice["text"], "note": "after conflict synthesis"})
    return {
        "client": HELD_OUT_CLIENT, "question": HELD_OUT_QUESTION, "rubric": [r[0] for r in RUBRIC], "points": points,
        "method": "Automated keyword rubric over advice generated by the deterministic composer from playbook snapshots. "
                  "Illustrative coverage score — not a human-judged or measured accuracy metric.",
    }


def comparison() -> dict:
    iso = adversarial.latest(False)
    naive = adversarial.latest(True)

    def summ(r):
        if not r:
            return None
        return {"passed": r["passed"], "total": r["total"], "leaked_terms": sum(len(x["leaked"]) for x in r["results"]),
                "rate": round(100 * r["passed"] / r["total"]) if r["total"] else 0}

    return {"isolated": summ(iso), "naive": summ(naive),
            "naive_note": "Naive baseline = every client's raw notes pooled into one shared context with no wall. "
                          "Built only for this comparison; never used by Veilmind."}
