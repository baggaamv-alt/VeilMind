/* Guided demo: seven steps that drive the real app pages and real API calls. */
(function () {
  const C = window.CCPM;
  const { $, $$, esc, api, post } = C;
  const Q = "How should we plan a complex systems migration with many legacy integrations?";
  const ctx = { before: null, after: null };
  let cur = 0, busy = false;

  const focus = (sel) => { const e = $(sel); if (e) { e.classList.remove("demo-focus"); void e.offsetWidth; e.classList.add("demo-focus"); setTimeout(() => e.classList.remove("demo-focus"), 4500); } };
  const status = (t, err) => { const s = $("#demoStatus"); s.innerHTML = t; s.classList.toggle("err", !!err); };
  async function firstActive(prefer) {
    const list = await api("/api/engagements");
    for (const id of prefer) { const e = list.find((x) => x.id === id && x.status === "Active"); if (e) return e; }
    return null;
  }

  const STEPS = [
    {
      t: "A new client asks for migration advice",
      d: "Ridgeway Freight Rail (a new, fictional client) is replacing a legacy dispatch system with dozens of integrations. The consultant opens the AI consultant in Shared Playbook Only mode.",
      run: async () => {
        C.go("consultant");
        await C.pages.consultant.show();
        C.pages.consultant.reset();
        C.pages.consultant.setMode("shared");
        $("#newClientSel").value = "ridgeway"; C.pages.consultant.syncCfg();
        $("#chatText").value = Q;
        focus("#chatForm");
        status("Question drafted. The memory source is <b>Shared Playbook Only</b>, so no private bank is reachable.");
      },
    },
    {
      t: "The assistant answers from the current shared playbook",
      d: "The answer uses only generalized, verified lessons. Right now the playbook has learned from a single closed engagement.",
      run: async () => {
        C.go("consultant");
        $("#chatText").value = "";
        ctx.before = await C.pages.consultant.ask(Q, { mode: "shared", newClientId: "ridgeway" });
        if (!ctx.before) throw new Error("No answer");
        focus("#chatThread");
        status(`Answered from <b>${ctx.before.playbook_size}</b> shared lesson(s). Banks accessed: <span class="mono">${esc(ctx.before.banks_accessed.join(", "))}</span>.`);
      },
    },
    {
      t: "Close an earlier engagement: private → generalized",
      d: "Close a past warehouse-system engagement. The pipeline recalls its private history, distills exactly one lesson, and shows the private notes next to the generalized lesson in an authorized review screen.",
      run: async () => {
        const e = await firstActive(["tessaract", "mariposa", "bluefin", "orchardlane"]);
        if (!e) { status("All example engagements are already closed. Restart the demo to replay this step.", true); return; }
        C.go("pipeline");
        status(`Running the learning pipeline for <b>${esc(e.name)}</b>…`);
        const w = await C.pages.pipeline.run(e.id);
        focus("#pipeReview");
        status(`Decision: <b>${esc(w.decision)}</b>. Compare the private notes (left) with the generalized lesson (right).`);
      },
    },
    {
      t: "The independent verification gate",
      d: "The verifier sees only the lesson text, with no client identity and no notes. Next we close a utility engagement whose draft lesson keeps an identifying industry + location + deadline combination. Watch the gate reject it.",
      run: async () => {
        const e = await firstActive(["sablepoint"]);
        C.go("pipeline");
        if (!e) { status("That engagement is already closed. Its run is in the workflow history.", true); return; }
        status("Closing the utility engagement…");
        const w = await C.pages.pipeline.run(e.id);
        focus("#pipeReview");
        const reasons = (w.verification && w.verification.reasons) || [];
        status(`Gate verdict: <b>${esc(w.verification ? w.verification.verdict : "?")}</b> → <b>${esc(w.decision)}</b>. ${reasons.length} identifying signal(s) found; the lesson never reached the shared bank.`);
      },
    },
    {
      t: "Ask the same question again: the advice improves",
      d: "Same new client, same question. The playbook now has more independent evidence, but it still contains no raw client data.",
      run: async () => {
        C.go("consultant");
        ctx.after = await C.pages.consultant.ask(Q, { mode: "shared", newClientId: "ridgeway" });
        focus("#chatThread");
        const b = ctx.before, a = ctx.after;
        const ev = (r) => (r.sources || []).reduce((s, x) => s + (x.status === "synthesis" ? 0 : x.evidence_count), 0);
        status(b ? `Evidence behind the answer: <b>${ev(b)}</b> → <b>${ev(a)}</b> engagement contributions. Answer length ${b.answer.length} → ${a.answer.length} chars. <button class="link-btn" id="demoCmp">Compare side by side</button>` : "Answered.");
        const cmp = $("#demoCmp");
        if (cmp) cmp.onclick = () => C.modal(`<h3>Before vs after</h3><div class="grid-2"><div class="panel"><h4>Before</h4><div class="advice md">${C.md(b.answer)}</div></div><div class="panel"><h4>After</h4><div class="advice md">${C.md(a.answer)}</div></div></div>`);
      },
    },
    {
      t: "Try to extract another client's secrets",
      d: "Run adversarial prompts: attribution, urgency pressure, claimed authorization, and a cross-client request from an authorized private session.",
      run: async () => {
        C.go("lab");
        await C.pages.lab.show();
        status("Running attacks A03, A09, A11, A15…");
        const r = await C.pages.lab.runIds(["A03", "A09", "A11", "A15"]);
        focus("#labTests");
        status(`Observed result: <b>${r.passed}/${r.total}</b> passed the leak audit. The shared layer has nothing to give.`, r.passed !== r.total);
      },
    },
    {
      t: "Contradicting evidence arrives: guidance evolves",
      d: "An aerospace plant's phased migration failed because its modules were too interdependent. The playbook detects the contradiction and reconciles it into conditional guidance, keeping both pieces of evidence.",
      run: async () => {
        const e = await firstActive(["kestrel"]);
        if (e) {
          C.go("pipeline");
          status("Closing the contradicting engagement…");
          await C.pages.pipeline.run(e.id);
        }
        C.go("conflicts");
        await C.pages.conflicts.show();
        status("Reconciling with reflect…");
        const c = await C.pages.conflicts.resolveOpen();
        focus("#conflictList");
        status(c && c.synthesis_text ? "Reconciled. The shared guidance is now conditional, and the original evidence is preserved. Demo complete." : "Conflict view updated.");
      },
    },
  ];

  function render() {
    const s = STEPS[cur];
    $("#demoStepNo").textContent = `Step ${cur + 1} of ${STEPS.length}`;
    $("#demoTitle").textContent = s.t;
    $("#demoDesc").textContent = s.d;
    $("#demoProgress").innerHTML = STEPS.map((_, i) => `<button class="${i < cur ? "done" : i === cur ? "cur" : ""}" data-i="${i}" aria-label="Go to step ${i + 1}"></button>`).join("");
    $$("#demoProgress button").forEach((b) => b.addEventListener("click", () => { cur = +b.dataset.i; status(""); render(); }));
    $("#demoPrev").disabled = cur === 0;
    $("#demoNext").disabled = cur === STEPS.length - 1;
    const act = $("#demoAct");
    act.textContent = s.done ? "Run again" : "Run step";
  }

  async function act() {
    if (busy) return;
    busy = true;
    const btn = $("#demoAct");
    btn.disabled = true; btn.classList.add("loading");
    try {
      await STEPS[cur].run();
      STEPS[cur].done = true;
      if (cur < STEPS.length - 1) $("#demoNext").classList.add("btn-primary");
    } catch (e) {
      status(esc(e.message || e), true);
    } finally {
      busy = false; btn.disabled = false; btn.classList.remove("loading");
      render();
    }
  }

  C.demo = {
    open() {
      $("#demoDock").hidden = false;
      render();
      if (!STEPS[cur].done && cur === 0) status("Press <b>Run step</b> to perform each step with real API calls.");
    },
    close() { $("#demoDock").hidden = true; },
    async restart() {
      const b = $("#demoRestart");
      b.disabled = true;
      status("Resetting data to the seeded state…");
      try {
        const r = await post("/api/reset");
        await C.waitJob(r.job_id);
        STEPS.forEach((s) => (s.done = false));
        ctx.before = ctx.after = null;
        C.state.currentWf = null;
        C.resetLab && C.resetLab();
        C.pages.consultant.reset();
        cur = 0;
        status("Reset complete. Press <b>Run step</b> to begin.");
        C.refreshAll();
      } catch (e) { status(esc(e.message), true); }
      b.disabled = false;
      render();
    },
  };

  document.addEventListener("click", (e) => { if (e.target.closest("[data-start-demo]")) { e.preventDefault(); C.go("consultant"); C.demo.open(); } });
  $("#demoAct").addEventListener("click", act);
  $("#demoNext").addEventListener("click", () => { if (cur < STEPS.length - 1) { cur++; $("#demoNext").classList.remove("btn-primary"); status(""); render(); } });
  $("#demoPrev").addEventListener("click", () => { if (cur > 0) { cur--; status(""); render(); } });
  $("#demoClose").addEventListener("click", () => C.demo.close());
  $("#demoRestart").addEventListener("click", () => C.demo.restart());
})();
