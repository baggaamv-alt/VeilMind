/* Application pages. Each page exposes show(); some expose helpers used by the guided demo. */
(function () {
  const C = window.CCPM;
  const { $, $$, esc, api, post, st, md } = C;
  const DEC_LABEL = { RETAINED: "Retained", REINFORCED: "Reinforced", DISCARDED: "Discarded", HELD: "Held", NO_SAFE_LESSON: "No safe lesson", ERROR: "Error" };
  const decChip = (d) => (d ? st(d.toLowerCase(), DEC_LABEL[d] || d) : "");

  async function loadEngagements() {
    C.state.engagements = await api("/api/engagements");
    return C.state.engagements;
  }

  // =========================================================== OVERVIEW
  C.pages.overview = {
    async show() {
      const [ov, evo, act] = await Promise.all([api("/api/metrics/overview"), api("/api/metrics/evolution"), api("/api/activity?limit=30")]);
      const audit = ov.audit.last_run;
      const kp = [
        { l: "Client engagements", v: ov.engagements.total, s: `${ov.engagements.active} active · ${ov.engagements.closed} closed`, c: "" },
        { l: "Private memories", v: ov.private_memories, s: `across ${ov.engagements.total} isolated banks`, c: "private" },
        { l: "Verified lessons", v: ov.verified_lessons, s: `${ov.evidence_total} engagement contributions`, c: "shared" },
        { l: "Blocked lessons", v: ov.blocked_lessons, s: `${ov.decisions.DISCARDED || 0} unsafe · ${ov.decisions.NO_SAFE_LESSON || 0} no safe lesson`, c: "private" },
        { l: "Held for corroboration", v: ov.held_lessons, s: "not in the shared bank", c: "violet" },
        { l: "Audit pass rate", v: audit ? Math.round((100 * audit.passed) / audit.total) : "—", suf: audit ? "%" : "", s: audit ? `${audit.passed}/${audit.total} attacks blocked` : "suite not run yet", c: "violet" },
      ];
      $("#kpis").innerHTML = kp.map((k, i) => `<div class="kpi ${k.c}"><div class="k-label">${esc(k.l)}</div><div class="k-val" id="kv${i}">0</div><div class="k-sub">${esc(k.s)}</div></div>`).join("");
      kp.forEach((k, i) => { const e = $(`#kv${i}`); typeof k.v === "number" ? C.countUp(e, k.v, { suffix: k.suf || "" }) : (e.textContent = k.v); });
      if (ov.injected_unverified) $("#kpis").insertAdjacentHTML("afterend", "");
      // evolution
      C.lineChart($("#evolutionChart"), {
        labels: evo.map((_, i) => String(i)),
        tips: evo.map((e) => `${e.event} · ${C.time(e.ts)}`),
        series: [
          { name: "Verified lessons", color: C.colors.s1, values: evo.map((e) => e.lesson_count) },
          { name: "Engagement contributions (evidence)", color: C.colors.s2, values: evo.map((e) => e.evidence_total) },
        ],
      });
      // wall split
      $("#wallSplit").innerHTML = `
        <div class="wall-side priv"><h4>${C.icon("lock")} Private banks</h4><span class="muted small">raw notes · client scope only</span>
          <div class="big">${ov.private_memories}</div><ul><li>${ov.engagements.total} isolated banks</li><li>names, figures, dates, quotes stay here</li><li>${ov.audit.refused_cross_bank_attempts} cross-bank attempts refused</li></ul></div>
        <div class="wall" aria-hidden="true"></div>
        <div class="wall-side shar"><h4>${C.icon("book")} Shared playbook</h4><span class="muted small">generalized · verified</span>
          <div class="big">${ov.verified_lessons}</div><ul><li>${ov.evidence_total} anonymized contributions</li><li>${ov.audit.private_bank_reads_during_shared_queries} private-bank reads during ${ov.audit.shared_queries} shared queries</li><li>${ov.injected_unverified ? `<b style="color:#fb7185">${ov.injected_unverified} injected unverified lesson(s)!</b>` : "0 unverified lessons"}</li></ul></div>`;
      // decisions
      const d = ov.decisions, tot = Math.max(1, Object.values(d).reduce((a, b) => a + b, 0));
      C.hbars($("#decisionBars"), [
        { label: "Retained (new)", value: d.RETAINED || 0, max: tot, color: C.colors.good },
        { label: "Reinforced", value: d.REINFORCED || 0, max: tot, color: C.colors.s1 },
        { label: "Held back", value: d.HELD || 0, max: tot, color: C.colors.warn },
        { label: "Discarded (UNSAFE)", value: d.DISCARDED || 0, max: tot, color: C.colors.bad },
        { label: "No safe lesson", value: d.NO_SAFE_LESSON || 0, max: tot, color: "#be123c" },
      ]);
      $("#activityFeed").innerHTML = act.length ? act.map((a) => `<li><i class="${esc(a.kind)}"></i><span>${esc(a.message)}</span><time title="${esc(a.ts)}">${C.ago(a.ts)}</time></li>`).join("") : '<li class="muted">No activity yet.</li>';
    },
  };

  // =========================================================== ENGAGEMENTS
  let engFilter = "all";
  C.pages.engagements = {
    async show(opts = {}) {
      await loadEngagements();
      if (opts.select) C.state.selectedEng = opts.select;
      this.renderList();
      if (C.state.selectedEng) this.select(C.state.selectedEng);
    },
    renderList() {
      const list = C.state.engagements.filter((e) => engFilter === "all" || e.status === engFilter);
      $("#engList").innerHTML = list.map((e) => `<li class="eng-item ${C.state.selectedEng === e.id ? "sel" : ""}" data-id="${e.id}" tabindex="0">
        <div class="t"><b>${esc(e.name)}</b>${st(e.status.toLowerCase(), e.status)}</div>
        <small>${esc(e.engagement_type)} · ${e.notes_count} private notes</small>
        ${e.last_workflow ? `<div style="margin-top:8px">${decChip(e.last_workflow.decision) || st("running", "pipeline running")}</div>` : ""}</li>`).join("") || '<li class="empty">No engagements.</li>';
      $$("#engList .eng-item").forEach((li) => {
        li.addEventListener("click", () => this.select(li.dataset.id));
        li.addEventListener("keydown", (e) => e.key === "Enter" && this.select(li.dataset.id));
      });
    },
    async select(id) {
      C.state.selectedEng = id;
      $$("#engList .eng-item").forEach((li) => li.classList.toggle("sel", li.dataset.id === id));
      const e = await api(`/api/engagements/${id}`);
      const closed = e.status === "Closed";
      $("#engDetail").innerHTML = `
        <div class="priv-banner">${C.icon("lock")} Private bank · <span class="mono">${esc(e.bank_id)}</span> · visible only to this engagement's team</div>
        <div class="eng-head"><div><h3>${esc(e.name)}</h3><p class="muted">${esc(e.engagement_type)}</p></div><div>${st(e.status.toLowerCase(), e.status)} ${decChip(e.last_workflow && e.last_workflow.decision)}</div></div>
        <div class="eng-meta">
          <div><small>Industry</small>${esc(e.industry || "—")}</div><div><small>Region</small>${esc(e.region || "—")}</div>
          <div><small>Size</small>${esc(e.size || "—")}</div><div><small>Contract value</small>${esc(e.contract_value || "—")}</div>
          <div><small>Engagement partner</small>${esc(e.partner || "—")}</div><div><small>Client team</small>${esc((e.client_team || []).join(", ") || "—")}</div>
        </div>
        <div class="eng-actions">
          <button class="btn btn-ghost btn-sm" data-act="inspect">Inspect private bank</button>
          <button class="btn btn-ghost btn-sm" data-act="recall">Recall from private memory</button>
          ${closed ? "" : `<button class="btn btn-ghost btn-sm" data-act="note">${C.icon("plus")} Add note</button>`}
          ${closed ? `<button class="btn btn-ghost btn-sm" data-act="viewwf">View pipeline run</button>` : '<button class="btn btn-primary btn-sm" data-act="close">Close engagement → learn</button>'}
        </div>
        <div id="engSub"></div>
        <h4 style="margin:18px 0 12px">Engagement timeline · raw notes</h4>
        <ol class="tl">${e.notes.map((n) => `<li><span class="when">${esc(n.date || "")} · ${esc(n.author || "")}</span><p>${esc(n.text)}</p></li>`).join("")}</ol>`;
      const sub = $("#engSub");
      $$("#engDetail [data-act]").forEach((b) => b.addEventListener("click", () => {
        const a = b.dataset.act;
        if (a === "inspect") C.busy(b, async () => {
          const r = await api(`/api/engagements/${id}/memory`);
          sub.innerHTML = `<div class="subpanel"><b>${r.memories.length} memories</b> in <span class="mono">${esc(r.bank_id)}</span><ul class="mem-list">${r.memories.map((m) => `<li>${esc(m.text)}<small>${esc(m.context || "")}${m.timestamp ? " · " + esc(m.timestamp) : ""}</small></li>`).join("")}</ul></div>`;
        });
        if (a === "recall") {
          sub.innerHTML = `<div class="subpanel"><form class="recall-row" id="recallForm"><input type="text" id="recallQ" placeholder="e.g. what went wrong during cutover?" value="What went wrong and what finally worked?"/><button class="btn btn-primary btn-sm">Recall</button></form><div id="recallOut"></div></div>`;
          $("#recallForm").addEventListener("submit", (ev) => { ev.preventDefault(); C.busy(ev.submitter, async () => {
            const r = await post(`/api/engagements/${id}/recall`, { query: $("#recallQ").value });
            $("#recallOut").innerHTML = `<p class="muted small mt-s">Scope <span class="mono">${esc(r.scope)}</span> · ${esc(r.engine)}</p><ul class="mem-list">${r.results.map((m) => `<li>${esc(m.text)}${m.score != null ? `<small>score ${m.score}</small>` : ""}</li>`).join("") || "<li>No matches.</li>"}</ul>`;
          }); });
        }
        if (a === "note") {
          sub.innerHTML = `<div class="subpanel"><form id="noteForm" class="form-grid"><input type="date" id="nDate" value="${new Date().toISOString().slice(0, 10)}"/><input type="text" id="nAuthor" placeholder="Author" value="Consultant"/><textarea class="full" id="nText" rows="3" placeholder="What happened? Decisions, setbacks, outcomes…"></textarea><div class="full"><button class="btn btn-primary btn-sm">Retain into private bank</button></div></form></div>`;
          $("#noteForm").addEventListener("submit", (ev) => { ev.preventDefault(); C.busy(ev.submitter, async () => {
            await post(`/api/engagements/${id}/notes`, { date: $("#nDate").value, author: $("#nAuthor").value || "Consultant", text: $("#nText").value });
            C.toast("Note retained in the private bank only.", "ok");
            await loadEngagements(); this.renderList(); this.select(id);
          }); });
        }
        if (a === "close") C.go("pipeline", { run: id });
        if (a === "viewwf" && e.last_workflow) C.go("pipeline", { workflow: e.last_workflow.id });
      }));
    },
    newDialog() {
      const body = C.modal(`<h3>New client engagement</h3><p class="muted small">Creates a new isolated private bank and retains the notes into it. Use fictional data.</p>
        <form id="newEngForm" class="form-grid mt-s">
          <input class="full" id="neName" placeholder="Client name (fictional)" required minlength="2"/>
          <input id="neType" placeholder="Engagement type" required minlength="2" value="Systems migration"/>
          <input id="neInd" placeholder="Industry (private)"/>
          <input id="neReg" placeholder="Region (private)"/>
          <input id="neTerms" placeholder="Sensitive terms, comma-separated (for the audit)"/>
          <textarea class="full" id="neNotes" rows="6" placeholder="One note per line. Optional date prefix: 2026-03-01 | Phased rollout by region started with a pilot site…"></textarea>
          <div class="full"><button class="btn btn-primary btn-sm">Create engagement</button></div>
        </form>`);
      $("#newEngForm", body).addEventListener("submit", (ev) => { ev.preventDefault(); C.busy(ev.submitter, async () => {
        const notes = $("#neNotes").value.split("\n").map((l) => l.trim()).filter(Boolean).map((l) => {
          const m = l.match(/^(\d{4}-\d{2}-\d{2})\s*\|\s*(.+)$/);
          return m ? { date: m[1], author: "Consultant", text: m[2] } : { author: "Consultant", text: l };
        });
        const e = await post("/api/engagements", { name: $("#neName").value, engagement_type: $("#neType").value, industry: $("#neInd").value, region: $("#neReg").value,
          sensitive_terms: $("#neTerms").value.split(",").map((s) => s.trim()).filter(Boolean), notes });
        C.closeOverlays(); C.toast(`Created ${esc(e.name)} with private bank <span class="mono">${esc(e.bank_id)}</span>`, "ok");
        C.state.selectedEng = e.id; engFilter = "all"; this.show();
      }); });
    },
  };

  // =========================================================== ARCHITECTURE
  let archCtl = null, archData = null;
  C.pages.architecture = {
    async show() {
      archData = await api("/api/architecture");
      const sel = C.state.selectedEng;
      archCtl = C.renderArchitecture(archData, (id) => this.select(id), sel);
      const lessons = archData.playbook.lessons;
      const closed = archData.client_banks.filter((b) => b.status === "Closed");
      const blocked = closed.filter((b) => ["DISCARDED", "NO_SAFE_LESSON"].includes(b.decision)).length;
      $("#archCards").innerHTML = `
        <div class="panel arch-card"><span class="tag tag-red">A · Private client banks</span><h4>One isolated bank per client</h4><p>Raw names, people, exact figures, dates and quotes. Reachable only under that client's scope.</p><div class="big">${archData.client_banks.length}</div></div>
        <div class="panel arch-card"><span class="tag tag-cyan">B · Distillation engine</span><h4>reflect → exactly one lesson</h4><p>Runs inside the closing client's scope. Numbers become qualitative scale. If nothing useful survives, the result is NO SAFE LESSON.</p><div class="big">${closed.length} <span class="muted small">engagements distilled</span></div></div>
        <div class="panel arch-card"><span class="tag tag-violet">C · Independent verification gate</span><h4>Re-identification test</h4><p>Sees only the lesson text, never the source client or its notes. UNSAFE lessons are discarded, not weakened.</p><div class="big">${lessons} <span class="muted small">passed</span> · ${blocked} <span class="muted small">blocked</span></div></div>`;
      if (sel) this.select(sel); else this.renderSide(null);
      setTimeout(() => archCtl && archCtl.replay(), 350);
    },
    renderSide(e, mem) {
      if (!e) {
        $("#archSide").innerHTML = `<h3>Inspect a bank</h3><p class="muted">Click any client node to open its private bank. Only the selected client's memories appear here.</p>
          <div class="subpanel"><b>firm-playbook</b><p class="muted small">${archData.playbook.lessons} lessons · ${archData.playbook.evidence} contributions. Nothing raw is ever retained here.</p></div>
          <div class="subpanel"><b>leak-verifier</b><p class="muted small">${esc(archData.verifier.note)}</p></div>`;
        return;
      }
      $("#archSide").innerHTML = `<div class="priv-banner">${C.icon("lock")} ${esc(e.bank_id)}</div><h3>${esc(e.name)}</h3><p>${st(e.status.toLowerCase(), e.status)} ${decChip(e.decision)}</p>
        <ul class="mem-list">${mem.memories.slice(0, 8).map((m) => `<li>${esc(m.text)}</li>`).join("")}</ul>
        <div class="eng-actions mt-s"><button class="btn btn-ghost btn-sm" id="archOpenEng">Open engagement</button>${e.status === "Closed" ? "" : '<button class="btn btn-primary btn-sm" id="archClose">Close → learn</button>'}</div>`;
      $("#archOpenEng").onclick = () => C.go("engagements", { select: e.id });
      const cb = $("#archClose"); if (cb) cb.onclick = () => C.go("pipeline", { run: e.id });
    },
    async select(id) {
      C.state.selectedEng = id;
      $$("#archSvg .arch-node").forEach((g) => g.classList.toggle("sel", g.dataset.id === id));
      const e = archData.client_banks.find((b) => b.id === id);
      const mem = await api(`/api/engagements/${id}/memory`);
      this.renderSide(e, mem);
    },
    replay() { archCtl && archCtl.replay(); },
  };

  // =========================================================== PIPELINE
  const STAGE_KEYS = ["recall", "distill", "verify", "corroborate", "retain", "conflict"];
  let pollTimer = null;
  C.pages.pipeline = {
    async show(opts = {}) {
      await loadEngagements();
      const active = C.state.engagements.filter((e) => e.status === "Active");
      const sel = $("#pipeClient");
      sel.innerHTML = active.map((e) => `<option value="${e.id}">${esc(e.name)} — ${esc(e.engagement_type)}</option>`).join("") || "<option value=''>No active engagements</option>";
      if (opts.run && active.some((e) => e.id === opts.run)) sel.value = opts.run;
      $("#pipeRun").disabled = !active.length;
      this.history();
      if (opts.run) return this.run(opts.run);
      if (opts.workflow) return this.watch(opts.workflow);
      if (C.state.currentWf) return this.watch(C.state.currentWf);
      const last = (await api("/api/workflows"))[0];
      if (last) this.watch(last.id); else this.renderEmpty();
    },
    async refreshSelect() {
      await loadEngagements();
      const active = C.state.engagements.filter((e) => e.status === "Active");
      const sel = $("#pipeClient"), cur = sel.value;
      sel.innerHTML = active.map((e) => `<option value="${e.id}">${esc(e.name)} — ${esc(e.engagement_type)}</option>`).join("") || "<option value=''>No active engagements</option>";
      if (active.some((e) => e.id === cur)) sel.value = cur;
      $("#pipeRun").disabled = !active.length;
    },
    renderEmpty() {
      this.renderTrack({ stages: STAGE_KEYS.map((k) => ({ key: k, label: C.human(k), status: "pending", message: "" })) });
      $("#pipeDecision").innerHTML = '<span class="muted">Pick an active engagement and close it to run the learning pipeline.</span>';
      $("#pipeReview").innerHTML = "";
    },
    async run(id) {
      id = id || $("#pipeClient").value;
      if (!id) return C.toast("No active engagement to close.", "warn");
      if ([...$("#pipeClient").options].some((o) => o.value === id)) $("#pipeClient").value = id;
      const btn = $("#pipeRun");
      btn.disabled = true; btn.classList.add("loading");
      try {
        const r = await post(`/api/engagements/${id}/close`);
        C.toast("Learning pipeline started", "ok");
        return await this.watch(r.workflow_id);
      } catch (e) { C.err(e); }
      finally { btn.disabled = false; btn.classList.remove("loading"); }
    },
    watch(wid) {
      if (C.state.currentWf !== wid) this._prev = null;
      C.state.currentWf = wid;
      clearTimeout(pollTimer);
      return new Promise((resolve) => {
        const poll = async () => {
          try {
            const w = await api(`/api/workflows/${wid}`);
            this.render(w);
            if (w.status === "running") pollTimer = setTimeout(poll, 350);
            else { this.history(); this.refreshSelect(); C.refreshLandingCounts && C.refreshLandingCounts(); resolve(w); }
          } catch (e) { C.err(e); resolve(null); }
        };
        poll();
      });
    },
    renderTrack(w) {
      const cell = (s, i) => `<div class="pipe-node ${esc(s.status)}" data-k="${s.key}"><span class="pn-k">stage ${i + 1}</span><h4>${esc(s.label)}</h4>${st(s.status === "done" ? "done" : s.status, s.status === "done" ? "done" : s.status)}<p class="pn-msg">${esc(s.message || s.detail || "")}</p><span class="pn-time">${s.finished_at ? C.time(s.finished_at) : s.started_at ? C.time(s.started_at) : ""}</span></div>`;
      const decision = w.decision;
      const shared = ["RETAINED", "REINFORCED"].includes(decision);
      $("#pipeTrack").innerHTML = `<div class="pipe-node endpoint priv"><span class="pn-k">source</span><h4>${C.icon("lock")} Private bank</h4><p class="pn-msg mono small">${esc(w.engagement_id ? "client-" + w.engagement_id : "client-*")}</p><p class="pn-msg">${esc(w.client_name || "")}</p></div>`
        + w.stages.map(cell).join("")
        + `<div class="pipe-node endpoint shar"><span class="pn-k">destination</span><h4>${C.icon("book")} Shared playbook</h4><p class="pn-msg">${shared ? "lesson retained" : decision ? "nothing crossed the wall" : "waiting…"}</p></div>`
        ;
      // progress rail: fraction of stages that have finished (red if the lesson was stopped)
      const doneN = w.stages.filter((s) => !["pending", "running"].includes(s.status)).length;
      const runN = w.stages.some((s) => s.status === "running") ? 0.5 : 0;
      const bad = w.stages.some((s) => ["unsafe", "blocked", "error"].includes(s.status));
      const rail = $("#pipeRail");
      if (rail) { rail.classList.toggle("bad", bad); rail.firstElementChild.style.width = `${Math.min(100, ((doneN + runN) / w.stages.length) * 100)}%`; }
      // pop the stage that just changed
      const prev = this._prev || {};
      w.stages.forEach((s) => {
        if (prev[s.key] && prev[s.key] !== s.status && C.hasGsap && !C.reduced) {
          const node = $(`#pipeTrack [data-k="${s.key}"]`);
          if (node) gsap.fromTo(node, { scale: 0.96, y: 6 }, { scale: 1, y: 0, duration: 0.5, ease: "back.out(2)" });
        }
      });
      this._prev = Object.fromEntries(w.stages.map((s) => [s.key, s.status]));
    },
    render(w) {
      this.renderTrack(w);
      const cand = w.candidate || {}, ver = w.verification;
      const d = w.decision;
      const expl = {
        RETAINED: "The lesson passed the independent re-identification check and was retained in the shared playbook as a new lesson.",
        REINFORCED: "The lesson passed the check and matched an existing shared lesson, so it was retained as independent reinforcement and the evidence count went up.",
        DISCARDED: "The independent verifier judged the lesson UNSAFE. It was discarded entirely and never reached the shared bank.",
        HELD: "The lesson passed the check, but only one engagement shows this unusual pattern. It is held back until a second, unrelated engagement corroborates it.",
        NO_SAFE_LESSON: "No lesson survived generalization while staying useful, so nothing crossed the wall. That's the correct outcome, not a failure.",
        ERROR: w.error || "The pipeline errored.",
      };
      $("#pipeDecision").innerHTML = w.status === "running"
        ? `${st("running", "running")} <span class="muted">Pipeline running for <b>${esc(w.client_name)}</b>…</span>`
        : `<span class="decision-big stamp">${decChip(d)}</span><span>${esc(expl[d] || "")}</span><span class="muted small">${C.time(w.started_at)} → ${C.time(w.finished_at)}</span>`;
      if (!w.recall && !w.candidate) { $("#pipeReview").innerHTML = ""; return; }
      const findings = (ver && ver.layer1 && ver.layer1.findings) || [];
      let ctext = esc(cand.lesson || "");
      findings.forEach((f) => { const m = esc(f.match.split(" … ")[0]); if (m && m.length > 1) ctext = ctext.split(m).join(`<mark class="leak">${m}</mark>`); });
      $("#pipeReview").innerHTML = `
        <div class="panel priv"><div class="priv-banner">${C.icon("lock")} Authorized reviewer view · engagement partner only</div><h3>Private information recalled</h3>
          <p class="muted small">${(w.recall || []).length} memories from the client's own bank. This column never leaves the private side.</p>
          <ul class="mem-list">${(w.recall || []).map((m) => `<li>${esc(m.text)}</li>`).join("")}</ul></div>
        <div class="panel shar"><h3>Generalized lesson candidate</h3><p class="muted small">${esc(cand.engine || "")}</p>
          ${cand.lesson ? `<div class="candidate">${ctext}</div>` : ""}
          ${cand.category ? `<dl class="kv"><dt>Category</dt><dd>${esc(C.human(cand.category))}</dd><dt>Approach</dt><dd>${esc(C.human(cand.approach))}</dd><dt>Outcome</dt><dd>${esc(cand.outcome)}</dd><dt>Why</dt><dd>${esc(cand.why || "")}</dd><dt>Applies when</dt><dd>${esc(cand.conditions || "")}</dd><dt>Scale</dt><dd>${esc(cand.scale || "")}</dd><dt>Rarity</dt><dd>${esc(cand.rarity || "")}</dd></dl>` : ""}
          ${ver ? `<div class="verifier-box"><b>Independent verifier</b> ${st(ver.verdict.toLowerCase(), ver.verdict)}
            <p class="muted small mt-s">Inputs seen: lesson text only (${ver.inputs_seen.lesson_chars} chars) · source client: <b>${esc(ver.inputs_seen.source_client_identity)}</b> · raw notes: <b>${esc(ver.inputs_seen.raw_notes)}</b></p>
            <p class="small mt-s">Layer 1 · ${esc(ver.layer1.engine)} → ${st(ver.layer1.verdict.toLowerCase(), ver.layer1.verdict)}</p>
            ${findings.length ? `<ul class="findings">${findings.map((f) => `<li><b>${esc(f.type)}</b>: “${esc(f.match)}” (${esc(f.why)})</li>`).join("")}</ul>` : ""}
            ${ver.layer2.verdict === "SKIPPED" ? "" : `<p class="small mt-s">Layer 2 · ${esc(ver.layer2.engine)} → ${st(ver.layer2.verdict === "SKIPPED" ? "skipped" : ver.layer2.verdict.toLowerCase(), ver.layer2.verdict)} ${ver.layer2.reason ? esc(ver.layer2.reason) : ""}</p>`}
            <p class="muted small mt-s">A prototype heuristic plus an LLM judge: this reduces risk but does not guarantee confidentiality.</p></div>` : ""}
        </div>`;
    },
    async history() {
      const rows = await api("/api/workflows");
      $("#wfHistory").innerHTML = rows.length ? `<table><thead><tr><th>Engagement</th><th>Decision</th><th>Started</th><th>Finished</th></tr></thead><tbody>${rows.map((r) => `<tr class="clickable" data-w="${r.id}"><td>${esc(r.client_name)}</td><td>${decChip(r.decision) || st(r.status, r.status)}</td><td class="mono">${C.time(r.started_at)}</td><td class="mono">${C.time(r.finished_at)}</td></tr>`).join("")}</tbody></table>` : '<div class="empty">No pipeline runs yet.</div>';
      $$("#wfHistory tr[data-w]").forEach((tr) => tr.addEventListener("click", () => { this.watch(tr.dataset.w); window.scrollTo({ top: $("#pipeTrack").getBoundingClientRect().top + scrollY - 100, behavior: "smooth" }); }));
    },
  };

  // =========================================================== PLAYBOOK
  C.pages.playbook = {
    async show() {
      const qs = new URLSearchParams({ q: $("#pbSearch").value, category: $("#pbCategory").value, approach: $("#pbApproach").value, outcome: $("#pbOutcome").value, strength: $("#pbStrength").value });
      const [r, held] = await Promise.all([api(`/api/playbook?${qs}`), api("/api/playbook/held")]);
      const fill = (sel, vals, label) => { const cur = sel.value; sel.innerHTML = `<option value="">${label}</option>` + vals.map((v) => `<option value="${esc(v)}">${esc(C.human(v))}</option>`).join(""); sel.value = vals.includes(cur) ? cur : ""; };
      fill($("#pbCategory"), r.facets.category, "All topics");
      fill($("#pbApproach"), r.facets.approach, "All approaches");
      fill($("#pbOutcome"), r.facets.outcome, "All outcomes");
      $("#lessonGrid").innerHTML = r.lessons.length ? r.lessons.map((l) => `
        <article class="lesson ${esc(l.status)}" data-id="${l.id}" tabindex="0">
          <div class="lt"><span class="tag tag-cyan">${esc(C.human(l.category))}</span><span class="tag">${esc(C.human(l.approach))}</span>${st(l.outcome === "worked" ? "safe" : l.outcome === "conditional" ? "held" : "unsafe", l.outcome)}${l.status === "synthesis" ? '<span class="tag tag-violet">reconciled</span>' : ""}${l.status === "injected" ? '<span class="tag tag-red">UNVERIFIED · fault injection</span>' : ""}</div>
          <p>${esc(l.text.length > 260 ? l.text.slice(0, 257) + "…" : l.text)}</p>
          <div class="lf"><span>${C.meter(l.evidence_count)} ${esc(l.strength)} evidence · ${l.evidence_count} engagement${l.evidence_count === 1 ? "" : "s"}</span><span>${C.ago(l.updated_at || l.created_at)}</span></div>
        </article>`).join("") : `<div class="empty">No lessons match${r.total ? " these filters" : " yet. Close an engagement to teach the playbook"}.</div>`;
      $$("#lessonGrid .lesson").forEach((a) => { a.addEventListener("click", () => this.open(a.dataset.id)); a.addEventListener("keydown", (e) => e.key === "Enter" && this.open(a.dataset.id)); });
      if (C.hasGsap && !C.reduced) gsap.from("#lessonGrid .lesson", { y: 14, opacity: 0, duration: 0.45, stagger: 0.05, ease: "power2.out" });
      $("#heldList").innerHTML = held.length ? held.map((l) => `<div class="subpanel"><div class="lt" style="display:flex;gap:6px;flex-wrap:wrap">${st("held", "held")}<span class="tag">${esc(C.human(l.category))}</span></div><p class="mt-s">${esc(l.text)}</p><p class="muted small mt-s">${l.evidence_count}/2 engagements · ${esc((l.history[0] || {}).detail || "")}</p></div>`).join("") : '<p class="muted">Nothing held back.</p>';
    },
    async open(id) {
      const l = await api(`/api/playbook/${id}`);
      const ev = { added: "cyan", reinforced: "green", corroborated: "green", contradicted: "amber", revised: "violet", injected: "red", held: "amber" };
      C.drawer(`<h3>Lesson detail</h3>
        <div class="lt" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px"><span class="tag tag-cyan">${esc(C.human(l.category))}</span><span class="tag">${esc(C.human(l.approach))}</span>${st(l.outcome === "worked" ? "safe" : l.outcome === "conditional" ? "held" : "unsafe", l.outcome)}</div>
        <p style="font-size:15.5px;line-height:1.7">${esc(l.text)}</p>
        <dl class="kv mt"><dt>Why</dt><dd>${esc(l.why || "—")}</dd><dt>Applies when</dt><dd>${esc(l.conditions || "—")}</dd><dt>Scale</dt><dd>${esc(l.scale || "—")}</dd>
        <dt>Evidence</dt><dd>${C.meter(l.evidence_count)} <b>${esc(l.strength)}</b> · ${l.evidence_count} independent engagement(s)<br><span class="muted small">Evidence strength = count of independent engagements that passed the gate. It is <b>not</b> measured accuracy.</span></dd></dl>
        <h4 class="mt">Contributing engagements (anonymized)</h4>
        <p class="muted small">Opaque contribution IDs and coarse periods only. The shared side has no link back to client identities.</p>
        <ul class="mem-list">${l.contributions.map((c) => `<li><span class="mono">${esc(c.contrib)}</span> · ${esc(c.kind)} · ${esc(c.period)}</li>`).join("") || "<li>—</li>"}</ul>
        <h4 class="mt">History</h4>
        <ol class="timeline">${l.history.map((h) => `<li><time>${esc(new Date(h.ts).toLocaleString())}</time><b style="color:var(--${{ cyan: "cyan", green: "emerald-l", amber: "amber", violet: "violet-l", red: "red" }[ev[h.event] || "cyan"]})">${esc(h.event)}</b> — ${esc(h.detail)}${h.text ? `<div class="subpanel small">${esc(h.text)}</div>` : ""}</li>`).join("")}</ol>
        ${l.conflict ? `<div class="subpanel mt"><b>Conflict ${esc(l.conflict.id)}</b> · ${st(l.conflict.status === "resolved" ? "done" : "conflict", l.conflict.status)}<p class="small mt-s">${esc(l.conflict.synthesis_text || "Awaiting reconciliation.")}</p><button class="btn btn-ghost btn-sm mt-s" data-close onclick="CCPM.go('conflicts')">Open conflict →</button></div>` : ""}`);
    },
    async inspectShared() {
      const r = await api("/api/playbook-bank/memories");
      C.modal(`<h3>Raw contents of <span class="mono">${esc(r.bank_id)}</span></h3><p class="muted small">Every memory stored in the shared bank. Only generalized lesson text is here: no notes, names or figures.</p><ul class="mem-list mt-s">${r.memories.map((m) => `<li>${esc(m.text)}<small>${esc(m.context || "")}</small></li>`).join("") || "<li>Empty.</li>"}</ul>`);
    },
  };

  // =========================================================== CONSULTANT
  const SUGGEST = {
    shared: ["How should we plan a complex systems migration with many legacy integrations?", "Should we cut over all at once or in phases?", "What should we watch out for when implementing a SaaS platform?", "How do we de-risk a customer-facing pricing change?", "Which client had the migration problem you mentioned?"],
    private: ["What went wrong and what finally worked?", "What were the key decisions and their outcomes?", "Show me the other client's notes on this problem."],
  };
  let chatMode = "shared", session = null, newClients = [];
  const newSession = () => (session = "s-" + Math.random().toString(36).slice(2, 10));
  C.pages.consultant = {
    async show() {
      if (!session) newSession();
      if (!newClients.length) newClients = await api("/api/new-clients");
      await loadEngagements();
      const nc = $("#newClientSel"), pc = $("#privClientSel");
      const cur1 = nc.value, cur2 = pc.value;
      nc.innerHTML = newClients.map((c) => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
      pc.innerHTML = C.state.engagements.map((e) => `<option value="${e.id}">${esc(e.name)}</option>`).join("");
      if (cur1) nc.value = cur1; if (cur2) pc.value = cur2;
      const mc = $("#memClientSel"), cur3 = mc.value;
      mc.innerHTML = C.state.engagements.map((e) => `<option value="${e.id}">${esc(e.name)}</option>`).join("");
      if (cur3) mc.value = cur3;
      this.syncCfg();
      this.memPanel().catch(C.err);
    },
    /** Phase 8: side-by-side view of ONE client's private bank next to the shared playbook bank. */
    async memPanel() {
      const id = $("#memClientSel").value;
      if (!id) return;
      const [priv, shared] = await Promise.all([api(`/api/engagements/${id}/memory`), api("/api/playbook-bank/memories")]);
      const name = $("#memClientSel").selectedOptions[0].textContent;
      $("#memPrivTitle").innerHTML = `${C.icon("lock")} Private bank · ${esc(name)}`;
      $("#memPrivSub").innerHTML = `<span class="mono">${esc(priv.bank_id)}</span> · ${priv.memories.length} raw memories (names, figures, dates, quotes) · client scope only`;
      $("#memPriv").innerHTML = priv.memories.map((m) => `<li>${esc(m.text)}${m.timestamp ? `<small>${esc(m.timestamp)}</small>` : ""}</li>`).join("") || "<li class='muted'>Empty.</li>";
      $("#memSharedSub").innerHTML = `<span class="mono">${esc(shared.bank_id)}</span> · ${shared.memories.length} generalized, verified entries · what new-client advice uses`;
      $("#memShared").innerHTML = shared.memories.map((m) => `<li>${esc(m.text)}</li>`).join("") || "<li class='muted'>No verified lessons yet.</li>";
    },
    syncCfg() {
      $$("#chatMode button").forEach((b) => b.classList.toggle("on", b.dataset.m === chatMode));
      $("#chatSharedCfg").hidden = chatMode !== "shared";
      $("#chatPrivateCfg").hidden = chatMode !== "private";
      const c = newClients.find((x) => x.id === $("#newClientSel").value);
      $("#challenge").innerHTML = c ? `<b>${esc(c.sector)}</b> · ${esc(c.challenge)}` : "";
      $("#suggest").innerHTML = SUGGEST[chatMode].map((s) => `<button type="button">${esc(s)}</button>`).join("");
      $$("#suggest button").forEach((b) => b.addEventListener("click", () => this.ask(b.textContent)));
      const priv = $("#privClientSel").selectedOptions[0];
      $("#chatSrc").innerHTML = chatMode === "shared"
        ? `<span class="src-badge shared"><i class="sdot"></i>Shared Playbook Only</span><span class="muted small">No private bank is reachable from this mode.</span>`
        : `<span class="src-badge private">${C.icon("lock")} Private bank: ${esc(priv ? priv.textContent : "")}</span><span class="muted small">Authorized for this one client only.</span>`;
    },
    setMode(m) { chatMode = m; this.syncCfg(); },
    reset() { newSession(); $("#chatThread").innerHTML = ""; },
    async ask(text, opts = {}) {
      text = (text || "").trim();
      if (!text) return;
      if (window.innerWidth < 980) $(".chat-panel").scrollIntoView({ behavior: C.reduced ? "auto" : "smooth", block: "start" });
      if (opts.mode) this.setMode(opts.mode);
      if (opts.newClientId) { $("#newClientSel").value = opts.newClientId; this.syncCfg(); }
      const th = $("#chatThread");
      th.insertAdjacentHTML("beforeend", `<div class="msg user">${esc(text)}</div><div class="msg bot" id="typing"><span class="typing"><i></i><i></i><i></i></span></div>`);
      th.scrollTop = th.scrollHeight;
      try {
        const r = await post("/api/chat", { session_id: session, message: text, mode: chatMode, client_id: chatMode === "private" ? $("#privClientSel").value : null, new_client_id: chatMode === "shared" ? $("#newClientSel").value : null });
        $("#typing").remove();
        const chips = [
          `<span class="src-badge ${chatMode}">${chatMode === "shared" ? '<i class="sdot"></i>' : C.icon("lock")}${esc(r.memory_source)}</span>`,
          `<span class="tag">${esc(r.engine)}</span>`,
          r.playbook_size != null ? `<span class="tag tag-cyan">playbook: ${r.playbook_size} lessons</span>` : "",
          `<span class="tag">banks: ${esc((r.banks_accessed || []).join(", "))}</span>`,
          (r.extraction_intent || []).length ? `<span class="tag tag-amber" title="${esc(r.extraction_intent.join("; "))}">extraction attempt detected</span>` : "",
          (r.output_filter || []).length ? `<span class="tag tag-red">output filter redacted ${r.output_filter.length}</span>` : "",
          r.refused_access ? `<span class="tag tag-red">cross-bank access refused</span>` : "",
        ].join("");
        const src = (r.sources || []).length ? `<div class="msg-sources"><span class="muted small">Lessons that informed this answer:</span>${r.sources.map((s) => `<details><summary>${esc(C.human(s.approach))} → ${esc(s.outcome)} · ${esc(s.strength)} (${s.evidence_count})${s.status === "synthesis" ? " · reconciled" : ""}</summary><p class="mt-s">${esc(s.text)}</p></details>`).join("")}</div>` : "";
        th.insertAdjacentHTML("beforeend", `<div class="msg bot"><div class="md">${md(r.answer)}</div>${src}<div class="msg-meta">${chips}</div></div>`);
        th.scrollTop = th.scrollHeight;
        this.memPanel().catch(() => {});
        return r;
      } catch (e) {
        const t = $("#typing"); if (t) t.remove();
        th.insertAdjacentHTML("beforeend", `<div class="msg bot" style="border-color:rgba(244,63,94,.5)">${C.icon("alert")} ${esc(e.message)}</div>`);
        C.err(e);
      }
    },
  };

  // =========================================================== LAB
  let labResults = {}, labPrompts = [], labFilter = "all", naiveRes = null;
  C.pages.lab = {
    async show() {
      const r = await api("/api/attacks");
      labPrompts = r.prompts;
      if (r.latest && !Object.keys(labResults).length) r.latest.results.forEach((x) => (labResults[x.test_id] = x));
      await loadEngagements();
      $("#customClient").innerHTML = C.state.engagements.map((e) => `<option value="${e.id}">${esc(e.name)}</option>`).join("");
      this.render();
    },
    render() {
      const vals = Object.values(labResults);
      const passed = vals.filter((x) => x.passed).length;
            $("#labKpis").innerHTML = `
        <div class="kpi shared"><div class="k-label">Pass rate (observed)</div><div class="k-val">${vals.length ? Math.round((100 * passed) / vals.length) + "%" : "—"}</div><div class="k-sub">${passed}/${vals.length} run of ${labPrompts.length}</div></div>
        <div class="kpi private"><div class="k-label">Failed tests</div><div class="k-val">${vals.length - passed}</div><div class="k-sub">leaks detected by the auditor</div></div>
        <div class="kpi violet"><div class="k-label">Naive baseline</div><div class="k-val">${naiveRes ? Math.round((100 * naiveRes.passed) / naiveRes.total) + "%" : "—"}</div><div class="k-sub">${naiveRes ? naiveRes.leaked_terms + " leaked terms" : "not run"}</div></div>
        <div class="kpi"><div class="k-label">Leaked terms</div><div class="k-val">${vals.reduce((a, x) => a + ((x.leaked || []).length), 0)}</div><div class="k-sub">client details found in responses</div></div>`;
      const rows = labPrompts.filter((p) => { const r = labResults[p.id]; return labFilter === "all" || (r && (labFilter === "pass" ? r.passed : !r.passed)); });
      $("#labTests").innerHTML = rows.map((p) => {
        const r = labResults[p.id];
        return `<div class="test ${r ? (r.passed ? "pass" : "fail") : ""}" data-id="${p.id}">
          <div class="test-row"><span class="id">${p.id}</span><span class="cat">${esc(p.category)}${p.mode === "private" ? " · private scope" : ""}</span><span class="pr">${esc(p.prompt)}</span>
            <span>${r ? st(r.passed ? "pass" : "fail", r.passed ? "pass" : "fail") : st("pending", "not run")}</span>
            <button class="btn btn-ghost btn-sm run" data-run="${p.id}">Run</button></div>
          <div class="test-body">${r ? `<p><b>Result:</b> ${esc(r.explanation)}</p>${p.mode === "private" ? `<p class="muted small">Authorized client: ${esc(p.authorized_client)} · attempted target bank: ${esc(p.target_client)}</p>` : ""}<div class="resp md">${md(r.response)}</div><p class="muted small mt-s">engine: ${esc(r.engine)}</p>` : '<p class="muted">Not run yet.</p>'}</div></div>`;
      }).join("") || '<div class="empty">No tests match this filter.</div>';
      $$("#labTests .test-row").forEach((row) => row.addEventListener("click", (e) => { if (!e.target.closest("[data-run]")) row.parentElement.classList.toggle("open"); }));
      $$("#labTests [data-run]").forEach((b) => b.addEventListener("click", () => this.runOne(b.dataset.run, b)));
    },
    async runOne(id, btn) {
      await C.busy(btn, async () => {
        const r = await post("/api/attacks/run", { test_ids: [id] });
        r.results.forEach((x) => (labResults[x.test_id] = x));
        this.render();
        const el = $(`#labTests .test[data-id="${id}"]`); if (el) el.classList.add("open");
      });
    },
    async runAll(btn) {
      return C.busy(btn, async () => {
        const r = await post("/api/attacks/run-all");
        labResults = {}; r.results.forEach((x) => (labResults[x.test_id] = x));
        this.render();
        C.toast(`Suite finished: <b>${r.passed}/${r.total}</b> passed`, r.passed === r.total ? "ok" : "warn");
        return r;
      });
    },
    async runIds(ids) {
      const r = await post("/api/attacks/run", { test_ids: ids });
      r.results.forEach((x) => (labResults[x.test_id] = x));
      this.render();
      ids.forEach((id) => { const el = $(`#labTests .test[data-id="${id}"]`); if (el) el.classList.add("open"); });
      return r;
    },
    async naive(btn) {
      await C.busy(btn, async () => { naiveRes = await post("/api/attacks/naive"); this.render(); C.toast(`Naive pooled-memory baseline: ${naiveRes.passed}/${naiveRes.total} passed, ${naiveRes.leaked_terms} leaked terms`, "warn"); });
    },
    async log() {
      const [rows, acc] = await Promise.all([api("/api/attacks/audit-log?limit=200"), api("/api/access-log?limit=300")]);
      const refused = acc.filter((a) => !a.allowed);
      $("#labLog").innerHTML = `<h3 style="font-size:15px;margin-bottom:10px">Attack audit log</h3><table><thead><tr><th>Time</th><th>Test</th><th>Scope</th><th>Result</th><th>Explanation</th><th>Engine</th></tr></thead><tbody>${rows.map((r) => `<tr><td class="mono">${C.time(r.created_at)}</td><td class="mono">${esc(r.test_id)}</td><td>${esc(r.naive ? "naive baseline" : r.mode)}</td><td>${st(r.passed ? "pass" : "fail", r.passed ? "pass" : "fail")}</td><td>${esc(r.explanation)}</td><td class="muted small">${esc(r.engine)}</td></tr>`).join("") || '<tr><td colspan="6" class="muted">No runs yet.</td></tr>'}</tbody></table>
        <h3 style="font-size:15px;margin:22px 0 10px">Scope gateway refusals</h3><table><thead><tr><th>Time</th><th>Scope</th><th>Bank requested</th><th>Operation</th><th>Caller</th></tr></thead><tbody>${refused.map((a) => `<tr><td class="mono">${C.time(a.ts)}</td><td class="mono">${esc(a.scope)}</td><td class="mono">${esc(a.bank_id)}</td><td>${esc(a.operation)}</td><td>${esc(a.caller)}</td></tr>`).join("") || '<tr><td colspan="5" class="muted">No refused attempts yet.</td></tr>'}</tbody></table>`;
    },
  };

  // =========================================================== CONFLICTS
  C.pages.conflicts = {
    async show() {
      const [list] = await Promise.all([api("/api/conflicts"), loadEngagements()]);
      if (!list.length) {
        const k = C.state.engagements.find((e) => e.id === "kestrel" && e.status === "Active");
        $("#conflictList").innerHTML = `<div class="panel empty"><p>No contradictions in the shared playbook yet.</p>
          <p class="muted small mt-s">Kestrel Aerospace Components (synthetic) has a phased migration that <b>failed</b>, which contradicts the lessons where phasing <b>worked</b>.</p>
          ${k ? '<button class="btn btn-primary btn-sm mt" id="introConflict">Introduce the conflicting engagement</button>' : ""}</div>`;
        const b = $("#introConflict"); if (b) b.onclick = () => C.go("pipeline", { run: "kestrel" });
        return;
      }
      $("#conflictList").innerHTML = list.map((c) => {
        const worked = c.lessons.filter((l) => l.outcome === "worked"), failed = c.lessons.filter((l) => l.outcome !== "worked");
        const side = (l, cls) => `<div class="side ${cls}"><div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px">${st(cls === "worked" ? "safe" : "unsafe", l.outcome)}<span class="tag">${C.meter(l.evidence_count)} ${esc(l.strength)} · ${l.evidence_count}</span></div>${esc(l.text)}<p class="muted small mt-s"><b>Applies when:</b> ${esc(l.conditions || "—")}</p></div>`;
        return `<div class="panel conflict" data-c="${c.id}"><div class="panel-head"><h3>${esc(C.human(c.category))} · approach “${esc(C.human(c.approach))}”</h3>${st(c.status === "resolved" ? "done" : "conflict", c.status === "resolved" ? "reconciled" : "contradiction detected")}</div>
          <div class="conflict-pair"><div>${worked.map((l) => side(l, "worked")).join("")}</div><div class="vs">VS</div><div>${failed.map((l) => side(l, "failed")).join("")}</div></div>
          ${c.synthesis ? `<div class="synth"><span class="tag tag-violet">conditional synthesis · ${esc(c.engine || "")}</span><p class="mt-s" style="font-size:15px;line-height:1.7">${esc(c.synthesis.text)}</p><p class="muted small mt-s">Passed the independent leak check before retention. Original lessons kept as evidence.</p></div>`
            : `<div class="mt"><button class="btn btn-primary btn-sm" data-resolve="${c.id}">Reconcile with reflect</button> <span class="muted small">Produces conditional guidance from the shared lessons only, then leak-checks it.</span></div>`}
          <div class="evo-steps"><b>Evolution:</b><span>1. Universal: “phased works” (${worked.reduce((a, l) => a + l.evidence_count, 0)} eng.)</span>→<span>2. Contradiction (${failed.reduce((a, l) => a + l.evidence_count, 0)} eng.)</span>→<span style="${c.synthesis ? "border-color:rgba(139,92,246,.6)" : "opacity:.5"}">3. Conditional guidance</span></div></div>`;
      }).join("");
      $$("[data-resolve]").forEach((b) => b.addEventListener("click", () => this.resolve(b.dataset.resolve, b)));
    },
    async resolve(id, btn) {
      return C.busy(btn, async () => {
        const r = await post(`/api/conflicts/${id}/resolve`);
        await this.show();
        const s = $(`.conflict[data-c="${id}"] .synth`);
        if (s && C.hasGsap && !C.reduced) gsap.from(s, { y: 18, opacity: 0, scale: 0.98, duration: 0.7, ease: "power3.out" });
        C.toast("Conflict reconciled into conditional guidance", "ok");
        return r;
      });
    },
    async resolveOpen() {
      const list = await api("/api/conflicts");
      const open = list.find((c) => c.status === "open");
      if (open) return this.resolve(open.id, $(`[data-resolve="${open.id}"]`));
      return list[0];
    },
  };

  // =========================================================== METRICS
  C.pages.metrics = {
    async show() {
      const [q, cmp, ov, evo] = await Promise.all([api("/api/metrics/quality"), api("/api/metrics/comparison"), api("/api/metrics/overview"), api("/api/metrics/evolution")]);
      const pts = q.points;
      C.barChart($("#qualityChart"), { bars: pts.map((p) => ({ label: p.note ? "synth" : `after ${p.after_engagements}`, value: p.score, color: p.note ? C.colors.s2 : C.colors.s1, tip: `<b>${p.score}/100</b> after ${p.after_engagements} contributing engagement(s)${p.note ? " + " + p.note : ""}<br>${p.hits.filter((h) => h.hit).length}/${p.hits.length} rubric points · ${p.lessons} lessons` })), max: 100 });
      $("#qualityNote").innerHTML = `Held-out client: <b>${esc(q.client)}</b>. Question: “${esc(q.question)}” ${esc(q.method)}`;
      if (pts.length) {
        const a = pts[0], b = pts[pts.length - 1];
        $("#q1Label").textContent = `rubric ${a.score}/100`;
        $("#qNLabel").textContent = `rubric ${b.score}/100 · after ${b.after_engagements} engagements`;
        $("#qFirst").innerHTML = md(a.advice);
        $("#qLast").innerHTML = md(b.advice);
      } else {
        $("#qFirst").innerHTML = $("#qLast").innerHTML = '<p class="muted">No playbook lessons yet.</p>';
      }
      const iso = cmp.isolated, nv = cmp.naive;
      C.hbars($("#cmpBars"), [
        { label: "Isolated · pass rate", value: iso ? iso.rate : 0, max: 100, color: C.colors.good, text: iso ? `${iso.rate}%` : "not run" },
        { label: "Naive · pass rate", value: nv ? nv.rate : 0, max: 100, color: C.colors.bad, text: nv ? `${nv.rate}%` : "not run" },
        { label: "Isolated · leaked terms", value: iso ? iso.leaked_terms : 0, max: Math.max(1, nv ? nv.leaked_terms : 1), color: C.colors.good, text: iso ? iso.leaked_terms : "—" },
        { label: "Naive · leaked terms", value: nv ? nv.leaked_terms : 0, max: Math.max(1, nv ? nv.leaked_terms : 1), color: C.colors.bad, text: nv ? nv.leaked_terms : "—" },
      ]);
      $("#cmpNote").innerHTML = `${esc(cmp.naive_note)} ${!iso || !nv ? '<button class="link-btn" id="mRunBoth">Run both now →</button>' : ""}`;
      const rb = $("#mRunBoth"); if (rb) rb.onclick = () => C.busy(rb, async () => { await post("/api/attacks/run-all"); await post("/api/attacks/naive"); this.show(); });
      const a = ov.audit;
      $("#auditPanel").innerHTML = `
        <div class="audit-row"><span>Last adversarial suite</span><b>${a.last_run ? `${a.last_run.passed}/${a.last_run.total}` : "not run"}</b></div>
        <div class="audit-row"><span>Shared-playbook queries recorded</span><b>${a.shared_queries}</b></div>
        <div class="audit-row"><span>Private-bank reads during shared queries</span><b style="color:${a.private_bank_reads_during_shared_queries ? "#fb7185" : "#6ee7b7"}">${a.private_bank_reads_during_shared_queries}</b></div>
        <div class="audit-row"><span>Cross-bank requests refused by the gateway</span><b>${a.refused_cross_bank_attempts}</b></div>
        <div class="audit-row"><span>Unverified lessons in shared bank</span><b style="color:${ov.injected_unverified ? "#fb7185" : "#6ee7b7"}">${ov.injected_unverified}</b></div>
        <p class="muted small mt-s">Counts come from the gateway access log and stored attack runs.</p>`;
      $("#evoTimeline").innerHTML = evo.slice().reverse().map((e) => `<li><time>${esc(new Date(e.ts).toLocaleString())}</time>${esc(e.event)} → <b>${e.lesson_count}</b> lessons · ${e.evidence_total} contributions</li>`).join("") || '<li class="muted">No snapshots.</li>';
    },
  };

  // =========================================================== bindings
  C.bindApp = function () {
    $$(".side-nav button").forEach((b) => b.addEventListener("click", () => C.go(b.dataset.page)));
    document.addEventListener("click", (e) => {
      const g = e.target.closest("[data-goto]"); if (g) C.go(g.dataset.goto);
      const r = e.target.closest("[data-refresh]"); if (r) C.refreshAll();
    });
    $("#sidebarToggle").addEventListener("click", () => $("#sidebar").classList.toggle("open"));
    $$("#engFilter button").forEach((b) => b.addEventListener("click", () => { engFilter = b.dataset.f; $$("#engFilter button").forEach((x) => x.classList.toggle("on", x === b)); C.pages.engagements.renderList(); }));
    $("#newEngagementBtn").addEventListener("click", () => C.pages.engagements.newDialog());
    $("#archReplay").addEventListener("click", () => C.pages.architecture.replay());
    $("#pipeRun").addEventListener("click", () => C.pages.pipeline.run());
    let t; const pb = () => { clearTimeout(t); t = setTimeout(() => C.pages.playbook.show().catch(C.err), 200); };
    ["#pbSearch", "#pbCategory", "#pbApproach", "#pbOutcome", "#pbStrength"].forEach((s) => $(s).addEventListener(s === "#pbSearch" ? "input" : "change", pb));
    $("#inspectShared").addEventListener("click", (e) => C.busy(e.currentTarget, () => C.pages.playbook.inspectShared()));
    $$("#chatMode button").forEach((b) => b.addEventListener("click", () => C.pages.consultant.setMode(b.dataset.m)));
    $("#newClientSel").addEventListener("change", () => C.pages.consultant.syncCfg());
    $("#privClientSel").addEventListener("change", () => { C.pages.consultant.reset(); C.pages.consultant.syncCfg(); });
    $("#chatNew").addEventListener("click", () => C.pages.consultant.reset());
    $("#memClientSel").addEventListener("change", () => C.pages.consultant.memPanel().catch(C.err));
    $("#memRefresh").addEventListener("click", () => C.pages.consultant.memPanel().catch(C.err));
    $("#privClientSel").addEventListener("change", () => { $("#memClientSel").value = $("#privClientSel").value; C.pages.consultant.memPanel().catch(C.err); });
    $("#chatForm").addEventListener("submit", (e) => { e.preventDefault(); const v = $("#chatText").value; $("#chatText").value = ""; C.pages.consultant.ask(v); });
    $("#chatText").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#chatForm").requestSubmit(); } });
    $("#labRunAll").addEventListener("click", (e) => C.pages.lab.runAll(e.currentTarget).catch(() => {}));
    $("#labNaive").addEventListener("click", (e) => C.pages.lab.naive(e.currentTarget));
    $("#labInject").addEventListener("click", (e) => C.busy(e.currentTarget, async () => { await post("/api/lab/inject-unsafe"); C.toast("Fault injected: an UNVERIFIED leaky lesson is now in the shared bank. Re-run the suite to see the auditor catch it.", "warn"); }));
    $("#labClear").addEventListener("click", (e) => C.busy(e.currentTarget, async () => { const r = await post("/api/lab/clear-injected"); C.toast(`Removed ${r.removed} injected lesson(s)`, "ok"); }));
    $$("#labFilter button").forEach((b) => b.addEventListener("click", () => { labFilter = b.dataset.f; $$("#labFilter button").forEach((x) => x.classList.toggle("on", x === b)); C.pages.lab.render(); }));
    $$("#labTab button").forEach((b) => b.addEventListener("click", () => {
      $$("#labTab button").forEach((x) => x.classList.toggle("on", x === b));
      $("#labTests").hidden = b.dataset.t !== "tests"; $("#labLog").hidden = b.dataset.t !== "log"; $("#labCustom").hidden = b.dataset.t !== "custom";
      $("#labFilter").style.visibility = b.dataset.t === "tests" ? "visible" : "hidden";
      if (b.dataset.t === "log") C.pages.lab.log().catch(C.err);
    }));
    $("#customForm").addEventListener("submit", (e) => { e.preventDefault(); C.busy(e.submitter, async () => {
      const r = await post("/api/attacks/custom", { prompt: $("#customPrompt").value, mode: $("#customMode").value, authorized_client: $("#customMode").value === "private" ? $("#customClient").value : null });
      $("#customResult").innerHTML = `<div class="test ${r.passed ? "pass" : "fail"} open mt"><div class="test-body" style="display:block;padding:14px"><p>${st(r.passed ? "pass" : "fail", r.passed ? "pass" : "fail")} ${esc(r.explanation)}</p><div class="resp md">${md(r.response)}</div></div></div>`;
    }); });
    $("#mSeed").addEventListener("click", (e) => C.busy(e.currentTarget, async () => { const r = await post("/api/seed"); await C.waitJob(r.job_id); C.toast("Synthetic engagements seeded", "ok"); C.state.currentWf = null; C.refreshAll(); }));
    $("#mReset").addEventListener("click", (e) => C.busy(e.currentTarget, async () => { const r = await post("/api/reset"); await C.waitJob(r.job_id); labResults = {}; naiveRes = null; C.state.currentWf = null; C.pages.consultant.reset(); C.toast("Demo reset to the seeded state", "ok"); C.refreshAll(); }));
    $("#mCloseAll").addEventListener("click", (e) => C.busy(e.currentTarget, async () => { const r = await post("/api/demo/close-all"); await C.waitJob(r.job_id, (m) => C.toast(esc(m))); C.toast("All engagements closed & conflicts reconciled", "ok"); C.refreshAll(); }));
  };
  C.resetLab = () => { labResults = {}; naiveRes = null; };
})();
