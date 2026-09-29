"""FastAPI application: API + static frontend."""

import json
import os
import re
import traceback

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import adversarial, advisor, db, metrics, pipeline, seed
from .config import DATA_DIR, STATIC_DIR, settings
from .llm import LLMUnavailable
from .memory import (ClientScope, PlaybookScope, ScopeViolation, client_bank, current_mode, gateway, mode_info,
                     playbook_bank, verifier_bank)

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_app):
    db.conn()
    if not db.one("SELECT id FROM engagements LIMIT 1") and current_mode() == "demo":
        seed.reset_and_seed()  # DEMO MODE auto-seeds so the dashboard is never empty; LIVE MODE seeds on request
    yield


app = FastAPI(title="Veilmind", version="1.1.0", lifespan=lifespan,
              description="Prototype: isolated per-client Hindsight banks + independently verified shared playbook.")


# ----------------------------------------------------------------------------- errors
@app.exception_handler(ValueError)
async def _value_error(_: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"error": str(exc)})


@app.exception_handler(ScopeViolation)
async def _scope(_: Request, exc: ScopeViolation):
    return JSONResponse(status_code=403, content={"error": str(exc), "kind": "scope_violation"})


@app.exception_handler(LLMUnavailable)
async def _llm(_: Request, exc: LLMUnavailable):
    return JSONResponse(status_code=503, content={"error": f"LLM unavailable after retries: {exc}"})


@app.exception_handler(Exception)
async def _any(_: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc()[-800:]})


# ----------------------------------------------------------------------------- models
class NoteIn(BaseModel):
    date: str | None = Field(default=None, max_length=10)
    author: str = Field(default="Consultant", max_length=80)
    text: str = Field(min_length=5, max_length=4000)

    @field_validator("date")
    @classmethod
    def _date(cls, v):
        if v and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
            raise ValueError("date must be YYYY-MM-DD")
        return v


class EngagementIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    engagement_type: str = Field(min_length=2, max_length=120)
    industry: str = Field(default="", max_length=120)
    region: str = Field(default="", max_length=120)
    size: str = Field(default="", max_length=120)
    partner: str = Field(default="", max_length=80)
    sensitive_terms: list[str] = Field(default_factory=list)
    notes: list[NoteIn] = Field(default_factory=list, max_length=60)


class RecallIn(BaseModel):
    query: str = Field(min_length=2, max_length=500)


class TextIn(BaseModel):
    text: str = Field(min_length=5, max_length=4000)


class ChatIn(BaseModel):
    session_id: str = Field(min_length=3, max_length=64)
    message: str = Field(min_length=1, max_length=2000)
    mode: str = Field(default="shared", pattern="^(shared|private)$")
    client_id: str | None = None
    new_client_id: str | None = None


class AttackIn(BaseModel):
    test_ids: list[str] | None = None


class CustomAttackIn(BaseModel):
    prompt: str = Field(min_length=3, max_length=2000)
    mode: str = Field(default="shared", pattern="^(shared|private)$")
    authorized_client: str | None = None


class ModeIn(BaseModel):
    mode: str = Field(pattern="^(live|demo|auto)$")


# ----------------------------------------------------------------------------- helpers
def _engagement(e: dict, detail: bool = False) -> dict:
    out = {k: e[k] for k in ("id", "name", "engagement_type", "status", "start_date", "end_date", "partner", "bank_id", "source", "closed_at")}
    out["notes_count"] = db.one("SELECT COUNT(*) n FROM notes WHERE engagement_id=?", (e["id"],))["n"]
    wf = db.one("SELECT id, decision, status FROM workflows WHERE engagement_id=? ORDER BY started_at DESC LIMIT 1", (e["id"],))
    out["last_workflow"] = wf
    if detail:
        out.update({k: e[k] for k in ("industry", "region", "size", "contract_value")})
        out["client_team"] = db.jload(e["client_team"], [])
        out["notes"] = db.query("SELECT id, date, author, text FROM notes WHERE engagement_id=? ORDER BY date, id", (e["id"],))
        out["has_simulation"] = bool(e.get("simulation"))
    return out


def _new_clients() -> list[dict]:
    with open(os.path.join(DATA_DIR, "new_clients.json"), encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------------------- system
@app.get("/api/health")
def health():
    ok = True
    try:
        db.one("SELECT 1 x")
    except Exception:  # noqa: BLE001
        ok = False
    return {"status": "ok" if ok else "degraded", "db": ok, **mode_info(), "version": app.version}


@app.get("/api/mode")
def get_mode():
    return mode_info()


@app.post("/api/mode")
def set_mode(body: ModeIn):
    if body.mode == "live" and not settings.live_available:
        raise ValueError("LIVE MODE needs HINDSIGHT_API_KEY in .env (restart the server after adding it).")
    before = current_mode()
    db.kv_set("mode_override", body.mode)
    after = current_mode()
    job = None
    if before != after:
        # state belongs to one backend at a time: reset + reseed into the newly active backend
        job = seed.start_job("seed", seed.reset_and_seed)
    return {**mode_info(), "reseed_job": job}


@app.post("/api/seed")
def seed_data():
    """Reset everything and seed the synthetic engagements (runs as a job; poll /api/jobs/{id})."""
    return {"job_id": seed.start_job("seed", seed.reset_and_seed), "mode": current_mode()}


@app.post("/api/reset")
def reset():
    return seed_data()


@app.get("/api/jobs/{job_id}")
def job(job_id: str):
    j = seed.JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "Unknown job")
    return j


# ----------------------------------------------------------------------------- engagements
@app.get("/api/engagements")
def list_engagements(status: str | None = None):
    rows = db.query("SELECT * FROM engagements ORDER BY status='Closed', start_date")
    if status:
        rows = [r for r in rows if r["status"].lower() == status.lower()]
    return [_engagement(r) for r in rows]


@app.post("/api/engagements")
def create_engagement(body: EngagementIn):
    slug = re.sub(r"[^a-z0-9]+", "", body.name.lower())[:24] or "client"
    base, i = slug, 2
    while db.one("SELECT id FROM engagements WHERE id=?", (slug,)):
        slug = f"{base}{i}"
        i += 1
    c = body.model_dump()
    c["id"] = slug
    c["start_date"] = (body.notes[0].date if body.notes and body.notes[0].date else db.now()[:10])
    from .memory import AdminScope
    gateway.create_bank(AdminScope("api.create"), client_bank(slug), f"Private: {body.name}", "Private engagement memory. Never shared.")
    seed.insert_engagement(c, source="user")
    if body.notes:
        seed.retain_notes(slug, body.name, [n.model_dump() for n in body.notes])
    db.log_activity("engagement", f"New engagement created: “{body.name}” with private bank {client_bank(slug)}", {"engagement_id": slug})
    return _engagement(db.one("SELECT * FROM engagements WHERE id=?", (slug,)), detail=True)


def _get_eng(eid: str) -> dict:
    e = db.one("SELECT * FROM engagements WHERE id=?", (eid,))
    if not e:
        raise HTTPException(404, f"Unknown engagement '{eid}'")
    return e


@app.get("/api/engagements/{eid}")
def engagement_detail(eid: str):
    return _engagement(_get_eng(eid), detail=True)


@app.post("/api/engagements/{eid}/notes")
def add_note(eid: str, body: NoteIn):
    e = _get_eng(eid)
    if e["status"] == "Closed":
        raise ValueError("Engagement is closed; its private bank is read-only.")
    res = seed.retain_notes(eid, e["name"], [body.model_dump()])
    db.log_activity("retain", f"Retained 1 note into {client_bank(eid)}", {"engagement_id": eid})
    return {"retained": True, "bank_id": client_bank(eid), "response": res}


@app.get("/api/engagements/{eid}/memory")
def engagement_memory(eid: str):
    _get_eng(eid)
    return {"bank_id": client_bank(eid), "memories": gateway.list_memories(ClientScope(eid, "api.inspect"), client_bank(eid)),
            "backend": current_mode()}


@app.post("/api/engagements/{eid}/recall")
def engagement_recall(eid: str, body: RecallIn):
    _get_eng(eid)
    return {"bank_id": client_bank(eid), "results": gateway.recall(ClientScope(eid, "api.recall"), client_bank(eid), body.query),
            "scope": f"client:{eid}", "engine": "scoped recall"}


@app.post("/api/engagements/{eid}/close")
def close_engagement(eid: str):
    _get_eng(eid)
    return {"workflow_id": pipeline.start_close(eid)}


# ----------------------------------------------------------------------------- pipeline
@app.get("/api/workflows")
def workflows():
    rows = db.query("SELECT w.id, w.engagement_id, e.name client_name, w.status, w.decision, w.mode, w.started_at, w.finished_at "
                    "FROM workflows w JOIN engagements e ON e.id=w.engagement_id ORDER BY w.started_at DESC")
    return rows


@app.get("/api/workflows/{wid}")
def workflow(wid: str):
    w = pipeline.get_workflow(wid)
    if not w:
        raise HTTPException(404, "Unknown workflow")
    return w


@app.post("/api/pipeline/distill/{eid}")
def distill_preview(eid: str):
    """Preview distillation only (nothing is verified or retained)."""
    return {"candidate": pipeline.distill(_get_eng(eid)), "retained": False}


@app.post("/api/pipeline/verify")
def verify(body: TextIn):
    """Run the independent leak check on arbitrary text (sees only the text)."""
    return pipeline.independent_check(body.text)


# ----------------------------------------------------------------------------- playbook
@app.get("/api/playbook")
def playbook(q: str = "", category: str = "", approach: str = "", outcome: str = "", strength: str = ""):
    items = pipeline.list_lessons()
    ql = q.lower().strip()
    out = []
    for l in items:
        if ql and ql not in (l["text"] + " " + (l.get("why") or "") + " " + (l.get("conditions") or "")).lower():
            continue
        if category and l["category"] != category:
            continue
        if approach and l["approach"] != approach:
            continue
        if outcome and l["outcome"] != outcome:
            continue
        if strength and l["strength"] != strength:
            continue
        out.append(l)
    return {"lessons": out, "total": len(items), "bank_id": playbook_bank(),
            "facets": {k: sorted({l[k] for l in items if l.get(k)}) for k in ("category", "approach", "outcome", "strength")}}


@app.get("/api/playbook/held")
def held():
    return pipeline.list_lessons(("held",))


@app.get("/api/playbook/{lid}")
def lesson(lid: str):
    l = pipeline.get_lesson(lid)
    if not l or l["status"] in ("merged",):
        raise HTTPException(404, "Unknown lesson")
    l["conflict"] = next((c for c in pipeline.list_conflicts() if c["id"] == l.get("conflict_id")), None)
    return l


@app.get("/api/playbook-bank/memories")
def playbook_memories():
    return {"bank_id": playbook_bank(), "memories": gateway.list_memories(PlaybookScope("api.inspect"), playbook_bank())}


# ----------------------------------------------------------------------------- chat
@app.get("/api/new-clients")
def new_clients():
    return _new_clients()


@app.post("/api/chat")
def chat(body: ChatIn):
    nc = next((c for c in _new_clients() if c["id"] == body.new_client_id), None)
    if body.mode == "private":
        _get_eng(body.client_id or "")
    return advisor.chat(body.session_id, body.message, body.mode, body.client_id, nc)


@app.get("/api/chat/{session_id}")
def chat_history(session_id: str):
    rows = db.query("SELECT role, content, mode, client_id, sources, engine, ts FROM chat_messages WHERE session_id=? ORDER BY id", (session_id,))
    for r in rows:
        r["sources"] = db.jload(r["sources"], [])
    return rows


# ----------------------------------------------------------------------------- attack lab
@app.get("/api/attacks")
def attacks():
    return {"prompts": adversarial.load_prompts(), "latest": adversarial.latest(), "mode": current_mode()}


@app.post("/api/attacks/run")
def attacks_run(body: AttackIn):
    return adversarial.run_suite(body.test_ids)


@app.post("/api/attacks/run-all")
def attacks_run_all():
    return adversarial.run_suite()


@app.post("/api/attacks/custom")
def attacks_custom(body: CustomAttackIn):
    if body.mode == "private":
        _get_eng(body.authorized_client or "")
    return adversarial.run_custom(body.prompt, body.mode, body.authorized_client)


@app.post("/api/attacks/naive")
def attacks_naive():
    return adversarial.run_naive()


@app.get("/api/attacks/audit-log")
def audit_log(limit: int = Query(200, le=1000)):
    rows = db.query("SELECT id, run_id, test_id, category, prompt, mode, passed, explanation, engine, naive, created_at FROM attack_runs ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["passed"] = bool(r["passed"])
    return rows


INJECT_TEXT = ("A mid-sized electric cooperative running the only nuclear-adjacent substation cluster in coastal Andhra Pradesh "
               "met its March 2026 regulator deadline for OT security; the plant director Venkataraman credited testing firewall "
               "rules in monitor-only mode first.")


@app.post("/api/lab/inject-unsafe")
def inject_unsafe():
    """FAULT INJECTION for testing the auditor: writes a leaky lesson into the shared bank, bypassing the verifier."""
    lid = db.new_id("inj")
    db.execute("INSERT INTO lessons(id,text,category,approach,outcome,why,conditions,scale,status,evidence_count,contributions,history,created_at,updated_at,backend) "
               "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (lid, INJECT_TEXT, "cybersecurity", "monitor-mode-first", "worked", "Injected for testing", "OT networks; regulator deadline",
                "Single site", "injected", 1, "[]", db.jdump([{"ts": db.now(), "event": "injected", "detail": "FAULT INJECTION — bypassed the verification gate."}]),
                db.now(), db.now(), current_mode()))
    gateway.retain_batch(PlaybookScope("lab.inject"), playbook_bank(), [{"content": INJECT_TEXT, "context": "FAULT INJECTION (unverified)", "timestamp": db.now()}],
                         document_id=f"{lid}-injected")
    db.log_activity("fault", "Fault injection: an UNVERIFIED leaky lesson was written to the shared bank (testing only)", {"lesson_id": lid})
    db.snapshot_playbook("fault injection")
    return {"injected": lid}


@app.post("/api/lab/clear-injected")
def clear_injected():
    rows = db.query("SELECT id FROM lessons WHERE status='injected'")
    for r in rows:
        try:
            gateway.delete_document(PlaybookScope("lab.clear"), playbook_bank(), f"{r['id']}-injected")
        except Exception:  # noqa: BLE001
            pass
        db.execute("DELETE FROM lessons WHERE id=?", (r["id"],))
    if rows:
        db.log_activity("fault", f"Removed {len(rows)} injected lesson(s) from the shared bank")
        db.snapshot_playbook("fault injection removed")
    return {"removed": len(rows)}


# ----------------------------------------------------------------------------- conflicts
@app.get("/api/conflicts")
def conflicts():
    return pipeline.list_conflicts()


@app.post("/api/conflicts/{cid}/resolve")
def resolve(cid: str):
    return pipeline.resolve_conflict(cid)


# ----------------------------------------------------------------------------- metrics & logs
@app.get("/api/metrics/overview")
def m_overview():
    return metrics.overview()


@app.get("/api/metrics/evolution")
def m_evolution():
    return metrics.evolution()


@app.get("/api/metrics/quality")
def m_quality(live: bool = False):
    q = metrics.quality()
    if live and current_mode() == "live":
        res = advisor.shared_advice(metrics.HELD_OUT_QUESTION, caller="advisor.shared")
        q["live_current"] = {"advice": res["answer"], **metrics.score_advice(res["answer"])}
    return q


@app.get("/api/metrics/comparison")
def m_comparison():
    return metrics.comparison()


@app.get("/api/activity")
def activity(limit: int = Query(40, le=500)):
    rows = db.query("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))
    for r in rows:
        r["meta"] = db.jload(r["meta"], {})
        r["meta"].pop("trace", None)
    return rows


@app.get("/api/access-log")
def access_log(limit: int = Query(100, le=1000)):
    return db.query("SELECT * FROM access_log ORDER BY id DESC LIMIT ?", (limit,))


@app.get("/api/architecture")
def architecture():
    engs = db.query("SELECT id, name, status, bank_id FROM engagements ORDER BY start_date")
    banks = []
    for e in engs:
        n = db.one("SELECT COUNT(*) n FROM notes WHERE engagement_id=?", (e["id"],))["n"]
        wf = db.one("SELECT decision FROM workflows WHERE engagement_id=? AND status='completed' ORDER BY finished_at DESC LIMIT 1", (e["id"],))
        banks.append({**e, "memories": n, "decision": wf and wf["decision"]})
    lessons = pipeline.list_lessons()
    return {
        "client_banks": banks,
        "playbook": {"bank_id": playbook_bank(), "lessons": len(lessons), "evidence": sum(l["evidence_count"] for l in lessons)},
        "verifier": {"bank_id": verifier_bank(), "memories": 0, "note": "Intentionally empty — the verifier never stores anything."},
        "mode": current_mode(),
    }


@app.post("/api/demo/close-all")
def close_all():
    """Close every remaining active engagement sequentially (job). Useful for the 1-vs-N metrics."""
    def run(progress):
        done = []
        for e in db.query("SELECT id, name FROM engagements WHERE status='Active' ORDER BY start_date"):
            progress(f"Closing {e['name']}")
            wid = pipeline.start_close(e["id"], background=False, delay=False)
            done.append({"engagement": e["id"], "workflow": wid, "decision": pipeline.get_workflow(wid)["decision"]})
        for c in pipeline.list_conflicts():
            if c["status"] == "open":
                progress("Reconciling conflict")
                try:
                    pipeline.resolve_conflict(c["id"])
                except Exception as ex:  # noqa: BLE001
                    progress(f"Conflict not reconciled: {ex}")
        return done
    return {"job_id": seed.start_job("close-all", run)}


# ----------------------------------------------------------------------------- static
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/app", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIR / "app.html")

