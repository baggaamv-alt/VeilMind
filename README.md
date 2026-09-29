# Veilmind

**Your firm learns. Your clients stay private.**
HackwithHyderabad 3.0 · Hindsight (Vectorize) memory agents · working prototype

An AI agent that lets a consulting firm learn from every client engagement without being able to leak one client's
confidential details to another. Each client has an isolated private memory bank. When an engagement closes, the agent
distills **one** generalized lesson. An **independent** verifier, which sees only the lesson text, checks whether it could
re-identify the client, and only SAFE lessons reach the shared `firm-playbook` bank.

> ⚠️ **Prototype.** LLM-based and heuristic leak checks *reduce* risk; they do **not** guarantee confidentiality.
> The UI reports the actual observed results of every check, and every simulated result is labeled as simulated.

---

## 1. Architecture (per the brief, §4)

```
 Client A bank ─┐                                   ┆
 Client B bank ─┼─ recall ─► distill (reflect) ─────┼─► independent leak check ─► retain ─► firm-playbook bank
 Client C bank ─┘            one generalized lesson ┆    lesson text ONLY            (SAFE)          │
   (raw notes: names, figures,                      ┆    UNSAFE → discarded                          ▼
    dates, quotes — never leave)          confidentiality wall                 new-client query: recall / reflect
```

| Piece | Implementation |
|---|---|
| Private banks | One Hindsight bank per client: `veilmind-client-<id>`. All raw notes are retained **only** there. |
| Shared bank | `veilmind-firm-playbook`. Only distilled lessons that passed verification (plus reconciled syntheses). |
| Verifier bank | `veilmind-leak-verifier`, intentionally **empty** and never written. Used only if the leak judge runs through Hindsight `reflect`. |
| Distill | `reflect(client bank, DISTILL_QUERY, response_schema=…)` under a **client scope**, which returns exactly one lesson or `NO SAFE LESSON`. |
| Verify | Layer 1: a deterministic re-identification screen (names, numbers, dates, quotes, locations, uniqueness claims, industry+size+location combos). Layer 2: an LLM judge (Groq `openai/gpt-oss-120b` → `qwen/qwen3-32b`, or Hindsight reflect on the empty verifier bank). **SAFE only if both layers agree; fail closed on errors.** |
| Corroboration gate | Lessons the distiller marks `unusual` are **held** (not shared) until a second, unrelated engagement shows the same pattern. |
| Reinforce / conflict | Same category + approach + outcome → reinforcement (evidence +1). Same approach with the opposite outcome → a contradiction is detected and reconciled with `reflect` on the shared bank into conditional guidance, which is leak-checked again. |
| Scope gateway | `app/memory.py::MemoryGateway` is the **only** path to memory. Every call is scope-checked (`client:<id>`, `playbook`, `verifier`, `admin`) and logged to `access_log`, so "private-bank reads during shared queries" is a **counted** number. |
| Metadata | SQLite: engagements, workflow records, lesson metadata and history, conflicts, attack runs, activity, access log, playbook snapshots. |

### Confidentiality controls (defense in depth)

1. One isolated bank per client plus one shared bank, and the gateway enforces scope on every call.
2. Raw notes are never retained in the shared bank. The test suite checks the shared bank's contents against every client's sensitive terms.
3. The verifier function signature takes **only a string**. No client id, name or notes are passed to it, and the UI shows "inputs seen: lesson text only".
4. UNSAFE lessons are discarded. The candidate text survives only in the private workflow record (authorized review screen).
5. Numbers become qualitative scale. Rare single-client lessons are held back. If nothing useful survives, the result is `NO SAFE LESSON` (a usefulness guard rejects over-redacted lessons).
6. Shared answers pass through an output filter that redacts figures, dates, quotes and locations.
7. The attack lab audits responses against every client's sensitive terms (the auditor is a test harness and is allowed to know them).

---

## 2. Quick start (any laptop)

**Requirement:** Python 3.10 or newer ([python.org/downloads](https://www.python.org/downloads/)). On Windows, tick
**"Add python.exe to PATH"** during setup. Nothing else needs to be installed.

| Laptop | How to start |
|---|---|
| **Windows** | Double-click **`Start Veilmind (Windows).bat`** |
| **macOS** | Double-click **`Start Veilmind (Mac).command`** (if macOS blocks it: right-click → Open, or run `python3 start.py` in Terminal) |
| **Linux** | `./start.sh` (or `python3 start.py`) |
| Any terminal | `python start.py` (Windows: `py -3 start.py`) |

The launcher (`start.py`, standard library only):

1. checks the Python version and explains how to fix it if it's too old;
2. creates a private environment for this computer (`.venv-<os>-py<version>`). A folder copied from another laptop never reuses that laptop's environment, and a broken one is rebuilt automatically;
3. installs the packages (**first run only, needs internet once**, then works offline);
4. creates `.env` from `.env.example` if missing (DEMO MODE, no keys needed);
5. picks a free port (8000, or the next free one), starts the server and opens the browser.

Pages: **`/`** landing, **`/app`** dashboard, **`/app?demo=1`** guided demo. Options: `--port 9000`, `--no-browser`,
`--reset` (wipe local data; synthetic data is re-seeded on start). Stop with **Ctrl+C**.

**Sending it to someone:** zip the folder *without* `.venv-*`, `.env` and `veilmind.sqlite3*` (the included zip already
excludes them). Each laptop builds its own environment and data on first run. Fonts and GSAP are bundled, so the pages
make no internet requests at runtime. The database uses the standard SQLite journal, so it's safe inside
OneDrive/Dropbox-synced folders.

Run the tests:

```bash
python start.py --no-browser    # once, to create the environment; then Ctrl+C
# Windows:   .venv-win32-py3XX\Scripts\python -m pip install -r requirements-dev.txt
#            .venv-win32-py3XX\Scripts\python -m pytest -q tests
# mac/Linux: .venv-*/bin/python -m pip install -r requirements-dev.txt && .venv-*/bin/python -m pytest -q tests
```

Verified: clean install and launch on Python 3.10 and 3.11, in a folder path containing spaces, with a busy default
port, and with a deliberately broken environment (rebuilt automatically). The pages load with zero external requests.

## 3. LIVE MODE vs DEMO MODE

| | **LIVE MODE** | **DEMO MODE** |
|---|---|---|
| Enabled when | `HINDSIGHT_API_KEY` set and `APP_MODE=auto` or `live` | no key, or `APP_MODE=demo` |
| Memory banks | Real Hindsight Cloud banks via `hindsight-client` | Local SQLite keyword store, labeled **"NOT Hindsight"** |
| Recall | `hindsight.recall` | Keyword/BM25-style ranking (stemming + small synonym list) |
| Distillation | `hindsight.reflect` with a JSON response schema | Pre-written candidate lesson per synthetic engagement (user-created engagements use a keyword template) |
| Leak check layer 1 | Deterministic screen (real) | Deterministic screen (real) |
| Leak check layer 2 | Groq LLM judge, or Hindsight reflect on the empty verifier bank | Not run, shown as **SKIPPED** |
| Advice / chat | `hindsight.reflect` on `firm-playbook` only | Deterministic composer over shared lessons only |
| Conflict synthesis | `hindsight.reflect` on `firm-playbook`, then leak-checked | Deterministic conditional template, then leak-checked |
| Attack lab | Live responses, real audit | Simulated responder, real audit, labeled **simulated** |

In DEMO MODE the scope gateway, access log, leak screen, corroboration gate, reinforcement, conflict detection, auditor,
metrics and every UI flow are **real code running on real data**. The only simulated parts are the ones an LLM or
Hindsight would do, and each is labeled.

### Switching to LIVE MODE

1. Register at Hindsight Cloud, then apply promo code `MEMHACK99` in *Billing* (after registering).
2. Edit `.env`:
   ```
   APP_MODE=auto
   HINDSIGHT_API_KEY=hs_...
   HINDSIGHT_BASE_URL=https://api.hindsight.vectorize.io
   GROQ_API_KEY=gsk_...        # optional: independent leak judge (recommended)
   ```
3. Smoke-test the round trip first (brief §4c.6), using the environment `start.py` created: `.venv-<os>-py<ver>/…/python scripts/smoke_test_hindsight.py`
4. Restart the server. In LIVE MODE data is **not** auto-seeded (it costs credits). Click **Metrics & demo → Seed synthetic engagements**, or run `python scripts\seed.py`.
5. You can switch modes at runtime from the mode card at the bottom of the sidebar. Switching resets and reseeds into the newly active backend.

Seeding in LIVE MODE makes 9 `retain_batch` calls plus one full pipeline run. Set `HINDSIGHT_RETAIN_ASYNC=true` to make it faster.
Check which LLM Hindsight Cloud uses server-side for `reflect` in your Hindsight console; this app's Groq key is only
used for the independent leak judge.

---

## 4. What's in the app

| Page | What works |
|---|---|
| Landing (`/`) | Masked word-by-word headline, scroll-triggered heading and card reveals, a scroll progress bar, a scroll-scrubbed "Remember → Generalize → Verify" diagram, light streaks flowing through the gate into a playbook that fills row by row, and live counters. "Open dashboard" goes to a separate page. |
| Dashboard (`/app`) | Separate page with sidebar navigation, staggered page transitions and cursor-tracked card borders. |
| Overview | KPI counters, a playbook evolution step chart (hover crosshair), private-vs-shared wall panel, a decision breakdown and the activity feed. |
| Engagements | Filterable list, private detail (team, figures, timeline), **Inspect private bank**, **Recall**, **Add note** (retained into that bank only), **Close → learn**, and **New engagement**. |
| Memory architecture | Interactive network of client banks → distillation → gate → playbook, with animated particles. Click a bank to inspect only that client. |
| Learning pipeline | A live, polled pipeline with per-stage status, timestamps and messages. The final decision is stamped. The authorized review shows **private notes next to the generalized lesson**, with leaky spans highlighted, plus verifier details. Includes workflow history. |
| Shared playbook | Search, filters (topic, approach, outcome, evidence), lesson drawer with anonymized contributions and a history timeline (added / reinforced / contradicted / revised), the held-back list, and a raw shared-bank inspector. |
| AI consultant | New-client selector, question box, "Shared Playbook Only" badge, sources used, playbook size at answer time, extraction-attempt flag, follow-ups, an **authorized private mode** scoped to one client, and the **memory panel** (brief Phase 8): the selected client's private bank contents next to the shared playbook bank contents. |
| Attack lab | 20 prompts; run one or all, pass/fail filters, responses, explanations, audit log, gateway refusals, custom attacks, **naive baseline**, and **fault injection** (proves the pass rate isn't hardcoded). |
| Conflicts | Both sides with their evidence, **Reconcile with reflect**, the conditional synthesis, and an evolution strip. |
| Metrics & demo | Quality rubric after 1 → N engagements, advice before and after, naive vs isolated comparison, audit panel, evolution timeline, **Seed**, **Reset**, **Close all remaining**. |
| Guided demo | A 7-step dock (brief §5 Phase 9 order) with a progress bar, prev/next/restart. Every step calls the real API. |

Responsive layout (sidebar collapses to a drawer on mobile). `prefers-reduced-motion` disables animations. GSAP is
vendored in `static/vendor` (it works offline). If GSAP fails, an IntersectionObserver fallback takes over.

---

## 5. Synthetic data (`data/clients/*.json`, all fictional)

| Engagement | Pattern | Expected pipeline result |
|---|---|---|
| Halvorsen Regional Bank: core banking migration | big-bang failed twice → phased worked | **RETAINED** (pre-closed at seed) |
| Tessaract Freight Logistics: WMS replacement | pilot site + waves worked | **REINFORCED** (same lesson) |
| Mariposa Health Network: EHR consolidation | site-by-site + champions worked | **REINFORCED** |
| Kestrel Aerospace Components: ERP/MRP | phased **failed** (tightly coupled, single site) → rehearsed single cutover | **RETAINED + contradiction** → reconciled |
| Bluefin Retail Group: pricing/loyalty | controlled regional pilot worked | **RETAINED** |
| Orchard Lane Mutual Insurance: claims SaaS | heavy customization failed | **RETAINED** |
| Sable Point Energy Cooperative: OT security | draft lesson keeps industry + location + deadline | **DISCARDED** (verifier UNSAFE) |
| Crescent Metro Transit Authority: bid protest | unusual single-client pattern | **HELD** (needs corroboration) |
| Velora Biologics: tech-transfer recovery | outcome driven by one interpersonal dispute | **NO SAFE LESSON** |

New-client personas for the consultant are in `data/new_clients.json`, and the adversarial prompts are in `data/adversarial_prompts.json`.

---

## 6. Observed results (DEMO MODE, from `tests/test_pipeline.py`)

* Pipeline decisions match the table above for all 8 closable engagements.
* Shared bank contents vs. every client's sensitive terms: **0 matches**.
* Adversarial suite (isolated architecture): **20/20 passed**. This was the **simulated responder**, so it is *not* a real-world security result.
* Naive pooled-memory baseline (same prompts, same auditor): **0/20 passed, ~245 leaked terms** (simulated for contrast).
* With **fault injection** (one unverified leaky lesson written straight to the shared bank), the suite drops to **19/20**. The auditor is real.
* Private-bank reads during shared queries (counted from the access log): **0**.
* Quality rubric for the held-out client: **56 → 100** as the playbook grows (automated keyword rubric, illustrative).
* The lab found one real leak during development: private-mode answers echoed the *refused bank id*, which contains the other client's slug. Fixed: refusals no longer echo bank ids.

In LIVE MODE, run `python scripts\run_adversarial.py` and report the number you actually observe.

---

## 7. Prompt changes vs. the brief's drafts (§4d)

* **Distillation:** added explicit bans on counts, percentages, durations, months, years and quarters (the draft only said "exact dollar figures, exact dates"). Added "never mention a location". Added a structured JSON schema (category, approach, outcome, why, conditions, scale, **rarity**) so reinforcement, conflict detection and the corroboration gate can work deterministically. Kept `NO SAFE LESSON` and told the model not to water lessons down.
* **Leak check:** added direct quotes and **uniqueness superlatives** ("the only…", "the first…") as re-identification signals. Required the verdict on the first line so it can be parsed reliably. Anything unparseable, or any judge error, counts as **UNSAFE** (fail closed).
* **Conflict synthesis:** the synthesis is itself leak-checked. In testing, the first template wrote evidence counts as digits ("3 engagements"), which the screen rejected, so counts are now written as words.

---

## 8. API endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health check + mode info |
| GET/POST | `/api/mode` | Read / switch mode (`live`, `demo`, `auto`; switching reseeds) |
| POST | `/api/seed`, `/api/reset` | Reset + seed synthetic engagements (background job) |
| GET | `/api/jobs/{id}` | Poll a background job |
| GET/POST | `/api/engagements` | List / create an engagement (creates its private bank + retains notes) |
| GET | `/api/engagements/{id}` | Engagement detail (private) |
| POST | `/api/engagements/{id}/notes` | Retain a note into that client's bank only |
| GET | `/api/engagements/{id}/memory` | Inspect that client's private bank |
| POST | `/api/engagements/{id}/recall` | Scoped recall on that client's bank |
| POST | `/api/engagements/{id}/close` | Close → start the learning pipeline (returns `workflow_id`) |
| GET | `/api/workflows`, `/api/workflows/{id}` | Pipeline runs with stages, timestamps, candidate and verification |
| POST | `/api/pipeline/distill/{id}` | Preview distillation only (nothing retained) |
| POST | `/api/pipeline/verify` | Run the independent leak check on arbitrary text |
| GET | `/api/playbook` | Verified lessons (`q`, `category`, `approach`, `outcome`, `strength`) |
| GET | `/api/playbook/{id}` | Lesson detail + history + conflict |
| GET | `/api/playbook/held` | Lessons held for corroboration |
| GET | `/api/playbook-bank/memories` | Raw contents of the shared bank |
| GET | `/api/new-clients` | New-client personas |
| POST | `/api/chat` | Consultant (`mode`: `shared` or `private`) |
| GET | `/api/chat/{session}` | Chat history |
| GET | `/api/attacks` | Prompts + latest run |
| POST | `/api/attacks/run`, `/api/attacks/run-all` | Run selected / all adversarial tests |
| POST | `/api/attacks/custom` | Run a custom attack |
| POST | `/api/attacks/naive` | Naive pooled-memory baseline (simulated) |
| GET | `/api/attacks/audit-log` | Attack audit log |
| POST | `/api/lab/inject-unsafe`, `/api/lab/clear-injected` | Fault injection for auditor testing |
| GET | `/api/conflicts` | Detected contradictions |
| POST | `/api/conflicts/{id}/resolve` | Reconcile with reflect → conditional synthesis |
| GET | `/api/metrics/overview`, `/evolution`, `/quality`, `/comparison` | Dashboard metrics (`quality?live=1` also scores the live answer) |
| GET | `/api/activity`, `/api/access-log` | Activity feed; gateway access log (incl. refusals) |
| GET | `/api/architecture` | Bank graph for the visualization |
| POST | `/api/demo/close-all` | Close every remaining engagement + reconcile (job) |

Interactive docs: **http://localhost:8000/docs**

---

## 9. Project layout

```
app/
  main.py        FastAPI routes, validation, error handling, static hosting
  config.py      env settings (.env)
  db.py          SQLite schema + helpers
  memory.py      MemoryGateway (scope enforcement + access log), HindsightBackend, SimulatedBackend
  llm.py         Groq client with retry + model fallback
  prompts.py     distillation / leak-check / advisor / conflict prompts + schemas
  redaction.py   deterministic re-identification screen + usefulness guard
  pipeline.py    close workflow, independent check, corroboration, retain, conflicts
  advisor.py     shared-playbook advice + authorized private query
  adversarial.py attack suite, auditor, naive baseline
  metrics.py     overview, evolution, quality rubric, comparison
  simulator.py   DEMO MODE deterministic logic (clearly labeled)
  seed.py        reset + seed + background jobs
data/            synthetic engagements, new clients, adversarial prompts (JSON)
static/          index.html (landing), app.html (dashboard), css/, js/ (core, charts, viz, pages, demo, landing, app), vendor/ (GSAP)
scripts/         init_db, seed, smoke_test_hindsight, run_adversarial
tests/           end-to-end pipeline + confidentiality test
```

## 10. Known limitations

* Heuristic + LLM leak checks can miss subtle re-identification, or reject safe text (false positives are discarded, not weakened).
* The SQLite metadata DB stores engagement notes for the private UI. It's scoped per engagement and never read by shared-query code paths, but a production system would keep it under the same access controls as the private banks.
* The quality curve is an automated keyword rubric, not a human evaluation.
* LIVE MODE was implemented against `hindsight-client` 0.10.1 and exercised with a mocked SDK. Run the smoke test with your key first.

## Troubleshooting

* **"Python is not installed" on Windows even after installing:** reinstall with "Add python.exe to PATH" ticked, or turn off the Microsoft Store "App execution aliases" for python.
* **Port in use:** handled automatically (the next free port is used), or pass `--port 9000`.
* **Mac says the .command file can't be opened:** right-click → Open once, or run `python3 start.py` in Terminal.
* **Behind a company proxy:** set `HTTPS_PROXY` before the first run so the package install can reach PyPI.
* **Start fresh:** `python start.py --reset`.
* **LIVE MODE errors:** check the pipeline card's error message. The workflow is saved as `ERROR` with the reason, and the lesson is never shared.
