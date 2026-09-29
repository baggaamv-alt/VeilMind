/* Animated visualizations: hero flow, scroll diagram, architecture network.
   Design rule: every shape stands for something (a bank, the gate, the playbook). No decorative circles. */
(function () {
  const C = window.CCPM;
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}, parent) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  };
  const canAnimate = () => C.hasGsap && !C.reduced;
  const LOCK = (x, y, s = 1, color = "#fb7185") =>
    `<g transform="translate(${x},${y}) scale(${s})" fill="none" stroke="${color}" stroke-width="1.6" stroke-linecap="round"><rect x="-5" y="-1" width="10" height="8" rx="1.6"/><path d="M-3 -1v-2.4a3 3 0 0 1 6 0V-1"/></g>`;
  const SHIELD = (cx, cy, s) => `M${cx} ${cy - 30 * s} L${cx + 24 * s} ${cy - 20 * s} V${cy + 2 * s} C${cx + 24 * s} ${cy + 18 * s} ${cx + 12 * s} ${cy + 27 * s} ${cx} ${cy + 32 * s} C${cx - 12 * s} ${cy + 27 * s} ${cx - 24 * s} ${cy + 18 * s} ${cx - 24 * s} ${cy + 2 * s} V${cy - 20 * s} Z`;

  /** A light "comet" that travels along an existing path. stopAt < 1 stops early (blocked) and fades. */
  function comet(svg, path, { color = "#22d3ee", width = 2.4, seg = 34, dur = 1.6, stopAt = 1, layer } = {}) {
    return new Promise((resolve) => {
      if (!canAnimate() || !path) return resolve();
      const len = path.getTotalLength();
      const c = el("path", { d: path.getAttribute("d"), fill: "none", stroke: color, "stroke-width": width, "stroke-linecap": "round", class: "streak" }, layer || svg);
      c.style.strokeDasharray = `${seg} ${len + seg}`;
      c.style.strokeDashoffset = seg;
      c.style.filter = `drop-shadow(0 0 4px ${color})`;
      gsap.to(c, {
        strokeDashoffset: seg - len * stopAt, duration: dur * stopAt, ease: stopAt < 1 ? "power2.in" : "power1.inOut",
        onComplete: () => gsap.to(c, { opacity: 0, duration: stopAt < 1 ? 0.35 : 0.2, onComplete: () => { c.remove(); resolve(); } }),
      });
    });
  }
  C.comet = comet;

  function onVisible(node, cb) {
    let on = true;
    if ("IntersectionObserver" in window) new IntersectionObserver((es) => (on = es[0].isIntersecting)).observe(node);
    return () => on && !document.hidden && cb();
  }

  // ------------------------------------------------------------------ hero
  C.initHeroFlow = function () {
    const svg = C.$("#heroFlow");
    if (!svg) return;
    svg.innerHTML = `<defs>
      <linearGradient id="hfGate" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#8b5cf6"/></linearGradient>
      <clipPath id="hfShield"><path d="${SHIELD(330, 220, 1.25)}"/></clipPath></defs>`;
    const G = { x: 330, y: 220 }, P = { x: 400, y: 145, w: 146, h: 160 };
    const base = el("g", {}, svg), fx = el("g", {}, svg), top = el("g", {}, svg);
    // wall
    el("line", { x1: G.x, x2: G.x, y1: 18, y2: 422, stroke: "#f43f5e", "stroke-width": 1, "stroke-dasharray": "3 6", opacity: 0.5 }, base);
    el("text", { x: G.x + 8, y: 30, class: "node-label", fill: "#fb7185" }, base).textContent = "confidentiality wall";
    el("text", { x: 24, y: 30, class: "node-label" }, base).textContent = "private banks";
    // client vaults
    const names = ["Client A", "Client B", "Client C", "Client D", "Client E"];
    const paths = names.map((n, i) => {
      const y = 62 + i * 76;
      const g = el("g", { class: "vault" }, top);
      g.innerHTML = `<rect x="24" y="${y - 20}" width="104" height="40" rx="9" fill="#050505" stroke="rgba(244,63,94,.45)"/>
        ${LOCK(44, y - 2, 1.1)}<text x="60" y="${y - 1}" class="node-title" font-size="12">${n}</text><text x="60" y="${y + 12}" class="node-label" font-size="9.5">raw notes</text>`;
      return el("path", { d: `M128 ${y} C 220 ${y}, 230 ${G.y}, ${G.x - 30} ${G.y}`, class: "flow-path" }, base);
    });
    const out = el("path", { d: `M${G.x + 30} ${G.y} L ${P.x} ${G.y}`, class: "flow-path lit" }, base);
    // gate (shield) with a scanning line inside
    const gate = el("path", { d: SHIELD(G.x, G.y, 1.25), fill: "#050505", stroke: "url(#hfGate)", "stroke-width": 1.8 }, top);
    const scan = el("rect", { x: G.x - 32, y: G.y - 40, width: 64, height: 2, fill: "#22d3ee", opacity: 0.7, "clip-path": "url(#hfShield)" }, top);
    el("path", { d: `M${G.x - 8} ${G.y + 2} l6 6 l11 -12`, fill: "none", stroke: "#e7ecf6", "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round" }, top);
    el("text", { x: G.x, y: G.y + 62, "text-anchor": "middle", class: "node-title" }, top).textContent = "Leak check";
    el("text", { x: G.x, y: G.y + 77, "text-anchor": "middle", class: "node-label" }, top).textContent = "sees lesson text only";
    // playbook card whose rows fill in as lessons arrive
    const pb = el("g", {}, top);
    const pbRect = el("rect", { x: P.x, y: P.y, width: P.w, height: P.h, rx: 12, fill: "#050505", stroke: "rgba(16,185,129,.55)" }, pb);
    el("text", { x: P.x + 14, y: P.y + 24, class: "node-title", "font-size": 12.5 }, pb).textContent = "Shared playbook";
    el("line", { x1: P.x + 14, x2: P.x + P.w - 14, y1: P.y + 34, y2: P.y + 34, stroke: "rgba(148,163,184,.18)" }, pb);
    const rows = el("g", {}, pb);
    el("text", { x: 230, y: 30, "text-anchor": "middle", class: "node-label" }, base).textContent = "reflect: one lesson each";
    let n = 0;
    function addRow() {
      const kids = Array.from(rows.children);
      if (kids.length >= 6) { const r = kids[0]; gsap.to(r, { opacity: 0, duration: 0.3, onComplete: () => r.remove() }); }
      Array.from(rows.children).forEach((r) => gsap.to(r, { y: "-=16", duration: 0.45, ease: "power3.out" }));
      const w = 50 + ((n++ * 37) % 44);
      const r = el("rect", { x: P.x + 14, y: P.y + 136, width: w, height: 5, rx: 2.5, fill: n % 3 ? "#34d399" : "#22d3ee" }, rows);
      gsap.fromTo(r, { attr: { width: 0 }, opacity: 0 }, { attr: { width: w }, opacity: 0.85, duration: 0.6, ease: "power3.out" });
      gsap.fromTo(pbRect, { attr: { stroke: "rgba(52,211,153,1)" } }, { attr: { stroke: "rgba(16,185,129,.55)" }, duration: 0.9 });
    }
    if (!canAnimate()) { for (let i = 0; i < 4; i++) { const w = 50 + i * 12; el("rect", { x: P.x + 14, y: P.y + 64 + i * 16, width: w, height: 5, rx: 2.5, fill: "#34d399", opacity: 0.8 }, rows); } return; }
    for (let i = 0; i < 4; i++) setTimeout(addRow, 1200 + i * 200);
    gsap.fromTo(scan, { attr: { y: G.y - 40 } }, { attr: { y: G.y + 38 }, duration: 1.8, ease: "sine.inOut", repeat: -1, yoyo: true });
    let k = 0;
    const tick = onVisible(svg, async () => {
      const p = paths[k++ % paths.length];
      const blocked = Math.random() < 0.3;
      if (blocked) {
        await comet(svg, p, { color: "#f43f5e", stopAt: 0.97, dur: 1.5, layer: fx });
        gsap.fromTo(gate, { attr: { stroke: "#f43f5e", "stroke-width": 3 } }, { attr: { stroke: "url(#hfGate)", "stroke-width": 1.8 }, duration: 0.8 });
      } else {
        await comet(svg, p, { dur: 1.5, layer: fx });
        gsap.fromTo(gate, { attr: { stroke: "#34d399", "stroke-width": 3 } }, { attr: { stroke: "url(#hfGate)", "stroke-width": 1.8 }, duration: 0.8 });
        await comet(svg, out, { color: "#34d399", seg: 22, dur: 0.5, layer: fx });
        addRow();
      }
    });
    setInterval(tick, 900);
  };

  // ------------------------------------------------------------------ how-it-works diagram (scroll-scrubbed)
  C.initHowDiagram = function () {
    const svg = C.$("#howDiagram");
    if (!svg) return;
    const nodes = [
      { y: 60, t: "Private bank", s: "raw notes · one per client", c: "#f43f5e" },
      { y: 200, t: "Distill (reflect)", s: "exactly one lesson", c: "#22d3ee" },
      { y: 340, t: "Independent check", s: "re-identification test", c: "#8b5cf6" },
      { y: 470, t: "Shared playbook", s: "verified lessons only", c: "#10b981" },
    ];
    let h = "";
    for (let i = 0; i < 3; i++) h += `<path class="how-track" d="M210 ${nodes[i].y + 32} V ${nodes[i + 1].y - 32}"/><path class="how-seg" d="M210 ${nodes[i].y + 32} V ${nodes[i + 1].y - 32}" stroke="${nodes[i + 1].c}"/>`;
    nodes.forEach((n, i) => {
      h += `<g class="how-node" data-i="${i}"><rect x="70" y="${n.y - 32}" width="280" height="64" rx="12" fill="#050505" stroke="${n.c}" stroke-opacity=".55"/>
        <rect x="90" y="${n.y - 6}" width="12" height="12" rx="3" fill="${n.c}"/>
        <text x="118" y="${n.y - 3}" class="node-title">${n.t}</text><text x="118" y="${n.y + 15}" class="node-label">${n.s}</text></g>`;
    });
    h += `<path d="M350 340 H 390" stroke="#f43f5e" stroke-dasharray="3 4"/><text x="394" y="336" class="node-label" fill="#fb7185">UNSAFE</text><text x="394" y="350" class="node-label" fill="#fb7185">discarded</text>`;
    svg.innerHTML = h;
    const segs = C.$$(".how-seg", svg), steps = C.$$(".how-step"), gs = C.$$(".how-node", svg);
    const setStep = (k) => {
      steps.forEach((s, i) => s.classList.toggle("on", i === k));
      gs.forEach((g, i) => g.classList.toggle("lit", i <= k + 1));
    };
    segs.forEach((s) => { const L = s.getTotalLength(); s.style.strokeDasharray = L; s.style.strokeDashoffset = canAnimate() ? L : 0; });
    if (canAnimate() && window.ScrollTrigger) {
      steps.forEach((st, i) => {
        ScrollTrigger.create({ trigger: st, start: "top 60%", end: "bottom 40%", onToggle: (self) => self.isActive && setStep(i) });
        gsap.to(segs[i], { strokeDashoffset: 0, ease: "none", scrollTrigger: { trigger: st, start: "top 75%", end: "center 45%", scrub: true } });
      });
      setStep(0);
    } else setStep(2);
  };

  // ------------------------------------------------------------------ architecture network
  C.renderArchitecture = function (data, onSelect, selected) {
    const svg = C.$("#archSvg");
    const banks = data.client_banks;
    const n = banks.length;
    const DIST = { x: 470, y: 280 }, GATE = { x: 640, y: 280 }, PLAY = { x: 780, y: 200, w: 180, h: 150 }, VER = { x: 640, y: 470 }, NEW = { x: 870, y: 470 };
    const rowY = (i) => 280 + (n === 1 ? 0 : ((2 * i) / (n - 1) - 1) * Math.min(235, 29 * (n - 1)));
    const color = (b) => {
      if (b.status !== "Closed") return "#22d3ee";
      if (["RETAINED", "REINFORCED"].includes(b.decision)) return "#8b5cf6";
      if (b.decision === "HELD") return "#f59e0b";
      return "#f43f5e";
    };
    let h = `<defs><linearGradient id="agGate" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="#22d3ee"/><stop offset="1" stop-color="#8b5cf6"/></linearGradient>
      <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="#64748b"/></marker></defs>`;
    h += `<line x1="${GATE.x}" x2="${GATE.x}" y1="24" y2="540" stroke="#f43f5e" stroke-dasharray="3 6" stroke-opacity=".5"/>`;
    h += `<text x="${GATE.x - 12}" y="38" text-anchor="end" class="node-label" fill="#fb7185">PRIVATE SIDE</text><text x="${GATE.x + 12}" y="38" class="node-label" fill="#6ee7b7">SHARED SIDE</text>`;
    banks.forEach((b, i) => {
      const y = rowY(i);
      h += `<path id="ap${i}" class="flow-path" d="M236 ${y} C 340 ${y}, ${DIST.x - 110} ${DIST.y}, ${DIST.x - 44} ${DIST.y}"/>`;
    });
    h += `<path id="apDG" class="flow-path lit" d="M${DIST.x + 44} ${DIST.y} L ${GATE.x - 30} ${GATE.y}"/>`;
    h += `<path id="apGP" class="flow-path lit" d="M${GATE.x + 30} ${GATE.y} C ${GATE.x + 70} ${GATE.y}, ${PLAY.x - 50} ${PLAY.y + PLAY.h / 2}, ${PLAY.x} ${PLAY.y + PLAY.h / 2}"/>`;
    h += `<path class="flow-path" d="M${GATE.x} ${GATE.y + 42} V ${VER.y - 24}" stroke-dasharray="3 5"/>`;
    h += `<path class="flow-path lit" d="M${PLAY.x + PLAY.w / 2} ${PLAY.y + PLAY.h} C ${PLAY.x + PLAY.w / 2} ${NEW.y - 60}, ${NEW.x} ${NEW.y - 70}, ${NEW.x} ${NEW.y - 26}" marker-end="url(#arr)"/>`;
    banks.forEach((b, i) => {
      const y = rowY(i), c = color(b);
      const nm = b.name.length > 24 ? b.name.slice(0, 23) + "…" : b.name;
      h += `<g class="arch-node ${selected === b.id ? "sel" : ""}" data-id="${b.id}" tabindex="0" role="button" aria-label="Inspect ${C.esc(b.name)} private bank">
        <rect class="node-ring" x="36" y="${y - 16}" width="200" height="32" rx="8" fill="#050505" stroke="${c}" stroke-opacity=".6"/>
        <rect x="36" y="${y - 16}" width="4" height="32" rx="2" fill="${c}"/>
        ${LOCK(54, y - 2, 0.95, c)}
        <text x="68" y="${y + 4}" class="node-label" fill="#e7ecf6" font-size="11">${C.esc(nm)}</text>
        <text x="226" y="${y + 4}" text-anchor="end" fill="${c}" font-size="10.5" font-family="JetBrains Mono, monospace">${b.memories}</text></g>`;
    });
    h += `<g><rect id="archDist" x="${DIST.x - 44}" y="${DIST.y - 30}" width="88" height="60" rx="12" fill="#050505" stroke="#22d3ee" stroke-width="1.6"/>
      <path d="M${DIST.x - 16} ${DIST.y - 12} H${DIST.x + 16} L${DIST.x + 4} ${DIST.y + 2} V${DIST.y + 13} L${DIST.x - 4} ${DIST.y + 9} V${DIST.y + 2} Z" fill="none" stroke="#67e8f9" stroke-width="1.6" stroke-linejoin="round"/>
      <text x="${DIST.x}" y="${DIST.y + 52}" text-anchor="middle" class="node-title">Distillation</text>
      <text x="${DIST.x}" y="${DIST.y + 67}" text-anchor="middle" class="node-label">reflect · client scope only</text></g>`;
    h += `<g><path id="archGate" d="${SHIELD(GATE.x, GATE.y, 1.25)}" fill="#050505" stroke="url(#agGate)" stroke-width="1.8"/>
      <path d="M${GATE.x - 8} ${GATE.y + 2} l6 6 l11 -12" fill="none" stroke="#e7ecf6" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      <text x="${GATE.x}" y="${GATE.y - 52}" text-anchor="middle" class="node-title">Verification gate</text></g>`;
    h += `<g><rect x="${VER.x - 72}" y="${VER.y - 22}" width="144" height="44" rx="10" fill="#050505" stroke="#475569" stroke-dasharray="4 4"/>
      <text x="${VER.x}" y="${VER.y - 3}" text-anchor="middle" class="node-label">leak-verifier bank</text><text x="${VER.x}" y="${VER.y + 12}" text-anchor="middle" class="node-label" fill="#94a3b8">isolated · always empty</text></g>`;
    const shown = Math.min(6, data.playbook.lessons);
    let rows = "";
    for (let i = 0; i < shown; i++) rows += `<rect x="${PLAY.x + 16}" y="${PLAY.y + 74 + i * 11}" width="${60 + ((i * 41) % 80)}" height="4" rx="2" fill="${i % 3 ? "#34d399" : "#22d3ee"}" opacity=".85" class="pb-row"/>`;
    h += `<g><rect id="archPlay" x="${PLAY.x}" y="${PLAY.y}" width="${PLAY.w}" height="${PLAY.h}" rx="14" fill="#050505" stroke="#10b981" stroke-width="1.6"/>
      <text x="${PLAY.x + 16}" y="${PLAY.y + 26}" class="node-title">firm-playbook</text>
      <text x="${PLAY.x + PLAY.w - 16}" y="${PLAY.y + 28}" text-anchor="end" fill="#6ee7b7" font-size="22" font-family="Space Grotesk" font-weight="700">${data.playbook.lessons}</text>
      <text x="${PLAY.x + 16}" y="${PLAY.y + 46}" class="node-label">verified lessons</text>${rows}</g>`;
    h += `<g><rect x="${NEW.x - 82}" y="${NEW.y - 22}" width="164" height="44" rx="10" fill="#050505" stroke="#22d3ee" stroke-opacity=".5"/>
      <text x="${NEW.x}" y="${NEW.y - 3}" text-anchor="middle" class="node-title" font-size="12">New client query</text><text x="${NEW.x}" y="${NEW.y + 12}" text-anchor="middle" class="node-label">shared playbook only</text></g>`;
    svg.innerHTML = h;
    C.$$(".arch-node", svg).forEach((g) => {
      g.addEventListener("click", () => onSelect(g.dataset.id));
      g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(g.dataset.id); } });
    });
    if (canAnimate()) {
      gsap.from(C.$$(".arch-node", svg), { x: -24, opacity: 0, duration: 0.6, ease: "expo.out", stagger: 0.04 });
      gsap.from(C.$$(".pb-row", svg), { attr: { width: 0 }, duration: 0.8, ease: "power3.out", stagger: 0.06, delay: 0.3 });
    }
    const flash = (node, col) => canAnimate() && node && gsap.fromTo(node, { attr: { "stroke-width": 3.4 }, stroke: col }, { attr: { "stroke-width": 1.8 }, stroke: "", duration: 0.9, clearProps: "stroke" });
    return {
      async replay() {
        if (!canAnimate()) return;
        const closed = banks.map((b, i) => ({ b, i })).filter((x) => x.b.status === "Closed");
        for (const { b, i } of closed) {
          const ok = ["RETAINED", "REINFORCED"].includes(b.decision), held = b.decision === "HELD";
          (async () => {
            await comet(svg, svg.querySelector(`#ap${i}`), { color: "#f43f5e", dur: 1.2, seg: 26 });
            flash(svg.querySelector("#archDist"), "#22d3ee");
            if (b.decision === "NO_SAFE_LESSON") return;
            const col = ok ? "#22d3ee" : held ? "#f59e0b" : "#f43f5e";
            await comet(svg, svg.querySelector("#apDG"), { color: col, dur: 0.6, seg: 22 });
            flash(svg.querySelector("#archGate"), ok ? "#34d399" : col);
            if (!ok) return;
            await comet(svg, svg.querySelector("#apGP"), { color: "#34d399", dur: 0.8, seg: 26 });
            flash(svg.querySelector("#archPlay"), "#34d399");
          })();
          await C.sleep(380);
        }
      },
    };
  };
})();
