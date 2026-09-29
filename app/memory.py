"""Memory layer.

Every memory operation goes through `MemoryGateway`, which enforces a *scope*:

* ``ClientScope(client_id)``  -> may only touch that client's private bank
* ``PlaybookScope``           -> may only touch the shared ``firm-playbook`` bank
* ``VerifierScope``           -> may only touch the empty, isolated ``leak-verifier`` bank
* ``AdminScope``              -> bank lifecycle only (create / delete) during seed & reset

Every call (allowed or refused) is written to ``access_log`` so the confidentiality audit
can *count* how many private-bank reads happened during shared-playbook queries.

Two interchangeable backends:

* ``HindsightBackend``  - LIVE MODE, the real ``hindsight-client`` SDK (retain / recall / reflect).
* ``SimulatedBackend``  - DEMO MODE, a transparent local keyword store in SQLite. It is *not*
  Hindsight and the UI labels it as a simulation.
"""
from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from . import db
from .config import settings


# --------------------------------------------------------------------------- bank ids
def client_bank(client_id: str) -> str:
    return f"{settings.bank_prefix}client-{client_id}"


def playbook_bank() -> str:
    return f"{settings.bank_prefix}firm-playbook"


def verifier_bank() -> str:
    return f"{settings.bank_prefix}leak-verifier"


# --------------------------------------------------------------------------- scopes
class ScopeViolation(PermissionError):
    pass


@dataclass(frozen=True)
class Scope:
    kind: str  # client | playbook | verifier | admin
    client_id: str | None = None
    caller: str = ""

    def allowed_bank(self) -> str | None:
        if self.kind == "client" and self.client_id:
            return client_bank(self.client_id)
        if self.kind == "playbook":
            return playbook_bank()
        if self.kind == "verifier":
            return verifier_bank()
        return None

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.client_id}" if self.client_id else self.kind


def ClientScope(client_id: str, caller: str = "") -> Scope:  # noqa: N802
    return Scope("client", client_id, caller)


def PlaybookScope(caller: str = "") -> Scope:  # noqa: N802
    return Scope("playbook", None, caller)


def VerifierScope(caller: str = "") -> Scope:  # noqa: N802
    return Scope("verifier", None, caller)


def AdminScope(caller: str = "") -> Scope:  # noqa: N802
    return Scope("admin", None, caller)


# --------------------------------------------------------------------------- mode
def current_mode() -> str:
    """Returns 'live' or 'demo'."""
    requested = (db.kv_get("mode_override") or settings.app_mode or "auto").lower()
    if requested == "demo":
        return "demo"
    if requested in ("live", "auto"):
        return "live" if settings.live_available else "demo"
    return "demo"


def mode_info() -> dict:
    mode = current_mode()
    requested = (db.kv_get("mode_override") or settings.app_mode or "auto").lower()
    return {
        "mode": mode,
        "requested": requested,
        "hindsight_configured": settings.live_available,
        "groq_configured": settings.groq_available,
        "hindsight_base_url": settings.hindsight_base_url if settings.live_available else None,
        "llm_primary": settings.llm_primary,
        "llm_fallback": settings.llm_fallback,
        "memory_engine": "Hindsight Cloud (hindsight-client SDK)" if mode == "live" else "Local simulated memory store (NOT Hindsight)",
        "notes": (
            "LIVE MODE: memory operations call the real Hindsight SDK."
            if mode == "live"
            else "DEMO MODE: deterministic local simulation. Distillation text is pre-authored per engagement; "
            "recall, leak screening, conflict detection, advice and attack auditing run locally. "
            "No operation in this mode is performed by Hindsight or a real LLM."
        ),
        "warning": (
            "APP_MODE=live requested but HINDSIGHT_API_KEY is not set — falling back to DEMO MODE."
            if requested == "live" and not settings.live_available
            else None
        ),
    }


# --------------------------------------------------------------------------- backends
_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = set(
    "the a an and or of to in on for with by at from as is was were be been are it its this that these those "
    "we our you your they their i me my he she his her them what which who whom how when where why do does did "
    "can could should would will just about into than then so if not no".split()
)


def _stem(t: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(t) > len(suf) + 3 and t.endswith(suf):
            return t[: -len(suf)]
    return t


def _tokens(text: str) -> list[str]:
    return [_stem(t) for t in _TOKEN.findall((text or "").lower()) if t not in _STOP and len(t) > 1]


# tiny query expansion so the keyword simulation behaves a little more like semantic recall
_SYNONYMS = {
    "wrong": "fail problem broke mismatch escalat rollback blam",
    "fail": "wrong problem broke abandon mismatch",
    "work": "succeed success live complete recover",
    "final": "outcome close complete succeed",
    "outcome": "result complete succeed live close",
    "decision": "agree decid plan recommend approv re-plann",
    "problem": "issue fail mismatch risk",
    "cost": "budget $ overran",
    "budget": "cost $",
}


def _expand(tokens: list[str]) -> list[str]:
    out = list(tokens)
    for t in tokens:
        for k, v in _SYNONYMS.items():
            if t.startswith(k):
                out += [_stem(x) for x in v.split()]
    return out


class SimulatedBackend:
    name = "simulated"

    def create_bank(self, bank_id: str, name: str = "", mission: str = "") -> dict:
        return {"bank_id": bank_id, "simulated": True}

    def delete_bank(self, bank_id: str) -> None:
        db.execute("DELETE FROM sim_memories WHERE bank_id=?", (bank_id,))

    def retain_batch(self, bank_id: str, items: list[dict], document_id: str | None = None) -> dict:
        for it in items:
            meta = dict(it.get("metadata") or {})
            if document_id:
                meta["document_id"] = document_id
            db.execute(
                "INSERT INTO sim_memories(bank_id,content,context,timestamp,meta,created_at) VALUES(?,?,?,?,?,?)",
                (bank_id, it["content"], it.get("context"), str(it.get("timestamp") or ""), db.jdump(meta), db.now()),
            )
        return {"success": True, "items_count": len(items), "bank_id": bank_id}

    def delete_document(self, bank_id: str, document_id: str) -> None:
        # plain-Python filter (no dependency on SQLite's JSON1 extension, which older builds may lack)
        for r in db.query("SELECT id, meta FROM sim_memories WHERE bank_id=?", (bank_id,)):
            if (db.jload(r["meta"], {}) or {}).get("document_id") == document_id:
                db.execute("DELETE FROM sim_memories WHERE id=?", (r["id"],))

    def list_memories(self, bank_id: str) -> list[dict]:
        rows = db.query("SELECT * FROM sim_memories WHERE bank_id=? ORDER BY id", (bank_id,))
        return [{"id": str(r["id"]), "text": r["content"], "context": r["context"], "timestamp": r["timestamp"]} for r in rows]

    def recall(self, bank_id: str, query: str, limit: int = 8) -> list[dict]:
        rows = self.list_memories(bank_id)
        if not rows:
            return []
        q = Counter(_expand(_tokens(query)))
        docs = [Counter(_tokens(r["text"] + " " + (r["context"] or ""))) for r in rows]
        n = len(docs)
        df = Counter(t for d in docs for t in d)
        scored = []
        for r, d in zip(rows, docs):
            s = 0.0
            for t in q:
                if t in d or any(dt.startswith(t) for dt in d if len(t) >= 4):
                    if t not in d:
                        d = d.copy(); d[t] = 1
                    idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                    s += idf * (d[t] * 2.2) / (d[t] + 1.2)
            scored.append((s, r))
        scored.sort(key=lambda x: -x[0])
        out = [dict(r, score=round(s, 3)) for s, r in scored if s > 0][:limit]
        if len(out) < max(1, limit // 2):
            # keyword recall is sparse: pad with the bank's remaining memories (chronological) so a broad
            # "summarize this engagement" recall still sees the whole trail. Padded items carry score 0.
            seen = {m["id"] for m in out}
            out += [dict(r, score=0.0) for r in rows if r["id"] not in seen][: limit - len(out)]
        return out

    def reflect(self, bank_id: str, query: str, context: str | None = None, response_schema: dict | None = None,
                simulate: Callable[[list[dict]], dict] | None = None) -> dict:
        recalled = self.recall(bank_id, query + " " + (context or ""), limit=10)
        if simulate is None:
            raise RuntimeError("Simulated reflect requires a deterministic simulate() callback")
        res = simulate(recalled)
        res.setdefault("based_on", [m["id"] for m in recalled])
        res["engine"] = "reflect"
        return res


class HindsightBackend:
    name = "hindsight"

    def __init__(self) -> None:
        from hindsight_client import Hindsight  # imported lazily so DEMO MODE never needs it

        from concurrent.futures import ThreadPoolExecutor

        # The SDK's sync wrappers drive an asyncio loop per thread. Pinning every call to ONE dedicated worker
        # thread keeps a single, persistent event loop (and HTTP session) no matter which request thread calls us.
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hindsight")
        self._client = self._pool.submit(
            lambda: Hindsight(base_url=settings.hindsight_base_url, api_key=settings.hindsight_api_key, timeout=180.0)
        ).result()

    def _call(self, fn, *args, **kwargs):
        return self._pool.submit(fn, *args, **kwargs).result()

    def _run(self, coro_factory):
        import asyncio

        def runner():
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            return loop.run_until_complete(coro_factory())

        return self._pool.submit(runner).result()

    def create_bank(self, bank_id: str, name: str = "", mission: str = "") -> dict:
        r = self._call(self._client.create_bank, bank_id=bank_id, name=name or bank_id, mission=mission or None)
        return {"bank_id": bank_id, "response": _to_dict(r)}

    def delete_bank(self, bank_id: str) -> None:
        try:
            self._call(self._client.delete_bank, bank_id)
        except Exception as e:  # bank may not exist yet
            if "404" not in str(e):
                raise

    def retain_batch(self, bank_id: str, items: list[dict], document_id: str | None = None) -> dict:
        payload = []
        for it in items:
            ts = it.get("timestamp")
            if isinstance(ts, str) and ts:
                try:
                    ts = datetime.fromisoformat(ts)
                except ValueError:
                    ts = None
            payload.append({
                "content": it["content"],
                "context": it.get("context"),
                "timestamp": ts,
                "metadata": {k: str(v) for k, v in (it.get("metadata") or {}).items()},
                "tags": it.get("tags"),
            })
        r = self._call(self._client.retain_batch, bank_id=bank_id, items=payload, document_id=document_id,
                       retain_async=settings.hindsight_retain_async)
        return _to_dict(r)

    def delete_document(self, bank_id: str, document_id: str) -> None:
        self._run(lambda: self._client.documents.delete_document(bank_id, document_id))

    def list_memories(self, bank_id: str) -> list[dict]:
        r = self._call(self._client.list_memories, bank_id=bank_id, limit=200)
        items = getattr(r, "items", None) or []
        return [{"id": str(getattr(m, "id", "")), "text": getattr(m, "text", str(m)), "context": getattr(m, "context", None)} for m in items]

    def recall(self, bank_id: str, query: str, limit: int = 8) -> list[dict]:
        r = self._call(self._client.recall, bank_id=bank_id, query=query, budget="mid", max_tokens=4096)
        out = []
        for m in (r.results or [])[:limit]:
            out.append({
                "id": m.id, "text": m.text, "context": m.context, "type": m.type,
                "timestamp": m.occurred_start or m.mentioned_at,
            })
        return out

    def reflect(self, bank_id: str, query: str, context: str | None = None, response_schema: dict | None = None,
                simulate: Callable | None = None) -> dict:
        r = self._call(self._client.reflect, bank_id=bank_id, query=query, context=context,
                       response_schema=response_schema, budget="mid")
        based = getattr(r, "based_on", None)
        return {
            "text": r.text,
            "structured": getattr(r, "structured_output", None),
            "structured_error": getattr(r, "structured_output_error", None),
            "based_on": _to_dict(based) if based is not None else None,
            "engine": "reflect",
        }


def _to_dict(obj: Any) -> Any:
    for attr in ("to_dict", "model_dump"):
        f = getattr(obj, attr, None)
        if callable(f):
            try:
                return f()
            except Exception:
                pass
    return str(obj)


_backends: dict[str, Any] = {}


def backend() -> Any:
    mode = current_mode()
    if mode not in _backends:
        _backends[mode] = HindsightBackend() if mode == "live" else SimulatedBackend()
    return _backends[mode]


# --------------------------------------------------------------------------- gateway
class MemoryGateway:
    """The ONLY path to memory. Enforces bank scope and writes the access log."""

    def _check(self, scope: Scope, bank_id: str, op: str) -> Any:
        b = backend()
        allowed = scope.kind == "admin" and op in ("create_bank", "delete_bank")
        if not allowed:
            allowed = scope.allowed_bank() == bank_id
        db.execute(
            "INSERT INTO access_log(ts,scope,bank_id,operation,caller,allowed,backend) VALUES(?,?,?,?,?,?,?)",
            (db.now(), scope.label, bank_id, op, scope.caller, 1 if allowed else 0, b.name),
        )
        if not allowed:
            raise ScopeViolation(f"Scope '{scope.label}' is not authorized to {op} on bank '{bank_id}'.")
        return b

    def create_bank(self, scope: Scope, bank_id: str, name: str = "", mission: str = "") -> dict:
        return self._check(scope, bank_id, "create_bank").create_bank(bank_id, name, mission)

    def delete_bank(self, scope: Scope, bank_id: str) -> None:
        self._check(scope, bank_id, "delete_bank").delete_bank(bank_id)

    def retain_batch(self, scope: Scope, bank_id: str, items: list[dict], document_id: str | None = None) -> dict:
        return self._check(scope, bank_id, "retain").retain_batch(bank_id, items, document_id)

    def delete_document(self, scope: Scope, bank_id: str, document_id: str) -> None:
        self._check(scope, bank_id, "delete_document").delete_document(bank_id, document_id)

    def recall(self, scope: Scope, bank_id: str, query: str, limit: int = 8) -> list[dict]:
        return self._check(scope, bank_id, "recall").recall(bank_id, query, limit)

    def list_memories(self, scope: Scope, bank_id: str) -> list[dict]:
        return self._check(scope, bank_id, "list").list_memories(bank_id)

    def reflect(self, scope: Scope, bank_id: str, query: str, context: str | None = None,
                response_schema: dict | None = None, simulate: Callable | None = None) -> dict:
        return self._check(scope, bank_id, "reflect").reflect(bank_id, query, context, response_schema, simulate)


gateway = MemoryGateway()
