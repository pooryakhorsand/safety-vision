/* ==========================================================================
   camera_grid.js — behaviour of the live camera grid.
     - layout buttons: whatever the server rendered (e.g. 1 / 2 for two cameras)
     - paging when there are more cameras than tiles
     - expand one camera (button or double-click), Esc to go back
     - remembers the chosen layout in this browser (localStorage)
   ========================================================================== */

(function () {
  "use strict";

  const STORAGE_KEY = "live.gridLayout";

  const grid = document.getElementById("camera-grid");
  if (!grid) return;

  const tiles = Array.from(grid.querySelectorAll(".camera-tile"));
  const layoutButtons = Array.from(document.querySelectorAll(".segmented__btn[data-layout]"));
  // Available layouts come from the buttons the server rendered.
  const LAYOUTS = layoutButtons.map((button) => Number(button.dataset.layout));
  const DEFAULT_LAYOUT = Number(grid.dataset.defaultLayout) || LAYOUTS[LAYOUTS.length - 1] || 1;
  const pager = document.getElementById("grid-pager");
  const pageLabel = document.getElementById("grid-page-label");

  const state = {
    layout: DEFAULT_LAYOUT,
    page: 0,
    expandedTile: null,
  };

  /* ---- Storage (may be blocked in some browsers, so always guarded) ---- */
  function loadLayout() {
    try {
      const saved = parseInt(localStorage.getItem(STORAGE_KEY), 10);
      if (LAYOUTS.includes(saved)) return saved;
    } catch (error) { /* ignore */ }
    // Default (decided by the server): the smallest layout that shows every camera.
    return DEFAULT_LAYOUT;
  }

  function saveLayout(size) {
    try { localStorage.setItem(STORAGE_KEY, String(size)); } catch (error) { /* ignore */ }
  }

  /* ---- Rendering ---- */
  function pageCount() {
    return Math.max(1, Math.ceil(tiles.length / state.layout));
  }

  function render() {
    if (state.expandedTile) {
      grid.classList.add("is-expanded");
      tiles.forEach((tile) => { tile.hidden = tile !== state.expandedTile; });
      pager.hidden = true;
      return;
    }

    grid.classList.remove("is-expanded");
    grid.dataset.layout = String(state.layout);

    const first = state.page * state.layout;
    const last = first + state.layout;
    tiles.forEach((tile, index) => { tile.hidden = index < first || index >= last; });

    pager.hidden = pageCount() <= 1;
    pageLabel.textContent = (state.page + 1) + " / " + pageCount();

    layoutButtons.forEach((button) => {
      const isActive = Number(button.dataset.layout) === state.layout;
      button.classList.toggle("is-active", isActive);
      button.setAttribute("aria-pressed", String(isActive));
    });
  }

  /* ---- Actions ---- */
  function setLayout(size) {
    state.layout = size;
    state.page = 0;
    state.expandedTile = null;
    saveLayout(size);
    render();
  }

  function changePage(step) {
    const pages = pageCount();
    state.page = (state.page + step + pages) % pages;
    render();
  }

  function toggleExpand(tile) {
    state.expandedTile = state.expandedTile === tile ? null : tile;
    render();
    if (state.expandedTile) tile.focus();
  }

  /* ---- Events ---- */
  layoutButtons.forEach((button) => {
    button.addEventListener("click", () => setLayout(Number(button.dataset.layout)));
  });

  pager.addEventListener("click", (event) => {
    const button = event.target.closest("[data-page]");
    if (button) changePage(button.dataset.page === "next" ? 1 : -1);
  });

  tiles.forEach((tile) => {
    tile.querySelector('[data-action="expand"]').addEventListener("click", () => toggleExpand(tile));
    tile.addEventListener("dblclick", () => toggleExpand(tile));
    tile.addEventListener("keydown", (event) => {
      if (event.key === "Enter") toggleExpand(tile);
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.expandedTile) {
      const tile = state.expandedTile;
      state.expandedTile = null;
      render();
      tile.focus();
    }
  });

  /* ---- Live status + stream (status_bar.js polls and broadcasts "engine-status") ---- */
  function updateTile(tile, info) {
    const id = tile.dataset.cameraId;
    const online = Boolean(info && info.online);
    const dot = tile.querySelector(".status-dot");
    const fps = tile.querySelector(".camera-tile__fps");
    const mode = tile.querySelector(".camera-tile__mode");
    const img = tile.querySelector(".camera-tile__stream");
    const placeholder = tile.querySelector(".camera-tile__placeholder");

    dot.className = "status-dot status-dot--" + (online ? "online" : "offline");
    dot.title = online ? grid.dataset.labelOnline : grid.dataset.labelOffline;
    fps.textContent = (online && info.fps != null ? Math.round(info.fps) : "—") + " FPS";

    // Honest label: replayed recordings are never shown as live.
    const recorded = online && info.mode === "replay";
    mode.hidden = !recorded;
    mode.textContent = recorded ? grid.dataset.labelRecorded : "";

    if (online && grid.dataset.streamUrl) {
      const url = grid.dataset.streamUrl + "/stream/" + id;
      if (img.getAttribute("src") !== url) img.setAttribute("src", url);
      img.hidden = false;
      placeholder.hidden = true;
    } else {
      img.removeAttribute("src");
      img.hidden = true;
      placeholder.hidden = false;
    }
  }

  document.addEventListener("engine-status", (event) => {
    const items = (event.detail && event.detail.cameras && event.detail.cameras.items) || {};
    tiles.forEach((tile) => updateTile(tile, items[tile.dataset.cameraId]));
  });

  // Stream died (engine restarted): fall back to the placeholder until the next status.
  tiles.forEach((tile) => {
    const img = tile.querySelector(".camera-tile__stream");
    img.addEventListener("error", () => {
      img.removeAttribute("src");
      img.hidden = true;
      tile.querySelector(".camera-tile__placeholder").hidden = false;
    });
  });

  state.layout = loadLayout();
  render();
})();
