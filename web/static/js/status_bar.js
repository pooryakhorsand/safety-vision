/* ==========================================================================
   status_bar.js — keeps the bottom status bar up to date.
     - clock: every second (browser time)
     - engine / GPU memory / FPS: polled from /api/system/status/ every 5 seconds
   The URL and translated labels come from data-* attributes on #status-bar.
   ========================================================================== */

(function () {
  "use strict";

  const POLL_INTERVAL_MS = 5000;

  const bar = document.getElementById("status-bar");
  if (!bar) return;

  const clock = document.getElementById("clock");
  const engineDot = document.getElementById("engine-dot");
  const engineLabel = document.getElementById("engine-label");
  const gpuValue = document.getElementById("gpu-value");
  const fpsValue = document.getElementById("fps-value");

  const labels = {
    online: bar.dataset.labelOnline,
    offline: bar.dataset.labelOffline,
    error: bar.dataset.labelError,
  };

  function updateClock() {
    clock.textContent = new Date().toLocaleTimeString("en-GB", { hour12: false });
  }

  function setEngineState(state) {
    const safeState = labels[state] ? state : "offline";
    const dotClass = { online: "online", offline: "offline", error: "alarm" }[safeState];
    engineDot.className = "status-dot status-dot--" + dotClass;
    engineLabel.textContent = labels[safeState];
  }

  async function pollStatus() {
    try {
      const response = await fetch(bar.dataset.statusUrl, { headers: { Accept: "application/json" } });
      if (response.redirected || !response.ok) throw new Error("status " + response.status);
      const data = await response.json();
      setEngineState(data.engine && data.engine.state);
      gpuValue.textContent = data.gpu && data.gpu.memory_percent != null ? data.gpu.memory_percent + "%" : "—";
      fpsValue.textContent = data.fps != null ? Math.round(data.fps) : "—";
      // Other scripts (live tiles) listen to this instead of polling again.
      document.dispatchEvent(new CustomEvent("engine-status", { detail: data }));
    } catch (error) {
      // Web server unreachable or session expired: show as offline.
      setEngineState("offline");
      document.dispatchEvent(new CustomEvent("engine-status", { detail: null }));
    }
  }

  updateClock();
  setInterval(updateClock, 1000);

  pollStatus();
  setInterval(pollStatus, POLL_INTERVAL_MS);
})();
