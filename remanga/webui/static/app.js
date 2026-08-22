// Panel Marker frontend. All marks are kept in NATURAL image pixel space (the
// resolution of the source page file); `scale` maps that to on-screen display
// pixels for rendering and mouse-event math only.

const isMac = navigator.platform.toUpperCase().includes("MAC");
document.querySelectorAll("#saveKbd, #hintSaveKbd").forEach(el => el.textContent = isMac ? "⌘S" : "Ctrl+S");

const stage = document.getElementById("stage");
const canvasWrap = document.getElementById("canvasWrap");
const pageImg = document.getElementById("pageImg");
const panelList = document.getElementById("panelList");
const panelCount = document.getElementById("panelCount");
const pageNumEl = document.getElementById("pageNum");
const pageTotalEl = document.getElementById("pageTotal");
const storyBadge = document.getElementById("storyBadge");
const zoomLabel = document.getElementById("zoomLabel");
const assistCard = document.getElementById("assistCard");
const assistBtn = document.getElementById("assistBtn");
const assistProgressBar = document.getElementById("assistProgressBar");
const assistStatus = document.getElementById("assistStatus");
const saveOverlay = document.getElementById("saveOverlay");

let chapter = null;          // { chapter, pages, magi_enabled }
let pageMarksCache = {};     // filename -> [{id,x,y,w,h,src}] in NATURAL pixel space
let touchedPages = new Set();
let pageIndex = 0;
let marks = [];              // current page's marks (same array objects as in cache)
let selectedId = null;
let mode = "draw";
let scale = 1;
let nextLocalId = 1;
let saveDebounce = null;
let magiEnabled = false;

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}

function currentFilename() {
  return chapter.pages[pageIndex].filename;
}

// ---------------- Load chapter ----------------
async function init() {
  chapter = await api("/api/chapter");
  magiEnabled = chapter.magi_enabled;
  pageTotalEl.textContent = chapter.pages.length;
  for (const p of chapter.pages) pageMarksCache[p.filename] = chapter.marks[p.filename] || [];

  if (!magiEnabled) {
    assistCard.classList.add("disabled");
    assistBtn.disabled = true;
    assistStatus.textContent = "Disabled in config.json";
  }

  await loadPage(0);
  pollDetectStatus();
  setInterval(pollDetectStatus, 1200);
}

async function loadPage(idx) {
  flushSave(true);
  pageIndex = Math.max(0, Math.min(chapter.pages.length - 1, idx));
  const page = chapter.pages[pageIndex];
  marks = pageMarksCache[page.filename];
  selectedId = null;

  pageNumEl.textContent = String(page.index).padStart(2, "0");
  document.getElementById("prevPage").disabled = pageIndex === 0;
  document.getElementById("nextPage").disabled = pageIndex === chapter.pages.length - 1;

  await new Promise(resolve => {
    pageImg.onload = resolve;
    pageImg.src = `/api/pages/${page.filename}`;
  });

  fitZoomToWrap(page.width, page.height);
  applyZoom();
  render();
}

function fitZoomToWrap(naturalW, naturalH) {
  const availW = canvasWrap.clientWidth - 80;
  const availH = canvasWrap.clientHeight - 80;
  scale = Math.min(1, availW / naturalW, availH / naturalH);
  scale = Math.max(0.15, scale);
}

function applyZoom() {
  const page = chapter.pages[pageIndex];
  stage.style.width = Math.round(page.width * scale) + "px";
  stage.style.height = Math.round(page.height * scale) + "px";
  pageImg.style.width = "100%";
  pageImg.style.height = "100%";
  zoomLabel.textContent = Math.round(scale * 100) + "%";
}

// ---------------- Rendering ----------------
function render() {
  stage.querySelectorAll(".mark, .guide-line").forEach(el => el.remove());

  marks.forEach((m, i) => {
    const el = document.createElement("div");
    el.className = "mark" + (m.src === "ai" ? " ai" : "") + (m.id === selectedId ? " selected" : "");
    Object.assign(el.style, {
      left: (m.x * scale) + "px", top: (m.y * scale) + "px",
      width: (m.w * scale) + "px", height: (m.h * scale) + "px",
    });

    const tag = document.createElement("div");
    tag.className = "tag";
    tag.textContent = "Panel " + (i + 1);
    el.appendChild(tag);

    if (m.id === selectedId) {
      ["nw", "n", "ne", "w", "e", "sw", "s", "se"].forEach(pos => {
        const h = document.createElement("div");
        h.className = "handle " + pos;
        el.appendChild(h);
      });
      const dim = document.createElement("div");
      dim.className = "dim-readout";
      dim.textContent = Math.round(m.w) + " × " + Math.round(m.h) + " px";
      el.appendChild(dim);
    }

    el.addEventListener("mousedown", (e) => onMarkMouseDown(e, m));
    el.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      deleteMark(m.id);
    });

    stage.appendChild(el);
  });

  renderList();
  updateStoryBadge();
}

function updateStoryBadge() {
  storyBadge.textContent = marks.length ? `${marks.length} panel${marks.length === 1 ? "" : "s"}` : "no panels";
  storyBadge.classList.toggle("story", marks.length > 0);
}

function renderList() {
  panelCount.textContent = marks.length;
  if (!marks.length) {
    panelList.innerHTML = `<div class="empty-list">No panels marked on this page yet.<br>Drag on the canvas to add one, or wait for MAGI v3.</div>`;
    return;
  }
  panelList.innerHTML = "";
  marks.forEach((m, i) => {
    const row = document.createElement("div");
    row.className = "panel-row" + (m.id === selectedId ? " selected" : "") + (m.src === "ai" ? " is-ai" : "");
    row.draggable = true;
    row.dataset.index = i;
    row.innerHTML = `
      <span class="grip">⠿</span>
      <span class="order-badge">${i + 1}</span>
      <span class="panel-row-main">
        <span class="panel-row-title">Panel ${i + 1}
          <span class="src-chip ${m.src === "ai" ? "ai" : ""}">${m.src === "ai" ? "AI" : "MANUAL"}</span>
        </span>
        <span class="panel-row-sub">${Math.round(m.w)}×${Math.round(m.h)} px</span>
      </span>
      <button class="row-del" title="Delete">✕</button>
    `;
    row.addEventListener("click", (e) => {
      if (e.target.closest(".row-del")) { deleteMark(m.id); return; }
      selectedId = m.id;
      render();
    });
    row.addEventListener("dragstart", (e) => {
      row.classList.add("dragging");
      e.dataTransfer.setData("text/plain", String(i));
    });
    row.addEventListener("dragend", () => row.classList.remove("dragging"));
    row.addEventListener("dragover", (e) => e.preventDefault());
    row.addEventListener("drop", (e) => {
      e.preventDefault();
      const from = parseInt(e.dataTransfer.getData("text/plain"), 10);
      const to = i;
      if (from === to) return;
      const [moved] = marks.splice(from, 1);
      marks.splice(to, 0, moved);
      markDirty();
      render();
    });
    panelList.appendChild(row);
  });
}

// ---------------- Editing marks ----------------
function markDirty() {
  pageMarksCache[currentFilename()] = marks;
  touchedPages.add(currentFilename());
  clearTimeout(saveDebounce);
  saveDebounce = setTimeout(() => flushSave(false), 400);
}

async function flushSave(immediate) {
  const filename = chapter?.pages[pageIndex]?.filename;
  if (!filename) return;
  clearTimeout(saveDebounce);
  try {
    await api(`/api/marks/${encodeURIComponent(filename)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pageMarksCache[filename] || []),
    });
  } catch (e) {
    if (immediate) console.error("Failed to save marks for", filename, e);
  }
}

function deleteMark(id) {
  marks = marks.filter(m => m.id !== id);
  pageMarksCache[currentFilename()] = marks;
  if (selectedId === id) selectedId = null;
  markDirty();
  render();
}

function clampBoxToPage(x, y, w, h) {
  const page = chapter.pages[pageIndex];
  x = Math.max(0, Math.min(x, page.width - 1));
  y = Math.max(0, Math.min(y, page.height - 1));
  w = Math.max(4, Math.min(w, page.width - x));
  h = Math.max(4, Math.min(h, page.height - y));
  return { x, y, w, h };
}

// ---------------- Alignment guides ----------------
function showGuides(activeDisplay, othersDisplay) {
  stage.querySelectorAll(".guide-line").forEach(el => el.remove());
  const THRESH = 5;
  const edgesX = [activeDisplay.x, activeDisplay.x + activeDisplay.w / 2, activeDisplay.x + activeDisplay.w];
  const edgesY = [activeDisplay.y, activeDisplay.y + activeDisplay.h / 2, activeDisplay.y + activeDisplay.h];
  othersDisplay.forEach(o => {
    const oEdgesX = [o.x, o.x + o.w / 2, o.x + o.w];
    const oEdgesY = [o.y, o.y + o.h / 2, o.y + o.h];
    edgesX.forEach(ax => oEdgesX.forEach(ox => { if (Math.abs(ax - ox) < THRESH) drawGuide("v", ox); }));
    edgesY.forEach(ay => oEdgesY.forEach(oy => { if (Math.abs(ay - oy) < THRESH) drawGuide("h", oy); }));
  });
}
function drawGuide(axis, pos) {
  const line = document.createElement("div");
  line.className = "guide-line " + axis;
  if (axis === "v") line.style.left = pos + "px"; else line.style.top = pos + "px";
  stage.appendChild(line);
}
function clearGuides() { stage.querySelectorAll(".guide-line").forEach(el => el.remove()); }

// ---------------- Move / resize an existing mark ----------------
function onMarkMouseDown(e, m) {
  if (e.button === 2) return;
  e.stopPropagation();
  selectedId = m.id;
  const handle = e.target.classList.contains("handle") ? [...e.target.classList].find(c => c !== "handle") : null;
  const startX = e.clientX, startY = e.clientY;
  const orig = { ...m };
  render();

  function onMove(ev) {
    const dxDisplay = ev.clientX - startX, dyDisplay = ev.clientY - startY;
    const dx = dxDisplay / scale, dy = dyDisplay / scale;
    let { x, y, w, h } = orig;

    if (handle) {
      if (handle.includes("e")) w = Math.max(4, orig.w + dx);
      if (handle.includes("s")) h = Math.max(4, orig.h + dy);
      if (handle.includes("w")) { x = orig.x + dx; w = Math.max(4, orig.w - dx); }
      if (handle.includes("n")) { y = orig.y + dy; h = Math.max(4, orig.h - dy); }
    } else {
      x = orig.x + dx; y = orig.y + dy;
    }

    const page = chapter.pages[pageIndex];
    x = Math.max(0, Math.min(x, page.width - 4));
    y = Math.max(0, Math.min(y, page.height - 4));
    w = Math.min(w, page.width - x);
    h = Math.min(h, page.height - y);

    m.x = x; m.y = y; m.w = w; m.h = h;
    if (m.src === "ai") m.src = "manual"; // any manual adjustment promotes it

    const activeDisplay = { x: m.x * scale, y: m.y * scale, w: m.w * scale, h: m.h * scale };
    const othersDisplay = marks.filter(o => o.id !== m.id).map(o => ({ x: o.x * scale, y: o.y * scale, w: o.w * scale, h: o.h * scale }));
    showGuides(activeDisplay, othersDisplay);
    render();
  }
  function onUp() {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    clearGuides();
    markDirty();
  }
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
}

// ---------------- Draw a new mark (Canva-style: can start outside the page) ----------------
let drawing = null, ghostEl = null;
canvasWrap.addEventListener("mousedown", (e) => {
  if (mode !== "draw" || e.button !== 0) return;
  if (e.target.closest(".mark")) return; // let mark-level handler deal with it
  e.preventDefault();

  const rect = stage.getBoundingClientRect();
  const anchorX = e.clientX - rect.left;   // may be negative or beyond stage size - that's fine
  const anchorY = e.clientY - rect.top;
  drawing = { anchorX, anchorY, x: anchorX, y: anchorY, w: 0, h: 0 };
  ghostEl = document.createElement("div");
  ghostEl.className = "draw-ghost";
  stage.appendChild(ghostEl);

  function onMove(ev) {
    const cx = ev.clientX - rect.left, cy = ev.clientY - rect.top;
    const x = Math.min(cx, drawing.anchorX), y = Math.min(cy, drawing.anchorY);
    const w = Math.abs(cx - drawing.anchorX), h = Math.abs(cy - drawing.anchorY);
    Object.assign(ghostEl.style, { left: x + "px", top: y + "px", width: w + "px", height: h + "px" });
    drawing.x = x; drawing.y = y; drawing.w = w; drawing.h = h;
  }
  function onUp() {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    ghostEl?.remove();
    if (drawing.w > 8 && drawing.h > 8) {
      const natural = clampBoxToPage(drawing.x / scale, drawing.y / scale, drawing.w / scale, drawing.h / scale);
      const m = { id: "local-" + (nextLocalId++), ...natural, src: "manual" };
      marks.push(m);
      selectedId = m.id;
      markDirty();
      render();
    }
    drawing = null;
  }
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
});
stage.addEventListener("contextmenu", (e) => e.preventDefault());

// ---------------- Mode / zoom / nav ----------------
function setMode(next) {
  mode = next;
  document.getElementById("toolDraw").classList.toggle("active", mode === "draw");
  document.getElementById("toolSelect").classList.toggle("active", mode === "select");
  stage.classList.toggle("select-mode", mode === "select");
}
document.getElementById("toolDraw").addEventListener("click", () => setMode("draw"));
document.getElementById("toolSelect").addEventListener("click", () => setMode("select"));

document.getElementById("zoomIn").addEventListener("click", () => { scale = Math.min(3, scale + 0.1); applyZoom(); render(); });
document.getElementById("zoomOut").addEventListener("click", () => { scale = Math.max(0.15, scale - 0.1); applyZoom(); render(); });

document.getElementById("prevPage").addEventListener("click", () => loadPage(pageIndex - 1));
document.getElementById("nextPage").addEventListener("click", () => loadPage(pageIndex + 1));

document.addEventListener("keydown", (e) => {
  const cmd = isMac ? e.metaKey : e.ctrlKey;
  if (cmd && e.key.toLowerCase() === "s") { e.preventDefault(); saveAndContinue(); return; }
  if (e.key === "d" || e.key === "D") setMode("draw");
  if (e.key === "v" || e.key === "V") setMode("select");
  if (e.key === "ArrowLeft") loadPage(pageIndex - 1);
  if (e.key === "ArrowRight") loadPage(pageIndex + 1);
  if ((e.key === "Delete" || e.key === "Backspace") && selectedId !== null) deleteMark(selectedId);
});

// ---------------- MAGI v3 assist ----------------
async function runDetect() {
  try {
    await api("/api/detect", { method: "POST" });
  } catch (e) {
    console.error(e);
  }
}
assistBtn.addEventListener("click", runDetect);

async function pollDetectStatus() {
  if (!magiEnabled) return;
  let status;
  try { status = await api("/api/detect/status"); } catch { return; }

  assistBtn.disabled = status.running;
  if (status.running) {
    assistProgressBar.style.width = status.total ? Math.round((status.done / status.total) * 100) + "%" : "0%";
    assistStatus.textContent = `Detecting… ${status.done}/${status.total} pages`;
  } else if (status.error) {
    assistStatus.textContent = "Error: " + status.error;
  } else if (status.total) {
    assistProgressBar.style.width = "100%";
    assistStatus.textContent = `Done · ${status.total} page(s) processed`;
  }

  let currentPageChanged = false;
  for (const [filename, serverMarks] of Object.entries(status.marks || {})) {
    if (touchedPages.has(filename)) continue;
    pageMarksCache[filename] = serverMarks;
    if (chapter.pages[pageIndex].filename === filename) currentPageChanged = true;
  }
  if (currentPageChanged) {
    marks = pageMarksCache[currentFilename()];
    render();
  }
}

// ---------------- Save & continue ----------------
async function saveAndContinue() {
  await flushSave(true);
  try {
    await api("/api/finish", { method: "POST" });
    saveOverlay.classList.add("visible");
    setTimeout(() => { try { window.close(); } catch {} }, 400);
  } catch (e) {
    alert("Failed to save: " + e.message);
  }
}
document.getElementById("saveBtn").addEventListener("click", saveAndContinue);
window.addEventListener("beforeunload", () => flushSave(true));
window.addEventListener("resize", () => { fitZoomToWrap(chapter.pages[pageIndex].width, chapter.pages[pageIndex].height); applyZoom(); render(); });

init();
