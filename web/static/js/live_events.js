/* ==========================================================================
   live_events.js — keeps every live alarm indicator up to date.
   Polls /api/events/summary/ every few seconds and updates, when present:
     - navbar bell             #alarm-count            (open events)
     - module sidebar counters [data-module-count=KEY] (open events per module)
     - overview cards          [data-today-count=KEY]  (events today per module)
     - latest events strip     #event-strip-list
     - camera tiles            .camera-tile.has-alarm  (ongoing open violation)
   Settings come from data-* attributes on #live-events (app_shell.html).
   Later this polling can be replaced by a WebSocket without touching the HTML.
   ========================================================================== */

(function () {
  "use strict";

  const POLL_INTERVAL_MS = 5000;

  const config = document.getElementById("live-events");
  if (!config) return;

  const grid = document.getElementById("camera-grid");
  const activeModule = grid ? grid.dataset.activeModule || "" : "";
  const summaryUrl = config.dataset.summaryUrl + (activeModule ? "?module=" + encodeURIComponent(activeModule) : "");
  const labels = {
    ongoing: config.dataset.labelOngoing,
    open: config.dataset.labelOpen,
    empty: config.dataset.labelEmpty,
  };

  function setText(element, value) {
    if (element && element.textContent !== String(value)) element.textContent = value;
  }

  function updateBell(total) {
    setText(document.getElementById("alarm-count"), total);
    const bell = document.querySelector(".alarm-counter");
    if (bell) bell.classList.toggle("has-alarms", total > 0);
  }

  function updateCounters(attribute, counts) {
    document.querySelectorAll("[" + attribute + "]").forEach((element) => {
      const value = counts[element.getAttribute(attribute)] || 0;
      setText(element, value);
      element.classList.toggle("has-alarms", attribute === "data-module-count" && value > 0);
    });
  }

  function updateTiles(cameraIds) {
    const alarmed = new Set(cameraIds.map(String));
    document.querySelectorAll(".camera-tile[data-camera-id]").forEach((tile) => {
      tile.classList.toggle("has-alarm", alarmed.has(tile.dataset.cameraId));
    });
  }

  /* Build one row of the latest-events strip with DOM methods (no innerHTML: data is never parsed as HTML). */
  function buildRow(item) {
    const row = document.createElement("li");
    row.className = "event-strip__item severity--" + item.severity;

    const link = document.createElement("a");
    link.href = item.url;

    const time = document.createElement("span");
    time.className = "event-strip__time";
    time.dir = "ltr";
    time.textContent = item.time;

    const dot = document.createElement("span");
    dot.className = "severity-dot";

    const type = document.createElement("span");
    type.className = "event-strip__type";
    type.textContent = item.type;

    const where = document.createElement("span");
    where.className = "event-strip__where";
    where.dir = "ltr";
    where.textContent = item.camera + (item.track_id !== null ? "  #" + item.track_id : "");

    link.append(time, dot, type, where);

    if (item.is_ongoing || item.is_open) {
      const badge = document.createElement("span");
      badge.className = "badge " + (item.is_ongoing ? "badge--alarm" : "badge--warn");
      badge.textContent = item.is_ongoing ? labels.ongoing : labels.open;
      link.append(badge);
    }
    row.append(link);
    return row;
  }

  function updateStrip(items) {
    const list = document.getElementById("event-strip-list");
    if (!list) return;
    const signature = JSON.stringify(items);
    if (list.dataset.signature === signature) return;      // nothing changed: no flicker
    list.dataset.signature = signature;

    list.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("li");
      empty.className = "event-strip__empty";
      empty.textContent = labels.empty;
      list.append(empty);
      return;
    }
    items.forEach((item) => list.append(buildRow(item)));
  }

  async function poll() {
    try {
      const response = await fetch(summaryUrl, { headers: { Accept: "application/json" } });
      if (response.redirected || !response.ok) return;     // session expired: leave the page as is
      const data = await response.json();
      updateBell(data.open_total);
      updateCounters("data-module-count", data.open_by_module);
      updateCounters("data-today-count", data.today_by_module);
      updateTiles(data.alarm_camera_ids);
      updateStrip(data.latest);
    } catch (error) {
      /* network hiccup: try again on the next tick */
    }
  }

  poll();
  setInterval(poll, POLL_INTERVAL_MS);
})();
