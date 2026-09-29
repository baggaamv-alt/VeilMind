/* Veilmind landing page: motion + live counters. The dashboard lives at /app. */
(function () {
  const C = window.CCPM;
  const { $, $$ } = C;
  const motion = C.hasGsap && window.ScrollTrigger && !C.reduced;

  // smooth in-page anchors
  document.addEventListener("click", (e) => {
    const a = e.target.closest("a[data-scroll]");
    if (!a) return;
    const t = document.querySelector(a.getAttribute("href"));
    if (!t) return;
    e.preventDefault();
    window.scrollTo({ top: t.getBoundingClientRect().top + window.scrollY - 70, behavior: C.reduced ? "auto" : "smooth" });
  });

  // nav: solid after scrolling, hides while scrolling down, returns when scrolling up
  let lastY = 0;
  window.addEventListener("scroll", () => {
    const y = window.scrollY, nav = $("#topnav");
    nav.classList.toggle("scrolled", y > 10);
    nav.classList.toggle("hide", y > 400 && y > lastY);
    lastY = y;
    if (!motion) { const max = document.documentElement.scrollHeight - innerHeight; $("#scrollProgress").style.transform = `scaleX(${max > 0 ? y / max : 0})`; }
  }, { passive: true });

  // split headings into masked words
  function splitWords(el) {
    const words = el.textContent.trim().split(/\s+/);
    el.setAttribute("aria-label", el.textContent.trim());
    el.innerHTML = words.map((w) => `<span class="wm" aria-hidden="true"><span class="w">${C.esc(w)}</span></span>`).join(" ");
    return $$(".w", el);
  }

  function scenes() {
    gsap.registerPlugin(ScrollTrigger);
    // hero: word-by-word masked rise, then copy, then the diagram unveils left to right
    $$(".hero-title .line").forEach((l) => l.classList.add("masked"));
    const tl = gsap.timeline({ defaults: { ease: "expo.out" } });
    tl.from(".hero-title .w", { yPercent: 115, rotate: 4, duration: 1.1, stagger: 0.06 })
      .from("[data-hero]", { y: 22, opacity: 0, duration: 0.9, stagger: 0.08 }, "-=0.75")
      .fromTo("[data-hero-visual]", { clipPath: "inset(0 100% 0 0 round 20px)", opacity: 0.4 }, { clipPath: "inset(0 0% 0 0 round 20px)", opacity: 1, duration: 1.3, ease: "power4.inOut" }, "-=1.1");
    gsap.to("#scrollProgress", { scaleX: 1, ease: "none", scrollTrigger: { start: 0, end: "max", scrub: 0.2 } });
    // headings
    $$(".split-reveal").forEach((h) => {
      const ws = splitWords(h);
      gsap.from(ws, { yPercent: 110, duration: 0.9, ease: "expo.out", stagger: 0.035, scrollTrigger: { trigger: h, start: "top 85%" } });
    });
    $$(".section .eyebrow").forEach((e) => gsap.from(e, { opacity: 0, x: -12, duration: 0.6, scrollTrigger: { trigger: e, start: "top 88%" } }));
    // cards rise with a slight depth tilt
    $$(".cabinet-grid, .story-grid").forEach((g) => {
      gsap.from(g.querySelectorAll(".stagger-card"), { y: 60, opacity: 0, rotateX: -8, transformOrigin: "50% 100%", duration: 1, ease: "expo.out", stagger: 0.12, scrollTrigger: { trigger: g, start: "top 80%" } });
    });
    gsap.from(".cabinet-arrow", { opacity: 0, x: -20, duration: 0.8, scrollTrigger: { trigger: ".cabinet-grid", start: "top 75%" } });
    gsap.from(".how-step", { x: -30, opacity: 0, duration: 0.9, ease: "expo.out", stagger: 0.1, scrollTrigger: { trigger: ".how-steps", start: "top 80%" } });
    gsap.from(".entry-card", { y: 50, opacity: 0, duration: 1, ease: "expo.out", scrollTrigger: { trigger: ".entry-card", start: "top 85%" } });
    // the hero diagram drifts up slightly as you leave the hero
    gsap.to("[data-hero-visual]", { y: -40, ease: "none", scrollTrigger: { trigger: ".hero", start: "top top", end: "bottom top", scrub: true } });
    // background grid fades as the page goes on
    gsap.to(".grid-bg", { opacity: 0.25, ease: "none", scrollTrigger: { trigger: "#cabinets", start: "top bottom", end: "#entry top", scrub: true } });
  }

  async function counts() {
    try {
      const ov = await C.api("/api/metrics/overview");
      const set = (k, v) => $$(`[data-count="${k}"]`).forEach((el) => C.countUp(el, v, { duration: 1.6 }));
      set("engagements", ov.engagements.total);
      set("lessons", ov.verified_lessons);
      set("blocked", ov.blocked_lessons);
    } catch (_) { /* backend offline: counters stay at 0 */ }
  }

  function boot() {
    C.hydrateIcons();
    C.initHeroFlow();
    C.initHowDiagram();
    if (motion) {
      try { scenes(); } catch (e) { console.warn("motion disabled", e); }
    }
    setTimeout(counts, motion ? 900 : 0);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
