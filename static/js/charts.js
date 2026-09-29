/* Small dependency-free SVG charts with hover tooltips. */
(function () {
  const C = window.CCPM;
  const NS = "http://www.w3.org/2000/svg";
  const S1 = "#0ea5c6", S2 = "#8b5cf6";
  C.colors = { s1: S1, s2: S2, s3: "#d97706", good: "#10b981", bad: "#f43f5e", warn: "#f59e0b" };

  function tipFor(el) {
    let t = el.querySelector(".chart-tip");
    if (!t) { t = document.createElement("div"); t.className = "chart-tip"; el.appendChild(t); }
    return t;
  }
  function niceMax(v) {
    if (v <= 5) return Math.max(1, Math.ceil(v));
    const p = Math.pow(10, Math.floor(Math.log10(v)));
    return Math.ceil(v / p) * p;
  }

  /** Step/line chart. series: [{name,color,values:[number]}], labels: [string] (x categories), tipLabels: [string] */
  C.lineChart = function (el, { series, labels, tips, height = 240, yMax }) {
    el.innerHTML = "";
    if (!labels.length) { el.innerHTML = '<div class="empty">No data yet.</div>'; return; }
    const legend = document.createElement("div");
    legend.className = "chart-legend";
    legend.innerHTML = series.map((s) => `<span><i style="background:${s.color}"></i>${C.esc(s.name)}</span>`).join("");
    el.appendChild(legend);
    const W = 640, H = height, m = { l: 34, r: 56, t: 12, b: 26 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const raw = yMax || Math.max(1, ...series.flatMap((s) => s.values));
    const stepV = raw <= 5 ? 1 : raw <= 10 ? 2 : raw <= 25 ? 5 : niceMax(raw) / 4;
    const max = Math.ceil(raw / stepV) * stepV;
    const n = labels.length;
    const x = (i) => m.l + (n === 1 ? iw / 2 : (i / (n - 1)) * iw);
    const y = (v) => m.t + ih - (v / max) * ih;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    let g = `<g class="grid">`;
    const ticks = Math.round(max / stepV);
    for (let i = 0; i <= ticks; i++) {
      const v = (max / ticks) * i;
      g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y(v)}" y2="${y(v)}"/>`;
    }
    g += `</g><g class="axis">`;
    for (let i = 0; i <= ticks; i++) { const v = (max / ticks) * i; g += `<text x="${m.l - 8}" y="${y(v) + 4}" text-anchor="end">${Math.round(v)}</text>`; }
    const step = Math.max(1, Math.ceil(n / 7));
    labels.forEach((l, i) => { if (i % step === 0 || i === n - 1) g += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle">${C.esc(l)}</text>`; });
    g += `</g>`;
    series.forEach((s) => {
      let d = "";
      s.values.forEach((v, i) => { d += i === 0 ? `M${x(i)},${y(v)}` : ` H${x(i)} V${y(v)}`; });
      const area = d + ` V${y(0)} H${x(0)} Z`;
      g += `<path d="${area}" fill="${s.color}" opacity="0.08"/>`;
      g += `<path class="ln" d="${d}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linejoin="round"/>`;
      const last = s.values.length - 1;
      g += `<circle cx="${x(last)}" cy="${y(s.values[last])}" r="4.5" fill="${s.color}" stroke="#0f1629" stroke-width="2"/>`;
      g += `<text x="${x(last) + 9}" y="${y(s.values[last]) + 4}" fill="#a7b1c6" font-size="11" font-family="JetBrains Mono, monospace">${s.values[last]}</text>`;
    });
    g += `<line class="xh" x1="0" x2="0" y1="${m.t}" y2="${m.t + ih}" stroke="rgba(148,163,184,.35)" stroke-dasharray="3 3" opacity="0"/>`;
    g += `<rect class="hit" x="${m.l - 10}" y="${m.t}" width="${iw + 20}" height="${ih}" fill="transparent"/>`;
    svg.innerHTML = g;
    el.appendChild(svg);
    // animate lines
    if (C.hasGsap && !C.reduced) {
      svg.querySelectorAll(".ln").forEach((p) => {
        const len = p.getTotalLength();
        gsap.fromTo(p, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, duration: 1.2, ease: "power2.out" });
      });
    }
    const tip = tipFor(el), xh = svg.querySelector(".xh"), hit = svg.querySelector(".hit");
    hit.addEventListener("mousemove", (ev) => {
      const r = svg.getBoundingClientRect();
      const px = ((ev.clientX - r.left) / r.width) * W;
      const i = Math.max(0, Math.min(n - 1, Math.round(n === 1 ? 0 : ((px - m.l) / iw) * (n - 1))));
      xh.setAttribute("x1", x(i)); xh.setAttribute("x2", x(i)); xh.setAttribute("opacity", 1);
      tip.innerHTML = `<b>${C.esc((tips && tips[i]) || labels[i])}</b><br>` + series.map((s) => `<i class="tip-key" style="background:${s.color}"></i> ${C.esc(s.name)}: <b>${s.values[i]}</b>`).join("<br>");
      tip.style.left = `${(x(i) / W) * r.width}px`;
      tip.style.top = `${(y(Math.max(...series.map((s) => s.values[i]))) / H) * r.height + legend.offsetHeight}px`;
      tip.classList.add("on");
    });
    hit.addEventListener("mouseleave", () => { tip.classList.remove("on"); xh.setAttribute("opacity", 0); });
  };

  /** Vertical bars. bars: [{label, value, tip}] */
  C.barChart = function (el, { bars, max = 100, color = S1, height = 240, suffix = "" }) {
    el.innerHTML = "";
    if (!bars.length) { el.innerHTML = '<div class="empty">No data yet — close engagements to build the curve.</div>'; return; }
    const W = 640, H = height, m = { l: 34, r: 10, t: 22, b: 30 };
    const iw = W - m.l - m.r, ih = H - m.t - m.b;
    const bw = Math.min(56, (iw / bars.length) * 0.62), gap = iw / bars.length;
    const y = (v) => m.t + ih - (v / max) * ih;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    let g = `<g class="grid">`;
    [0, 25, 50, 75, 100].forEach((v) => (g += `<line x1="${m.l}" x2="${W - m.r}" y1="${y((v / 100) * max)}" y2="${y((v / 100) * max)}"/>`));
    g += `</g><g class="axis">`;
    [0, 50, 100].forEach((v) => (g += `<text x="${m.l - 8}" y="${y((v / 100) * max) + 4}" text-anchor="end">${Math.round((v / 100) * max)}</text>`));
    bars.forEach((b, i) => (g += `<text x="${m.l + gap * i + gap / 2}" y="${H - 8}" text-anchor="middle">${C.esc(b.label)}</text>`));
    g += `</g>`;
    bars.forEach((b, i) => {
      const bx = m.l + gap * i + (gap - bw) / 2, h = Math.max(2, (b.value / max) * ih);
      const col = b.color || color;
      g += `<g class="bar" data-i="${i}"><rect class="hitb" x="${m.l + gap * i}" y="${m.t}" width="${gap}" height="${ih}" fill="transparent"/>`;
      g += `<path class="bf" d="M${bx},${y(0)} V${y(0) - h + 4} Q${bx},${y(0) - h} ${bx + 4},${y(0) - h} H${bx + bw - 4} Q${bx + bw},${y(0) - h} ${bx + bw},${y(0) - h + 4} V${y(0)} Z" fill="${col}" style="transform-origin:${bx + bw / 2}px ${y(0)}px"/>`;
      if (i === 0 || i === bars.length - 1) g += `<text x="${bx + bw / 2}" y="${y(0) - h - 7}" text-anchor="middle" fill="#e7ecf6" font-size="12" font-weight="600">${b.value}${suffix}</text>`;
      g += `</g>`;
    });
    svg.innerHTML = g;
    el.appendChild(svg);
    if (C.hasGsap && !C.reduced) gsap.from(svg.querySelectorAll(".bf"), { scaleY: 0, duration: 0.8, ease: "power3.out", stagger: 0.06 });
    const tip = tipFor(el);
    svg.querySelectorAll(".bar").forEach((gEl) => {
      gEl.addEventListener("mouseenter", () => {
        const b = bars[+gEl.dataset.i];
        const r = svg.getBoundingClientRect();
        tip.innerHTML = b.tip || `${C.esc(b.label)}: <b>${b.value}${suffix}</b>`;
        tip.style.left = `${((m.l + gap * +gEl.dataset.i + gap / 2) / W) * r.width}px`;
        tip.style.top = `${(y(b.value) / H) * r.height}px`;
        tip.classList.add("on");
        gEl.querySelector(".bf").setAttribute("opacity", "0.85");
      });
      gEl.addEventListener("mouseleave", () => { tip.classList.remove("on"); gEl.querySelector(".bf").removeAttribute("opacity"); });
    });
  };

  /** Horizontal labeled bars. rows: [{label, value, max, color, text}] */
  C.hbars = function (el, rows) {
    el.innerHTML = rows.map((r) => `<div class="hbar" title="${C.esc(r.title || "")}"><span>${C.esc(r.label)}</span><div class="track"><div class="fill" style="background:${r.color}" data-w="${r.max ? Math.round((100 * r.value) / r.max) : 0}"></div></div><span class="v">${C.esc(r.text != null ? r.text : r.value)}</span></div>`).join("");
    requestAnimationFrame(() => C.$$(".fill", el).forEach((f) => (f.style.width = f.dataset.w + "%")));
  };
})();
