"""Reset + seed synthetic engagements into isolated per-client banks."""
from __future__ import annotations

import glob
import json
import os
import threading
import traceback

from . import db, pipeline
from .config import DATA_DIR
from .memory import (AdminScope, ClientScope, client_bank, current_mode, gateway, playbook_bank, verifier_bank)

JOBS: dict[str, dict] = {}


def load_client_files() -> list[dict]:
    out = []
    for f in sorted(glob.glob(os.path.join(DATA_DIR, "clients", "*.json"))):
        with open(f, encoding="utf-8") as fh:
            out.append(json.load(fh))
    return out


def _known_bank_ids() -> list[str]:
    ids = {r["bank_id"] for r in db.query("SELECT bank_id FROM engagements")}
    ids |= {client_bank(c["id"]) for c in load_client_files()}
    ids |= {playbook_bank(), verifier_bank()}
    return sorted(ids)


def insert_engagement(c: dict, source: str = "seed") -> None:
    db.execute(
        "INSERT INTO engagements(id,name,engagement_type,industry,region,size,status,start_date,end_date,partner,client_team,"
        "contract_value,sensitive_terms,simulation,bank_id,source,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (c["id"], c["name"], c.get("engagement_type"), c.get("industry"), c.get("region"), c.get("size"), "Active",
         c.get("start_date"), None, c.get("partner"), db.jdump(c.get("client_team") or []), c.get("contract_value"),
         db.jdump(c.get("sensitive_terms") or []), db.jdump(c.get("simulation")) if c.get("simulation") else None,
         client_bank(c["id"]), source, db.now()),
    )


def retain_notes(client_id: str, client_name: str, notes: list[dict]) -> dict:
    items = [{
        "content": n["text"],
        "context": f"Private engagement note for {client_name} by {n.get('author', 'consultant')}",
        "timestamp": (n.get("date") or "") + "T09:00:00" if n.get("date") else None,
        "metadata": {"author": n.get("author", ""), "client": client_id},
    } for n in notes]
    res = gateway.retain_batch(ClientScope(client_id, "seed.retain"), client_bank(client_id), items)
    for n in notes:
        db.execute("INSERT INTO notes(engagement_id,date,author,text,retained_backend,created_at) VALUES(?,?,?,?,?,?)",
                   (client_id, n.get("date"), n.get("author"), n["text"], current_mode(), db.now()))
    return res


def reset_and_seed(progress=None) -> dict:
    def p(msg):
        if progress:
            progress(msg)

    admin = AdminScope("seed.reset")
    p("Deleting existing banks")
    for b in _known_bank_ids():
        try:
            gateway.delete_bank(admin, b)
        except Exception:  # noqa: BLE001
            pass
    db.reset_all()
    clients = load_client_files()
    gateway.create_bank(admin, playbook_bank(), "Firm playbook (shared)",
                        "Shared firm playbook. Holds ONLY generalized, independently verified lessons. Never raw client data.")
    gateway.create_bank(admin, verifier_bank(), "Leak verifier (isolated, intentionally empty)",
                        "Independent re-identification checker. Nothing is ever retained here.")
    for c in clients:
        p(f"Creating private bank for {c['name']}")
        gateway.create_bank(admin, client_bank(c["id"]), f"Private: {c['name']}",
                            f"Private memory for a single consulting engagement ({c['engagement_type']}). Never shared.")
        insert_engagement(c)
        retain_notes(c["id"], c["name"], c["notes"])
        db.log_activity("retain", f"Retained {len(c['notes'])} raw notes into private bank {client_bank(c['id'])}", {"engagement_id": c["id"]})
    db.snapshot_playbook("seed: empty playbook")
    for c in clients:
        if c.get("seed_closed"):
            p(f"Closing {c['name']} through the full pipeline")
            pipeline.start_close(c["id"], background=False, delay=False)
    db.log_activity("seed", f"Seeded {len(clients)} synthetic engagements")
    return {"engagements": len(clients), "mode": current_mode()}


def start_job(kind: str, fn) -> str:
    jid = db.new_id("job")
    JOBS[jid] = {"id": jid, "kind": kind, "status": "running", "log": [], "result": None, "error": None, "started_at": db.now()}

    def run():
        try:
            JOBS[jid]["result"] = fn(lambda m: JOBS[jid]["log"].append({"ts": db.now(), "msg": m}))
            JOBS[jid]["status"] = "done"
        except Exception as e:  # noqa: BLE001
            JOBS[jid]["status"] = "failed"
            JOBS[jid]["error"] = f"{type(e).__name__}: {e}"
            JOBS[jid]["trace"] = traceback.format_exc()[-2000:]
        JOBS[jid]["finished_at"] = db.now()

    threading.Thread(target=run, daemon=True).start()
    return jid
