"""The learning pipeline: Private bank -> Distill (reflect) -> Independent leak check -> Shared playbook.

Confidentiality invariants enforced here (defense in depth, not a guarantee):
  * distillation runs under ClientScope and can only read that client's bank;
  * the verifier receives ONLY the candidate lesson string - never notes, client id or name;
  * UNSAFE lessons are discarded (the candidate text stays in the private workflow record only);
  * only SAFE lessons are retained into firm-playbook, under PlaybookScope;
  * 'unusual' single-engagement lessons are held back until corroborated.
"""
from __future__ import annotations

import hashlib
import threading
import time
import traceback
from datetime import datetime, timezone

from . import db, llm, prompts, redaction, simulator
from .config import settings
from .memory import (ClientScope, PlaybookScope, VerifierScope, client_bank, current_mode, gateway,
                     playbook_bank, verifier_bank)

STAGES = [
    ("recall", "Recall private history", "hindsight.recall on the client's private bank"),
    ("distill", "Distill one lesson", "hindsight.reflect → one generalized lesson"),
    ("verify", "Independent leak check", "re-identification test on the lesson text only"),
    ("corroborate", "Corroboration gate", "unusual lessons need ≥2 unrelated engagements"),
    ("retain", "Retain in shared playbook", "hindsight.retain into firm-playbook"),
    ("conflict", "Conflict scan", "compare with existing shared lessons"),
]


# ----------------------------------------------------------------------------- helpers
def _lesson_row(r: dict) -> dict:
    r = dict(r)
    r["contributions"] = db.jload(r.get("contributions"), [])
    r["history"] = db.jload(r.get("history"), [])
    r["strength"] = simulator.strength_label(r.get("evidence_count") or 1)
    return r


def list_lessons(statuses=("retained", "synthesis", "injected")) -> list[dict]:
    qs = ",".join("?" * len(statuses))
    return [_lesson_row(r) for r in db.query(f"SELECT * FROM lessons WHERE status IN ({qs}) ORDER BY created_at", statuses)]


def get_lesson(lid: str) -> dict | None:
    r = db.one("SELECT * FROM lessons WHERE id=?", (lid,))
    return _lesson_row(r) if r else None


def _period(ts: str | None = None) -> str:
    d = datetime.now(timezone.utc)
    return f"{d.year}-H{1 if d.month <= 6 else 2}"


def _contrib_id(workflow_id: str) -> str:
    return "E-" + hashlib.sha256(workflow_id.encode()).hexdigest()[:6].upper()


def _retain_lesson_to_playbook(lesson: dict, kind: str) -> dict:
    """Retain ONLY generalized text into the shared bank. Never raw notes."""
    content = f"[{kind}] {lesson['text']}"
    if lesson.get("conditions"):
        content += f" Applies when: {lesson['conditions']}"
    return gateway.retain_batch(
        PlaybookScope("pipeline.retain"), playbook_bank(),
        [{"content": content, "context": f"firm playbook lesson · category={lesson.get('category')} · approach={lesson.get('approach')} · outcome={lesson.get('outcome')}",
          "timestamp": db.now(), "metadata": {"lesson_id": lesson["id"], "kind": kind, "category": lesson.get("category") or ""},
          "tags": ["firm-playbook", lesson.get("category") or "other"]}],
        document_id=f"{lesson['id']}-{kind}-{int(time.time() * 1000)}",
    )


# ----------------------------------------------------------------------------- independent verifier
def independent_check(lesson_text: str) -> dict:
    """Receives ONLY the lesson text. Deliberately takes no client id, name or notes."""
    started = time.time()
    layer1 = redaction.screen(lesson_text)
    layer2: dict
    mode = current_mode()
    engine_pref = settings.verifier_engine
    if mode != "live":
        layer2 = {"verdict": "SKIPPED", "engine": "LLM judge (runs when API keys are configured)", "reason": ""}
    else:
        use_groq = engine_pref == "groq" or (engine_pref == "auto" and settings.groq_available)
        prompt = prompts.LEAK_CHECK_PROMPT.format(lesson=lesson_text)
        try:
            if use_groq:
                r = llm.chat([{"role": "user", "content": prompt}], temperature=0, max_tokens=120)
                text, engine = r["text"], f"Groq {r['model']} (no memory access)"
            else:
                r = gateway.reflect(VerifierScope("pipeline.verify"), verifier_bank(), prompt)
                text, engine = r["text"], "hindsight.reflect on empty isolated leak-verifier bank"
            first = text.strip().split("\n", 1)
            word = first[0].strip().upper().strip("*.: ")
            verdict = "SAFE" if word.startswith("SAFE") else "UNSAFE"  # anything unclear => UNSAFE
            layer2 = {"verdict": verdict, "engine": engine, "reason": first[1].strip() if len(first) > 1 else "", "raw": text[:500]}
        except Exception as e:  # noqa: BLE001
            # fail closed: if the independent judge can't run, the lesson is not shared
            layer2 = {"verdict": "UNSAFE", "engine": "LLM judge unavailable — failing closed", "reason": str(e)[:300]}
    final = "SAFE" if layer1["verdict"] == "SAFE" and layer2["verdict"] in ("SAFE", "SKIPPED") else "UNSAFE"
    reasons = [f"{f['why']}: “{f['match']}”" for f in layer1["findings"]]
    if layer2.get("verdict") == "UNSAFE" and layer2.get("reason"):
        reasons.append(f"LLM judge: {layer2['reason']}")
    return {
        "verdict": final,
        "layer1": layer1,
        "layer2": layer2,
        "reasons": reasons,
        "inputs_seen": {"lesson_chars": len(lesson_text), "source_client_identity": "withheld", "raw_notes": "not provided"},
        "elapsed_ms": int((time.time() - started) * 1000),
    }


# ----------------------------------------------------------------------------- distillation
def distill(engagement: dict) -> dict:
    eid = engagement["id"]
    scope = ClientScope(eid, "pipeline.distill")
    if current_mode() == "live":
        r = gateway.reflect(scope, client_bank(eid), prompts.DISTILL_QUERY, response_schema=prompts.DISTILL_SCHEMA)
        data = r.get("structured") or llm.parse_json(r.get("text") or "")
        if not data:
            text = (r.get("text") or "").strip()
            no_safe = "NO SAFE LESSON" in text.upper()
            data = {"no_safe_lesson": no_safe, "lesson": "NO SAFE LESSON" if no_safe else text,
                    "category": simulator.classify_category(text), "approach": "other", "outcome": "mixed",
                    "why": "", "conditions": "", "scale": "", "rarity": "common"}
        data["engine"] = r.get("engine")
        data["based_on"] = r.get("based_on")
        return data
    sim = db.jload(engagement.get("simulation"), None)
    if sim:
        def fake(_recalled):
            return {k: v for k, v in sim.items()}
        r = gateway.reflect(scope, client_bank(eid), prompts.DISTILL_QUERY, simulate=fake)
        r["engine"] = "reflect · distillation"
        r.setdefault("no_safe_lesson", False)
        return r
    notes = db.query("SELECT * FROM notes WHERE engagement_id=? ORDER BY date", (eid,))
    r = gateway.reflect(scope, client_bank(eid), prompts.DISTILL_QUERY, simulate=lambda _r: simulator.template_distill(notes))
    r["engine"] = "reflect · distillation"
    return r


# ----------------------------------------------------------------------------- workflow
def _save(wf: dict) -> None:
    db.execute(
        "UPDATE workflows SET status=?, decision=?, stages=?, candidate=?, verification=?, recall=?, lesson_id=?, finished_at=?, error=? WHERE id=?",
        (wf["status"], wf.get("decision"), db.jdump(wf["stages"]), db.jdump(wf.get("candidate")), db.jdump(wf.get("verification")),
         db.jdump(wf.get("recall")), wf.get("lesson_id"), wf.get("finished_at"), wf.get("error"), wf["id"]),
    )


def get_workflow(wid: str) -> dict | None:
    r = db.one("SELECT w.*, e.name AS client_name FROM workflows w JOIN engagements e ON e.id=w.engagement_id WHERE w.id=?", (wid,))
    if not r:
        return None
    for k in ("stages", "candidate", "verification", "recall"):
        r[k] = db.jload(r[k])
    return r


def start_close(engagement_id: str, *, background: bool = True, delay: bool = True) -> str:
    e = db.one("SELECT * FROM engagements WHERE id=?", (engagement_id,))
    if not e:
        raise ValueError(f"Unknown engagement '{engagement_id}'")
    busy = db.one("SELECT id FROM workflows WHERE engagement_id=? AND status='running'", (engagement_id,))
    if busy:
        return busy["id"]
    if e["status"] == "Closed" and db.one("SELECT id FROM workflows WHERE engagement_id=? AND status='completed'", (engagement_id,)):
        raise ValueError("Engagement is already closed and its learning workflow has completed.")
    wid = db.new_id("wf")
    stages = [{"key": k, "label": l, "detail": d, "status": "pending", "started_at": None, "finished_at": None, "message": ""} for k, l, d in STAGES]
    db.execute("INSERT INTO workflows(id,engagement_id,status,stages,mode,started_at) VALUES(?,?,?,?,?,?)",
               (wid, engagement_id, "running", db.jdump(stages), current_mode(), db.now()))
    db.log_activity("workflow", f"Closing engagement “{e['name']}” — learning pipeline started", {"workflow_id": wid, "engagement_id": engagement_id})
    if background:
        threading.Thread(target=_run, args=(wid, delay), daemon=True).start()
    else:
        _run(wid, delay)
    return wid


def _run(wid: str, delay: bool) -> None:
    wf = get_workflow(wid)
    e = db.one("SELECT * FROM engagements WHERE id=?", (wf["engagement_id"],))
    pause = (settings.demo_stage_delay_ms / 1000.0) if (delay and current_mode() == "demo") else 0

    def stage(key: str, status: str, message: str = "", **extra):
        for s in wf["stages"]:
            if s["key"] == key:
                if status == "running":
                    s["started_at"] = db.now()
                else:
                    s["finished_at"] = db.now()
                    s.setdefault("started_at", s["finished_at"])
                s["status"] = status
                s["message"] = message
                s.update(extra)
        _save(wf)

    def finish(decision: str, skip_from: str | None = None):
        if skip_from:
            hit = False
            for s in wf["stages"]:
                if s["key"] == skip_from:
                    hit = True
                if hit and s["status"] == "pending":
                    s["status"] = "skipped"
        wf["decision"] = decision
        wf["status"] = "completed"
        wf["finished_at"] = db.now()
        _save(wf)
        db.execute("UPDATE engagements SET status='Closed', closed_at=?, end_date=COALESCE(end_date, ?) WHERE id=?",
                   (db.now(), db.now()[:10], e["id"]))
        db.log_activity("decision", f"“{e['name']}” closed → {decision.replace('_', ' ')}", {"workflow_id": wid, "decision": decision})
        db.snapshot_playbook(f"{decision}: workflow {wid}")

    try:
        # 1. recall
        stage("recall", "running"); time.sleep(pause)
        recalled = gateway.recall(ClientScope(e["id"], "pipeline.recall"), client_bank(e["id"]),
                                  "key decisions, setbacks, what approach worked or failed, and the final outcome", limit=8)
        wf["recall"] = recalled
        stage("recall", "done", f"{len(recalled)} private memories recalled from {client_bank(e['id'])}")

        # 2. distill
        stage("distill", "running"); time.sleep(pause)
        cand = distill(e)
        wf["candidate"] = cand
        if cand.get("no_safe_lesson") or (cand.get("lesson") or "").strip().upper() == "NO SAFE LESSON":
            stage("distill", "blocked", "Distiller returned NO SAFE LESSON — nothing crosses the wall.")
            return finish("NO_SAFE_LESSON", "verify")
        use = redaction.usefulness(cand["lesson"])
        if not use["useful"]:
            stage("distill", "blocked", "Lesson too generic after generalization — treated as NO SAFE LESSON (no watered-down lessons).")
            return finish("NO_SAFE_LESSON", "verify")
        stage("distill", "done", f"One generalized lesson produced ({cand.get('category')} · {cand.get('approach')} · {cand.get('outcome')})")

        # 3. independent verification — ONLY the lesson string crosses into this call
        stage("verify", "running"); time.sleep(pause)
        lesson_text: str = str(cand["lesson"])
        ver = independent_check(lesson_text)
        wf["verification"] = ver
        if ver["verdict"] != "SAFE":
            stage("verify", "unsafe", "UNSAFE — lesson discarded entirely. " + "; ".join(ver["reasons"][:3]))
            return finish("DISCARDED", "corroborate")
        stage("verify", "safe", "SAFE — no re-identifying detail found.")

        # 4. corroboration gate for unusual lessons
        stage("corroborate", "running"); time.sleep(pause * 0.6)
        contrib = {"contrib": _contrib_id(wid), "period": _period(), "kind": "origin"}
        if cand.get("rarity") == "unusual":
            held = db.one("SELECT * FROM lessons WHERE status='held' AND category=? ORDER BY created_at LIMIT 1", (cand.get("category"),))
            if not held or held["id"] is None:
                lid = db.new_id("held")
                db.execute(
                    "INSERT INTO lessons(id,text,category,approach,outcome,why,conditions,scale,status,evidence_count,contributions,history,created_at,updated_at,backend) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (lid, lesson_text, cand.get("category"), cand.get("approach"), cand.get("outcome"), cand.get("why"), cand.get("conditions"),
                     cand.get("scale"), "held", 1, db.jdump([contrib]),
                     db.jdump([{"ts": db.now(), "event": "held", "detail": "Unusual single-engagement pattern held back — needs corroboration from a second, unrelated engagement."}]),
                     db.now(), db.now(), "not-shared"))
                wf["lesson_id"] = lid
                stage("corroborate", "held", f"HELD — only one engagement shows this pattern (need ≥{settings.min_corroboration}). Not retained in shared bank.")
                return finish("HELD", "retain")
            # corroborated: promote the held lesson and merge
            db.execute("UPDATE lessons SET status='merged' WHERE id=?", (held["id"],))
            contribs = db.jload(held["contributions"], []) + [dict(contrib, kind="corroboration")]
            stage("corroborate", "done", "Corroborated by a second unrelated engagement — released from hold.")
        else:
            contribs = [contrib]
            stage("corroborate", "done", "Common pattern — no hold required.")

        # 5. retain (reinforce if same category+approach+outcome exists)
        stage("retain", "running"); time.sleep(pause)
        existing = db.one(
            "SELECT * FROM lessons WHERE status='retained' AND category=? AND approach=? AND outcome=? ORDER BY created_at LIMIT 1",
            (cand.get("category"), cand.get("approach"), cand.get("outcome")))
        if existing:
            hist = db.jload(existing["history"], []) + [{"ts": db.now(), "event": "reinforced", "detail": "An independent engagement reached the same generalized conclusion.", "text": lesson_text}]
            cons = db.jload(existing["contributions"], []) + [dict(c, kind="reinforcement") for c in contribs]
            conds = existing["conditions"] or ""
            new_cond = (cand.get("conditions") or "").strip()
            if new_cond and new_cond.lower() not in conds.lower():
                conds = (conds.rstrip(". ") + "; " + new_cond) if conds else new_cond
            db.execute("UPDATE lessons SET evidence_count=evidence_count+?, history=?, contributions=?, conditions=?, updated_at=? WHERE id=?",
                       (len(contribs), db.jdump(hist), db.jdump(cons), conds, db.now(), existing["id"]))
            lesson = get_lesson(existing["id"])
            _retain_lesson_to_playbook({**lesson, "text": lesson_text, "conditions": cand.get("conditions")}, "reinforcement")
            wf["lesson_id"] = existing["id"]
            decision = "REINFORCED"
            stage("retain", "retained", f"RETAINED as reinforcement — evidence now {lesson['evidence_count']} independent engagements.")
        else:
            lid = db.new_id("lsn")
            hist = [{"ts": db.now(), "event": "added", "detail": "Verified SAFE and retained into the shared playbook."}]
            if len(contribs) > 1:
                hist.insert(0, {"ts": db.now(), "event": "corroborated", "detail": "Released from hold after a second unrelated engagement showed the same pattern."})
            db.execute(
                "INSERT INTO lessons(id,text,category,approach,outcome,why,conditions,scale,status,evidence_count,contributions,history,created_at,updated_at,backend) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (lid, lesson_text, cand.get("category"), cand.get("approach"), cand.get("outcome"), cand.get("why"), cand.get("conditions"),
                 cand.get("scale"), "retained", len(contribs), db.jdump(contribs), db.jdump(hist), db.now(), db.now(), current_mode()))
            lesson = get_lesson(lid)
            _retain_lesson_to_playbook(lesson, "lesson")
            wf["lesson_id"] = lid
            decision = "RETAINED"
            stage("retain", "retained", f"RETAINED in {playbook_bank()} — new lesson.")

        # 6. conflict scan
        stage("conflict", "running"); time.sleep(pause * 0.6)
        found = detect_conflicts(lesson["id"])
        stage("conflict", "conflict" if found else "done",
              f"Contradiction detected with {len(found['lesson_ids']) - 1} existing lesson(s) — open in Conflict Resolution." if found else "No contradictions with existing shared lessons.")
        finish(decision)
    except Exception as ex:  # noqa: BLE001
        wf["status"] = "failed"
        wf["decision"] = "ERROR"
        wf["error"] = f"{type(ex).__name__}: {ex}"
        wf["finished_at"] = db.now()
        for s in wf["stages"]:
            if s["status"] == "running":
                s["status"] = "error"
                s["message"] = wf["error"]
        _save(wf)
        db.log_activity("error", f"Pipeline error for “{e['name']}”: {ex}", {"trace": traceback.format_exc()[-1500:]})


# ----------------------------------------------------------------------------- conflicts
def detect_conflicts(lesson_id: str) -> dict | None:
    l = get_lesson(lesson_id)
    if not l:
        return None
    others = db.query("SELECT * FROM lessons WHERE status='retained' AND category=? AND approach=? AND outcome<>? AND id<>?",
                      (l["category"], l["approach"], l["outcome"], l["id"]))
    if not others:
        return None
    ids = sorted({l["id"], *[o["id"] for o in others]})
    for c in db.query("SELECT * FROM conflicts WHERE category=? AND approach=?", (l["category"], l["approach"])):
        if sorted(db.jload(c["lesson_ids"], [])) == ids:
            return None
    cid = db.new_id("cfl")
    db.execute("INSERT INTO conflicts(id,category,approach,lesson_ids,status,created_at) VALUES(?,?,?,?,?,?)",
               (cid, l["category"], l["approach"], db.jdump(ids), "open", db.now()))
    for i in ids:
        db.execute("UPDATE lessons SET conflict_id=? WHERE id=?", (cid, i))
        lx = get_lesson(i)
        hist = lx["history"] + [{"ts": db.now(), "event": "contradicted", "detail": f"Contradicting evidence detected on '{l['approach']}' — conflict {cid} opened."}]
        db.execute("UPDATE lessons SET history=? WHERE id=?", (db.jdump(hist), i))
    db.log_activity("conflict", f"Contradiction detected in {l['category']} on approach '{l['approach']}'", {"conflict_id": cid})
    return {"id": cid, "lesson_ids": ids}


def list_conflicts() -> list[dict]:
    out = []
    for c in db.query("SELECT * FROM conflicts ORDER BY created_at DESC"):
        c["lesson_ids"] = db.jload(c["lesson_ids"], [])
        c["lessons"] = [get_lesson(i) for i in c["lesson_ids"]]
        c["synthesis"] = get_lesson(c["synthesis_lesson_id"]) if c.get("synthesis_lesson_id") else None
        out.append(c)
    return out


def resolve_conflict(cid: str) -> dict:
    c = db.one("SELECT * FROM conflicts WHERE id=?", (cid,))
    if not c:
        raise ValueError("Unknown conflict")
    if c["status"] == "resolved":
        return next(x for x in list_conflicts() if x["id"] == cid)
    lessons = [get_lesson(i) for i in db.jload(c["lesson_ids"], [])]
    # attach alternative approach hints from the (already generalized) candidate records if present
    for l in lessons:
        wf = db.one("SELECT candidate FROM workflows WHERE lesson_id=?", (l["id"],))
        cand = db.jload(wf["candidate"], {}) if wf else {}
        if cand.get("alternative_approach"):
            l["alternative_approach"] = cand["alternative_approach"]
    listing = "\n".join(f"{i + 1}. [{l['outcome'].upper()}] {l['text']} (Applies when: {l.get('conditions') or 'n/a'}; evidence: {l['evidence_count']} engagement(s))"
                        for i, l in enumerate(lessons))
    query = prompts.CONFLICT_QUERY.format(category=c["category"], approach=c["approach"], lessons=listing)
    if current_mode() == "live":
        r = gateway.reflect(PlaybookScope("conflict.reflect"), playbook_bank(), query, response_schema=prompts.CONFLICT_SCHEMA)
        text = ((r.get("structured") or {}).get("synthesis") or r.get("text") or "").strip()
        engine = "reflect · conditional synthesis"
    else:
        text = simulator.synthesize_conflict(c["category"], c["approach"], lessons)
        engine = "reflect · conditional synthesis"
    ver = independent_check(text)
    if ver["verdict"] != "SAFE":
        db.log_activity("conflict", f"Synthesis for {cid} failed the leak check and was discarded", {"reasons": ver["reasons"]})
        raise ValueError("Synthesis failed the independent leak check and was discarded: " + "; ".join(ver["reasons"][:3]))
    lid = db.new_id("syn")
    ev = sum(l["evidence_count"] for l in lessons)
    contribs = [{"contrib": x["contrib"], "period": x["period"], "kind": "evidence"} for l in lessons for x in l["contributions"]]
    hist = [{"ts": db.now(), "event": "revised", "detail": f"Conditional synthesis produced from {len(lessons)} contradicting lessons ({ev} engagements). Original evidence preserved."}]
    db.execute(
        "INSERT INTO lessons(id,text,category,approach,outcome,why,conditions,scale,status,evidence_count,contributions,history,created_at,updated_at,backend,conflict_id) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (lid, text, c["category"], c["approach"], "conditional", "Evidence supports different approaches under different conditions.",
         "; ".join(sorted({l.get('conditions') or '' for l in lessons if l.get('conditions')})), "Varies", "synthesis", ev,
         db.jdump(contribs), db.jdump(hist), db.now(), db.now(), current_mode(), cid))
    _retain_lesson_to_playbook(get_lesson(lid), "synthesis")
    for l in lessons:
        h = l["history"] + [{"ts": db.now(), "event": "revised", "detail": "Superseded as guidance by a conditional synthesis; kept as evidence."}]
        db.execute("UPDATE lessons SET history=? WHERE id=?", (db.jdump(h), l["id"]))
    db.execute("UPDATE conflicts SET status='resolved', synthesis_lesson_id=?, synthesis_text=?, engine=?, resolved_at=? WHERE id=?",
               (lid, text, engine, db.now(), cid))
    db.log_activity("conflict", f"Conflict {cid} reconciled into conditional guidance", {"synthesis_id": lid})
    db.snapshot_playbook(f"SYNTHESIS: conflict {cid}")
    return next(x for x in list_conflicts() if x["id"] == cid)
