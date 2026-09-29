/* Core utilities: API client, router, UI helpers. Exposes window.CCPM */
(function () {
  const C = (window.CCPM = window.CCPM || {});
  C.reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  C.hasGsap = typeof window.gsap !== "undefined";
  C.state = { mode: null, page: "overview", selectedEng: null, engagements: [], currentWf: null };

  // ---------------------------------------------------------------- API
  C.api = async function (path, opts = {}) {
    const init = { method: opts.method || "GET", headers: {} };
    if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
      if (!opts.method) init.method = "POST";
    }
    if (opts.method === "POST" && opts.body === undefined) init.body = "{}", (init.headers["Content-Type"] = "application/json");
    let res;
    try {
      res = await fetch(path, init);
    } catch (e) {
      throw new Error("Network error — is the server running?");
    }
    let data = null;
    try { data = await res.json(); } catch (_) { /* non-json */ }
    if (!res.ok) {
      let msg = (data && (data.error || data.detail)) || res.statusText;
      if (Array.isArray(msg)) msg = msg.map((d) => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join("; ");
      const err = new Error(msg);
      err.status = res.status;
      throw err;
    }
    return data;
  };
  C.post = (p, body) => C.api(p, { method: "POST", body });

  C.waitJob = async function (jobId, onLog) {
    for (let i = 0; i < 1800; i++) {
      const j = await C.api(`/api/jobs/${jobId}`);
      if (onLog && j.log && j.log.length && j.log.length !== C._lastLogLen) { C._lastLogLen = j.log.length; onLog(j.log[j.log.length - 1].msg); }
      if (j.status !== "running") {
        if (j.status === "failed") throw new Error(j.error || "Job failed");
        return j;
      }
      await C.sleep(400);
    }
    throw new Error("Job timed out");
  };

  // ---------------------------------------------------------------- helpers
  C.sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  C.$ = (s, r = document) => r.querySelector(s);
  C.$$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  C.esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  C.time = (ts) => {
    if (!ts) return "";
    const d = new Date(ts);
    if (isNaN(d)) return ts;
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };
  C.ago = (ts) => {
    const s = (Date.now() - new Date(ts).getTime()) / 1000;
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return new Date(ts).toLocaleDateString();
  };
  C.human = (s) => String(s || "").replace(/[-_]/g, " ");
  C.st = (status, label) => `<span class="st st-${C.esc(String(status).toLowerCase())}">${C.esc(label || C.human(status))}</span>`;
  C.meter = (n) => `<span class="meter" title="${n} independent engagement(s)">${[1, 2, 3].map((i) => `<i class="${n >= i ? "on" : ""}"></i>`).join("")}</span>`;

  C.md = function (src) {
    const lines = C.esc(src || "").split(/\n/);
    let html = "", inList = 0;
    const inline = (t) => t.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/(^|[^*])\*(?!\s)(.+?)\*/g, "$1<em>$2</em>").replace(/_(.+?)_/g, "<em>$1</em>").replace(/`(.+?)`/g, "<code>$1</code>");
    const close = (to) => { while (inList > to) { html += "</ul>"; inList--; } };
    for (const raw of lines) {
      const m = raw.match(/^(\s*)[-*]\s+(.*)$/);
      if (m) {
        const depth = m[1].length >= 2 ? 2 : 1;
        if (inList < depth) { while (inList < depth) { html += "<ul>"; inList++; } }
        else close(depth);
        html += `<li>${inline(m[2])}</li>`;
      } else {
        close(0);
        const h = raw.match(/^#{1,4}\s+(.*)$/);
        if (h) html += `<p><strong>${inline(h[1])}</strong></p>`;
        else if (raw.trim()) html += `<p>${inline(raw)}</p>`;
      }
    }
    close(0);
    return html;
  };

  C.toast = function (msg, kind = "") {
    const t = document.createElement("div");
    t.className = `toast ${kind}`;
    t.innerHTML = msg;
    C.$("#toasts").appendChild(t);
    setTimeout(() => { t.style.transition = "opacity .4s"; t.style.opacity = "0"; setTimeout(() => t.remove(), 400); }, kind === "err" ? 6500 : 3800);
  };
  C.err = (e) => C.toast(`<b>Error:</b> ${C.esc(e.message || e)}`, "err");

  C.busy = async function (btn, fn) {
    if (btn) { btn.disabled = true; btn.classList.add("loading"); }
    try { return await fn(); }
    catch (e) { C.err(e); throw e; }
    finally { if (btn) { btn.disabled = false; btn.classList.remove("loading"); } }
  };

  C.modal = function (html) {
    C.$("#modalBody").innerHTML = html;
    C.$("#modal").hidden = false;
    return C.$("#modalBody");
  };
  C.drawer = function (html) {
    C.$("#drawerBody").innerHTML = html;
    C.$("#drawer").hidden = false;
    return C.$("#drawerBody");
  };
  C.closeOverlays = () => { ["#modal", "#drawer"].forEach((id) => { const el = C.$(id); if (el) el.hidden = true; }); };
  document.addEventListener("click", (e) => {
    if (e.target.matches("[data-close]") || e.target.id === "modal" || e.target.id === "drawer") C.closeOverlays();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") C.closeOverlays(); });

  C.countUp = function (el, to, opts = {}) {
    const from = parseFloat(el.dataset.v || "0") || 0;
    el.dataset.v = to;
    const suffix = opts.suffix || "";
    if (C.reduced || !C.hasGsap || from === to) { el.textContent = to + suffix; return; }
    const o = { v: from };
    gsap.to(o, { v: to, duration: opts.duration || 1.1, ease: "power3.out", onUpdate: () => (el.textContent = Math.round(o.v) + suffix) });
  };

  // ---------------------------------------------------------------- router
  C.pages = {};
  C.go = function (page, opts = {}) {
    if (!C.pages[page]) page = "overview";
    const changed = C.state.page !== page || !C._booted;
    C._booted = true;
    C.state.page = page;
    C.$$(".side-nav button").forEach((b) => b.classList.toggle("active", b.dataset.page === page));
    C.$$(".app-main > .page").forEach((p) => p.classList.toggle("active", p.dataset.page === page));
    const sb = C.$("#sidebar"); if (sb) sb.classList.remove("open");
    if (history.replaceState) history.replaceState(null, "", `${location.pathname}${location.search}#/${page}`);
    if (changed && opts.scroll !== false) window.scrollTo({ top: 0, behavior: "instant" });
    let r;
    try { r = C.pages[page].show && C.pages[page].show(opts); } catch (e) { C.err(e); }
    if (changed) Promise.resolve(r).catch(() => {}).then(() => C.animatePage(page));
  };

  // staggered entrance for the cards of a freshly shown page
  C.animatePage = function (page) {
    if (!C.hasGsap || C.reduced) return;
    const root = C.$(`.app-main > .page[data-page="${page}"]`);
    if (!root) return;
    const items = C.$$(":scope > .page-head, :scope > * > .panel, :scope > .panel, :scope > .kpis > .kpi, :scope > .grid-2 > .panel, :scope > .grid-3 > .panel", root);
    gsap.fromTo(items, { y: 18, opacity: 0 }, { y: 0, opacity: 1, duration: 0.55, ease: "power3.out", stagger: 0.045, clearProps: "transform,opacity" });
  };

  // ---------------------------------------------------------------- icons (inline SVG, no emoji)
  const ICONS = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    folders: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    network: '<rect x="2" y="3" width="6" height="5" rx="1"/><rect x="2" y="16" width="6" height="5" rx="1"/><rect x="16" y="9.5" width="6" height="5" rx="1"/><path d="M8 5.5h3v13H8M11 12h5"/>',
    flow: '<path d="M3 12h4l3-6 4 12 3-6h4"/>',
    book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5M8 7h7M8 11h7"/>',
    chat: '<path d="M4 5h16v11H9l-5 4z"/>',
    shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="M9 12l2 2 4-4"/>',
    swap: '<path d="M4 8h14l-4-4M20 16H6l4 4"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    play: '<path d="M7 5l12 7-12 7z"/>',
    refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 5v6h-6"/>',
    rotate: '<path d="M4 13a8 8 0 1 0 2.3-5.7M4 5v6h6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
    arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
    check: '<path d="M5 12l5 5 9-10"/>',
  };
  C.icon = (name, cls = "") => `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ""}</svg>`;
  C.hydrateIcons = (root = document) => C.$$("i[data-icon]", root).forEach((i) => { if (!i.dataset.done) { i.innerHTML = C.icon(i.dataset.icon); i.dataset.done = 1; } });

  // ---------------------------------------------------------------- page-to-page transition (landing <-> dashboard)
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-nav]");
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
    const veil = C.$("#pageVeil");
    if (!veil || C.reduced) return;
    e.preventDefault();
    veil.classList.add("leaving");
    setTimeout(() => (location.href = a.href), 280);
  });
  window.addEventListener("pageshow", () => { const v = C.$("#pageVeil"); if (v) v.classList.remove("leaving"); });

  // ---------------------------------------------------------------- pointer-tracked border glow on cards
  document.addEventListener("pointermove", (e) => {
    const card = e.target.closest && e.target.closest(".panel, .kpi, .lesson, .story-card, .how-step, .cabinet, .eng-item, .test");
    if (!card) return;
    const r = card.getBoundingClientRect();
    card.style.setProperty("--mx", `${e.clientX - r.left}px`);
    card.style.setProperty("--my", `${e.clientY - r.top}px`);
  }, { passive: true });

  // ---------------------------------------------------------------- mode
  C.loadMode = async function () {
    const m = await C.api("/api/mode");
    C.state.mode = m;
    const live = m.mode === "live";
    return m;
  };

  C.refreshAll = function () {
    const p = C.pages[C.state.page];
    if (p && p.show) p.show({ refresh: true });
    C.refreshLandingCounts && C.refreshLandingCounts();
  };
})();
