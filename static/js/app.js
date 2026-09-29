/* Veilmind dashboard bootstrap (served at /app). */
(function () {
  const C = window.CCPM;
  const { $, $$ } = C;

  // keeps the "open conflicts" badge in the sidebar current (called after pipeline runs / resets)
  C.refreshLandingCounts = async function () {
    try {
      const ov = await C.api("/api/metrics/overview");
      const n = $(".side-nav button[data-page='conflicts']");
      if (!n) return;
      const old = n.querySelector(".badge-count"); if (old) old.remove();
      if (ov.conflicts.open) n.insertAdjacentHTML("beforeend", `<span class="badge-count">${ov.conflicts.open}</span>`);
    } catch (_) { /* ignore */ }
  };

  window.addEventListener("hashchange", () => {
    const m = location.hash.match(/^#\/(\w+)/);
    if (m && m[1] !== C.state.page) C.go(m[1]);
  });

  async function boot() {
    C.hydrateIcons();
    C.bindApp();
    // re-hydrate icons whenever pages inject markup that contains them
    new MutationObserver(() => C.hydrateIcons()).observe($(".app"), { childList: true, subtree: true });
    try { await C.loadMode(); } catch (e) { C.toast("Backend not reachable. Start the server with <code>uvicorn app.main:app</code>.", "err"); }
    if (C.hasGsap && !C.reduced) {
      gsap.from(".sidebar", { x: -30, opacity: 0, duration: 0.7, ease: "expo.out" });
      gsap.from(".side-nav button", { x: -14, opacity: 0, duration: 0.5, ease: "power3.out", stagger: 0.035, delay: 0.1 });
    }
    const m = location.hash.match(/^#\/(\w+)/);
    C.go(m ? m[1] : "overview");
    C.refreshLandingCounts();
    if (new URLSearchParams(location.search).get("demo") === "1") {
      C.go("consultant");
      C.demo.open();
    }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
})();
