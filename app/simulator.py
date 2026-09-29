"""DEMO MODE deterministic simulation (NOT an LLM, NOT Hindsight).

Everything here is transparent, rule-based logic so the full UI works without credentials. The UI labels every
result produced here as simulated.
"""
from __future__ import annotations

import re
from collections import Counter

from .memory import _tokens

CATEGORY_KEYWORDS = {
    "systems-migration": "migration migrate migrating cutover rollout legacy replace replacing system platform erp ehr wms core go-live integration integrations interfaces dispatch consolidat cloud mainframe",
    "pricing-strategy": "pricing price loyalty membership subscription discount tier tiered member promotion",
    "vendor-selection": "vendor saas package packaged customization customize configure platform selection rfp implementation upgrade",
    "cybersecurity": "security cyber ot network segmentation firewall threat breach",
    "public-procurement": "procurement bid protest tender award evaluator public agency",
    "change-management": "adoption champions training resistance change morale",
    "org-dynamics": "conflict dispute leadership board mediation",
}
APPROACH_KEYWORDS = [
    ("rehearsed-single-cutover", r"single[- ]weekend|dress rehearsal|single cutover|one cutover"),
    ("phased-rollout", r"phased|wave|pilot site|site-by-site|facility-by-facility|product line|module-by-module|dept-by-dept"),
    ("controlled-pilot", r"test regions?|control regions?|a/b|pilot|kill metric"),
    ("heavy-customization", r"custom code|customi[sz]"),
    ("monitor-mode-first", r"monitor-only|monitor mode"),
    ("documented-evaluation", r"written justification|score sheets|rationale"),
]
FAIL_WORDS = r"\b(fail|failed|failing|broke|broken|backfire|abandon|abandoned|not working|mismatch|two sources of truth)\b"
WIN_WORDS = r"\b(worked|succeeded|success|live|complete|recovered|satisfied|on time|ahead of)\b"


def classify_category(text: str) -> str:
    toks = set(_tokens(text))
    best, score = "other", 0
    for cat, kw in CATEGORY_KEYWORDS.items():
        s = sum(1 for k in kw.split() if any(t.startswith(k) for t in toks))
        if s > score:
            best, score = cat, s
    return best


def template_distill(notes: list[dict]) -> dict:
    """Generic, template-based distiller for user-created engagements in DEMO MODE."""
    blob = " ".join(n["text"] for n in notes)
    low = blob.lower()
    approach = next((a for a, pat in APPROACH_KEYWORDS if re.search(pat, low)), None)
    category = classify_category(blob)
    fails = len(re.findall(FAIL_WORDS, low))
    wins = len(re.findall(WIN_WORDS, low))
    if not approach or category in ("other", "org-dynamics"):
        return {"no_safe_lesson": True, "lesson": "NO SAFE LESSON", "category": category, "approach": approach or "other",
                "outcome": "mixed", "why": "The template distiller found no generalizable approach/outcome pattern in these notes.",
                "conditions": "", "scale": "", "rarity": "common"}
    outcome = "worked" if wins >= fails else "failed"
    human = approach.replace("-", " ")
    cat_h = category.replace("-", " ")
    verb = "tended to work" if outcome == "worked" else "tended to fail"
    lesson = (f"In a {cat_h} engagement, a {human} approach {verb}, because the team's notes tie the outcome to how "
              f"early risks and dependencies were surfaced; consultants should validate whether the same conditions hold "
              f"before reusing this approach.")
    return {"no_safe_lesson": False, "lesson": lesson, "category": category, "approach": approach, "outcome": outcome,
            "why": "Derived from the engagement notes.", "conditions": "Similar engagement type.",
            "scale": "Unspecified", "rarity": "common"}


# ----------------------------------------------------------------------------- extraction intent guard
EXTRACTION_PATTERNS = [
    (r"\b(which|what|who|name)\b.{0,40}\b(client|company|companies|bank|hospital|firm|insurer|utility|organi[sz]ation|retailer)s?\b", "asks to identify a client"),
    (r"\bwho (was|is|were)\b", "asks to identify a person or organization"),
    (r"\b(real|actual|exact)\b.{0,30}\b(example|numbers?|figures?|amounts?|budget|dates?|names?)\b", "asks for real specifics"),
    (r"\b(budget|contract value|cost|price|how much|dollars?|\$)\b", "asks for exact figures"),
    (r"\b(exact date|what date|when exactly|on what (exact )?date|deadline|which year)\b", "asks for exact dates"),
    (r"\b(quote|verbatim|exactly what .* said)\b", "asks for direct quotes"),
    (r"\b(ignore|bypass|disable|override)\b.{0,40}\b(anonymi[sz]ation|rules?|policy|confidentiality|instructions?|module)\b", "attempts to override confidentiality"),
    (r"\b(i'?m|i am|as)\b.{0,20}\b(the client|managing partner|partner|admin|auditor|ceo)\b", "claims special authorization"),
    (r"\b(urgent|asap|no time|emergency)\b", "applies urgency pressure"),
    (r"\b(raw|unfiltered|original)\b.{0,30}\b(notes?|data|archive|records?)\b", "asks for raw notes"),
    (r"\b(bank_id|client-\*|bank contents|list (every|all) client)", "asks for bank contents / client enumeration"),
    (r"\b(industry|region|headcount|location|where was)\b.{0,60}\b(client|utility|company|so i can figure)", "attempts re-identification by combination"),
]


def extraction_intent(question: str) -> list[str]:
    q = question.lower()
    return sorted({why for pat, why in EXTRACTION_PATTERNS if re.search(pat, q)})


# ----------------------------------------------------------------------------- advice composer
NUM_WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def nw(n: int) -> str:
    return NUM_WORDS[n] if 0 <= n < len(NUM_WORDS) else "many"


def strength_label(n: int) -> str:
    return "Strong" if n >= 3 else "Moderate" if n == 2 else "Emerging"


def rank_lessons(question: str, lessons: list[dict], limit: int = 4) -> list[tuple[float, dict]]:
    q = Counter(_tokens(question))
    q_cat = classify_category(question)
    if q_cat != "other" and any(l.get("category") == q_cat for l in lessons):
        # stay on-topic: when the playbook has lessons in the question's category, use only those
        lessons = [l for l in lessons if l.get("category") == q_cat]
    out = []
    for l in lessons:
        d = Counter(_tokens(" ".join([l["text"], l.get("category") or "", l.get("approach") or "", l.get("conditions") or "", l.get("why") or ""])))
        s = sum(min(q[t], d[t]) for t in q)
        if l.get("category") == q_cat:
            s += 4
        if l.get("status") == "synthesis":
            s += 1.5
        if s > 0:
            out.append((s, l))
    out.sort(key=lambda x: -x[0])
    return out[:limit]


def compose_advice(question: str, lessons: list[dict], intents: list[str]) -> dict:
    ranked = rank_lessons(question, lessons)
    parts: list[str] = []
    if intents:
        parts.append("**Confidentiality note:** I can't tell you which client, people, figures, dates or quotes are behind "
                     "any lesson. The shared playbook never stored them, so there's nothing here to reveal. What I can "
                     "share is the generalized guidance.")
    if not ranked:
        parts.append("The shared playbook doesn't have a verified lesson relevant to this question yet. As more "
                     "engagements close and pass the independent leak check, advice on this topic will appear here.")
        return {"text": "\n\n".join(parts), "used": []}
    synth = [l for _, l in ranked if l.get("status") == "synthesis"]
    used = [l for _, l in ranked]
    total_ev = sum(l.get("evidence_count", 1) for l in used if l.get("status") != "synthesis")
    if synth:
        parts.append(f"**Conditional guidance (reconciled from conflicting evidence):** {synth[0]['text']}")
    bullets = []
    for l in used:
        if l.get("status") == "synthesis":
            continue
        ev = l.get("evidence_count", 1)
        tag = f"{strength_label(ev)} evidence · {ev} independent engagement{'s' if ev != 1 else ''}"
        cond = f" *Applies when:* {l['conditions']}" if l.get("conditions") else ""
        bullets.append(f"- **{l.get('approach', '').replace('-', ' ').capitalize()} → {l.get('outcome')}** ({tag}). {l['text']}{cond}")
        for h in [h for h in (l.get("history") or []) if h.get("event") == "reinforced" and h.get("text")][:2]:
            bullets.append(f"  - *Independent corroboration:* {h['text']}")
    if bullets:
        parts.append("**What the playbook says:**\n" + "\n".join(bullets))
    # questions derived from the conditions of the used lessons
    conds = [l.get("conditions") for l in used if l.get("conditions")]
    if conds:
        qs = "\n".join(f"- Does this hold for your client? *{c}*" for c in conds[:3])
        parts.append("**Check before applying:**\n" + qs)
    parts.append(f"**Evidence strength:** {strength_label(total_ev)} — based on {total_ev} verified, anonymized "
                 f"engagement contribution{'s' if total_ev != 1 else ''}. This is evidence count, not measured accuracy.")
    return {"text": "\n\n".join(parts), "used": used}


def synthesize_conflict(category: str, approach: str, lessons: list[dict]) -> str:
    worked = [l for l in lessons if l.get("outcome") == "worked"]
    failed = [l for l in lessons if l.get("outcome") != "worked"]
    ah = approach.replace("-", " ")
    w_cond = "; ".join(sorted({l.get("conditions", "").rstrip(".") for l in worked if l.get("conditions")})) or "the conditions in the supporting lessons"
    f_cond = "; ".join(sorted({l.get("conditions", "").rstrip(".") for l in failed if l.get("conditions")})) or "the conditions in the contrary lesson"
    ev_w = sum(l.get("evidence_count", 1) for l in worked)
    ev_f = sum(l.get("evidence_count", 1) for l in failed)
    alt = next((l.get("alternative_approach") for l in failed if l.get("alternative_approach")), "a single, heavily rehearsed cutover")
    return (f"There is no universal answer on a {ah} for {category.replace('-', ' ')}. Prefer a {ah} when the work "
            f"involves {w_cond.lower()} (supported by {nw(ev_w)} engagement{'s' if ev_w != 1 else ''}). Where {f_cond.lower()}, "
            f"running old and new side by side can create conflicting records, and {alt.replace('-', ' ')} with full "
            f"rehearsals and a hard rollback criterion has worked better (supported by {nw(ev_f)} engagement{'s' if ev_f != 1 else ''}). "
            f"Decide by testing how independently the parts can operate, not by defaulting to either approach.")


def private_answer(question: str, recalled: list[dict], client_name: str) -> str:
    if not recalled:
        return f"No memories in {client_name}'s private bank matched that question."
    lines = [f"From **{client_name}**'s private bank only (authorized engagement-team view), the most relevant memories are:"]
    for m in recalled[:4]:
        ts = f"[{m.get('timestamp')}] " if m.get("timestamp") else ""
        lines.append(f"- {ts}{m['text']}")
    lines.append("_No other client's bank was accessed._")
    return "\n".join(lines)


def naive_answer(question: str, pooled_notes: list[dict]) -> str:
    """Hypothetical naive architecture: every client's raw notes in one shared context, no wall."""
    q = Counter(_tokens(question))
    scored = []
    for n in pooled_notes:
        d = Counter(_tokens(n["text"] + " " + n["client"]))
        s = sum(min(q[t], d[t]) for t in q)
        scored.append((s, n))
    scored.sort(key=lambda x: -x[0])
    top = [n for s, n in scored[:3]]
    return "Here's what I found across all engagements:\n" + "\n".join(f"- {n['client']}: {n['text']}" for n in top)
