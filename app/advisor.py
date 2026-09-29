"""AI consultant: shared-playbook advice for new clients + authorized private-bank queries."""
from __future__ import annotations

import re

from . import db, pipeline, prompts, redaction, simulator
from .memory import (ClientScope, PlaybookScope, ScopeViolation, client_bank, current_mode, gateway, playbook_bank)

HIGH_RISK = {"exact-figure", "exact-date", "direct-quote", "location", "contact"}


def _output_filter(text: str) -> tuple[str, list[dict]]:
    """Defense-in-depth output filter for shared answers: redact high-risk spans the playbook should never contain."""
    findings = [f for f in redaction.screen(text)["findings"] if f["type"] in HIGH_RISK]
    out = text
    for f in findings:
        out = out.replace(f["match"], "[redacted]")
    return out, findings


def shared_advice(question: str, *, client: dict | None = None, history: list[dict] | None = None, caller: str = "advisor.shared") -> dict:
    question = (question or "").strip()
    if not question:
        raise ValueError("Question is empty")
    intents = simulator.extraction_intent(question)
    scope = PlaybookScope(caller)
    # the question for ranking includes the previous user turn so follow-ups keep context
    prev = " ".join(m["content"] for m in (history or [])[-2:] if m["role"] == "user")
    rank_q = f"{question} {prev} {(client or {}).get('challenge', '')}"
    recalled = gateway.recall(scope, playbook_bank(), rank_q, limit=8)
    lessons = pipeline.list_lessons()
    engine = ""
    if current_mode() == "live":
        ctx = prompts.ADVISOR_CONTEXT
        if client:
            ctx += f"\nNew client context: {client.get('sector')} — {client.get('challenge')}"
        if history:
            ctx += "\nConversation so far:\n" + "\n".join(f"{m['role']}: {m['content'][:400]}" for m in history[-4:])
        r = gateway.reflect(scope, playbook_bank(), question, context=ctx)
        text = r["text"]
        engine = "shared-playbook advisor"
        used = [l for _, l in simulator.rank_lessons(rank_q, lessons)]
    else:
        comp = simulator.compose_advice(rank_q, lessons, intents)
        text, used = comp["text"], comp["used"]
        engine = "shared-playbook advisor"
    text, filtered = _output_filter(text)
    return {
        "answer": text,
        "sources": [{"id": l["id"], "text": l["text"], "category": l["category"], "approach": l["approach"], "outcome": l["outcome"],
                     "evidence_count": l["evidence_count"], "strength": l["strength"], "status": l["status"]} for l in used],
        "recalled": [{"id": m["id"], "text": m["text"]} for m in recalled],
        "memory_source": "Shared Playbook Only",
        "banks_accessed": [playbook_bank()],
        "extraction_intent": intents,
        "output_filter": filtered,
        "engine": engine,
        "playbook_size": len(lessons),
    }


def private_query(client_id: str, question: str, *, attempted_bank: str | None = None, caller: str = "advisor.private") -> dict:
    e = db.one("SELECT * FROM engagements WHERE id=?", (client_id,))
    if not e:
        raise ValueError("Unknown client")
    scope = ClientScope(client_id, caller)
    refused = None
    if attempted_bank and attempted_bank != client_bank(client_id):
        try:
            gateway.recall(scope, attempted_bank, question)
        except ScopeViolation:
            # don't echo the target bank id back — it contains the other client's slug
            refused = "a request for another client's bank was refused by the scope gateway and logged"
    recalled = gateway.recall(scope, client_bank(client_id), question, limit=6)
    if current_mode() == "live":
        r = gateway.reflect(scope, client_bank(client_id), question, context=prompts.PRIVATE_CONTEXT + f" Client: {e['name']}.")
        text, engine = r["text"], "private-bank recall"
    else:
        text = simulator.private_answer(question, recalled, e["name"])
        engine = "private-bank recall"
    other_names = [r["name"] for r in db.query("SELECT name FROM engagements WHERE id<>?", (client_id,))]
    mentions_other = [n for n in other_names if re.search(re.escape(n.split()[0]), question, re.I)]
    if mentions_other or refused:
        text = ("**Scope notice:** this session is authorized only for "
                f"**{e['name']}**'s private bank. Other clients' banks are unreachable from this scope"
                + (f" ({refused})" if refused else "") + ".\n\n" + text)
    return {
        "answer": text,
        "recalled": recalled,
        "memory_source": f"Private bank: {e['name']} (authorized)",
        "banks_accessed": [client_bank(client_id)],
        "refused_access": refused,
        "engine": engine,
    }


def chat(session_id: str, message: str, mode: str, client_id: str | None, new_client: dict | None) -> dict:
    history = [dict(r) for r in db.query("SELECT role, content FROM chat_messages WHERE session_id=? ORDER BY id", (session_id,))]
    if mode == "private":
        if not client_id:
            raise ValueError("Private mode requires an authorized client")
        res = private_query(client_id, message)
    else:
        res = shared_advice(message, client=new_client, history=history)
    db.execute("INSERT INTO chat_messages(session_id,role,content,mode,client_id,sources,engine,ts) VALUES(?,?,?,?,?,?,?,?)",
               (session_id, "user", message, mode, client_id or (new_client or {}).get("id"), None, None, db.now()))
    db.execute("INSERT INTO chat_messages(session_id,role,content,mode,client_id,sources,engine,ts) VALUES(?,?,?,?,?,?,?,?)",
               (session_id, "assistant", res["answer"], mode, client_id or (new_client or {}).get("id"), db.jdump(res.get("sources", [])), res["engine"], db.now()))
    return res
