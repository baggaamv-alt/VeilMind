"""Layer-1 deterministic re-identification screen.

This screen sees ONLY the candidate lesson text. It has no client list, no private notes and no knowledge of which
engagement produced the text — it looks for *kinds* of identifying detail (names, numbers, dates, quotes,
locations, uniqueness claims, identifying combinations). It is a transparent heuristic, not a guarantee.
"""
from __future__ import annotations

import re

MONTHS = "January|February|March|April|June|July|August|September|October|November|December"
GENERIC_CAPS = {
    # acronyms / generic capitalized terms that are not identifying on their own
    "IT", "OT", "ERP", "EHR", "EMR", "MRP", "WMS", "TMS", "CRM", "SaaS", "API", "APIs", "EDI", "ASN", "CIO", "CEO", "CFO",
    "COO", "CISO", "CMIO", "CTO", "VP", "PMO", "KPI", "KPIs", "SLA", "SLAs", "UAT", "QA", "AI", "ML", "LAN", "HR", "RFP",
    "ROI", "B2B", "B2C", "SKU", "SKUs", "POS", "I", "A", "An", "The", "NO", "SAFE", "LESSON", "OK", "US",
}
LOCATIONS = [
    # broad gazetteer of place words (generic world knowledge, not client data)
    "India", "Hyderabad", "Telangana", "Andhra Pradesh", "Andhra", "Bengaluru", "Bangalore", "Mumbai", "Delhi", "Chennai",
    "Pune", "Kolkata", "Gujarat", "Kerala", "Karnataka", "Tamil Nadu", "Maharashtra", "Genome Valley",
    "United States", "USA", "America", "Canada", "Mexico", "Europe", "Germany", "France", "London", "UK", "Britain",
    "Singapore", "Japan", "China", "Australia", "Dubai", "Texas", "California", "New York", "Florida", "Ohio",
    "Illinois", "Chicago", "Boston", "Seattle", "Atlanta", "Denver", "Houston", "Beaumont",
    "Midwest", "Upper Midwest", "Northeast", "Southwest", "Southeast", "Northwest", "Pacific Northwest",
    "Gulf Coast", "Mid-Atlantic", "New England", "Bay Area", "Silicon Valley",
]
UNIQUENESS = re.compile(r"\b(the only|the first|the largest|the biggest|the oldest|sole|one of only|only one of)\b", re.I)
INDUSTRY_WORDS = re.compile(
    r"\b(bank|banking|credit union|cooperative|hospital|health network|insurer|insurance|utility|nuclear|"
    r"transit|airline|aerospace|defen[cs]e|biotech|biologics|pharma|retailer|logistics|freight|university|ministry|"
    r"municipal|government agency)\b", re.I)
SIZE_WORDS = re.compile(r"\b(mid-sized|mid-size|small|large|regional|national|global|single[- ]site|family-owned)\b", re.I)
REGION_ADJ = re.compile(r"\b(coastal|northern|southern|eastern|western|rural|metropolitan|downtown)\b", re.I)

CURRENCY = re.compile(r"([$€£₹]\s?\d[\d,.]*\s?(k|m|mn|bn|million|billion|crore|lakh)?|\b\d[\d,.]*\s?(million|billion|crore|lakh|dollars|rupees)\b)", re.I)
NUMBER = re.compile(r"\b\d[\d,.]*%?")
YEAR = re.compile(r"\b(19|20)\d{2}\b")
MONTH = re.compile(rf"\b({MONTHS})\b|\bMay\s+(\d|19|20)")
QUARTER = re.compile(r"\bQ[1-4]\b")
QUOTE = re.compile(r"[\"“”]([^\"“”]{12,})[\"“”]")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")


def _proper_nouns(text: str) -> list[str]:
    found = []
    # split into sentences and ignore the first word of each sentence
    for sent in re.split(r"(?<=[.!?:;])\s+|\n+", text):
        words = re.findall(r"[A-Za-z][A-Za-z'’\-]*", sent)
        for i, w in enumerate(words):
            if i == 0 or len(w) < 2:
                continue
            if w[0].isupper() and w not in GENERIC_CAPS and w.rstrip("s") not in GENERIC_CAPS:
                found.append(w)
    return found


def screen(text: str) -> dict:
    """Return {'verdict': 'SAFE'|'UNSAFE', 'findings': [...], 'engine': ...}."""
    findings: list[dict] = []
    t = text or ""

    def add(kind: str, match: str, why: str) -> None:
        findings.append({"type": kind, "match": match.strip()[:80], "why": why})

    money_spans = []
    for m in CURRENCY.finditer(t):
        money_spans.append(m.span())
        add("exact-figure", m.group(0), "Exact monetary amount")
    for m in YEAR.finditer(t):
        add("exact-date", m.group(0), "Specific year")
    for m in MONTH.finditer(t):
        add("exact-date", m.group(0), "Specific month / date")
    for m in QUARTER.finditer(t):
        add("exact-date", m.group(0), "Specific quarter")
    for m in NUMBER.finditer(t):
            if YEAR.fullmatch(m.group(0)) or any(a <= m.start() < b for a, b in money_spans):
                continue
            add("exact-number", m.group(0), "Exact number (should be qualitative scale)")
    for m in QUOTE.finditer(t):
        add("direct-quote", m.group(0), "Looks like a direct quote")
    for m in EMAIL.finditer(t):
        add("contact", m.group(0), "Email address")
    loc_hits = []
    for loc in sorted(LOCATIONS, key=len, reverse=True):
        if any(loc in h for h in loc_hits):
            continue
        if re.search(rf"\b{re.escape(loc)}\b", t):
            loc_hits.append(loc)
            add("location", loc, "Names a location")
    loc_words = {w for l in loc_hits for w in l.split()}
    for w in _proper_nouns(t):
        if w in loc_words or w in MONTHS.split("|"):
            continue
        add("proper-noun", w, "Capitalized name mid-sentence (possible company/person/product name)")
    uniq = UNIQUENESS.search(t)
    ind = INDUSTRY_WORDS.search(t)
    if uniq and ind:
        add("uniqueness-claim", f"{uniq.group(0)} … {ind.group(0)}", "Uniqueness claim + industry narrows to one organization")
    region = REGION_ADJ.search(t)
    size = SIZE_WORDS.search(t)
    if ind and size and (region or loc_hits):
        add("identifying-combination", f"{size.group(0)} + {ind.group(0)} + {(region.group(0) if region else loc_hits[0])}",
            "Industry + size + location combination")

    # de-duplicate
    seen, uniq_findings = set(), []
    for f in findings:
        k = (f["type"], f["match"].lower())
        if k not in seen:
            seen.add(k)
            uniq_findings.append(f)
    return {
        "verdict": "UNSAFE" if uniq_findings else "SAFE",
        "findings": uniq_findings,
        "engine": "deterministic re-identification screen (regex + gazetteer; no client context)",
    }


def usefulness(lesson: str) -> dict:
    """Guard against over-redaction: a lesson must still say something actionable."""
    t = (lesson or "").strip()
    words = len(t.split())
    has_reason = bool(re.search(r"\b(because|since|so that|which|cause|reason|where|when|—|->|;)\b", t, re.I)) or "," in t
    ok = words >= 18 and has_reason and t.upper() != "NO SAFE LESSON"
    return {"useful": ok, "words": words, "has_reason": has_reason}
