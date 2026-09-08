// Narration Writer frontend: one flat list of panel cards, each showing the
// panel's cropped image and a text field the user types the narration line
// into directly. No flag/issue concept here (see the Reviewer's app.js for
// that pattern) - this UI writes narration.json itself.
//
// Two things that only matter once a chapter has a lot of panels:
//  - #panel-nav (right side): a dot per panel, colored by written/empty,
//    click to jump straight to it. Always fully rendered (see
//    buildNav()) - a few hundred small colorless-image-free divs cost
//    nothing, unlike the image-heavy cards themselves.
//  - Virtual sliding window (see initVirtualList() down to trimBottomIfNeeded()):
//    only a bounded range of panel CARDS is ever mounted in the DOM at once,
//    centered on wherever the user is scrolled to. Scrolling toward either
//    edge of the mounted range grows it that direction and, once it's
//    grown past MAX_RENDERED, trims the opposite (off-screen) end back off
//    - so memory/DOM/decoded-image cost stays roughly constant no matter
//    how many panels the chapter has, instead of the whole chapter's worth
//    of full-resolution images sitting in the DOM simultaneously.

let PANELS = [];
let CHAPTER = null;
const texts = new Map(); // panel_id -> text
const saveTimers = new Map(); // panel_id -> debounce timer, so a burst of
// keystrokes doesn't fire one POST per character - see scheduleSave() below.
const SAVE_DEBOUNCE_MS = 600;

// ---- Virtual sliding window state -----------------------------------------
const CHUNK = 8; // panels added per scroll-triggered extension
const MAX_RENDERED = 24; // cards kept mounted before the far end gets trimmed
let renderStart = 0; // inclusive index into PANELS
let renderEnd = 0; // exclusive index into PANELS
let topSentinel, bottomSentinel, panelListEl;
let topObserver, bottomObserver, centerObserver;
const navDots = new Map(); // panel_id -> nav dot element
let activePanelId = null;

async function main() {
  const res = await fetch("/api/narration");
  if (!res.ok) {
    document.getElementById("loading").textContent = "Failed to load panels.";
    return;
  }
  const data = await res.json();
  PANELS = data.panels;
  CHAPTER = data.chapter;

  for (const p of PANELS) texts.set(p.panel_id, p.text || "");

  document.getElementById("chapter-meta").textContent = `Chapter ${CHAPTER} — ${PANELS.length} panel(s)`;
  document.title = `Narration Writer — Ch. ${CHAPTER}`;
  document.getElementById("loading").style.display = "none";
  document.getElementById("hint").style.display = "block";
  document.getElementById("footer").style.display = "flex";

  buildNav();
  initVirtualList();
  wireFooter();
  wireLightbox();
  wireUnloadFlush();
}

// ---- Right-side panel navigator -------------------------------------------
function buildNav() {
  const nav = document.getElementById("panel-nav");
  nav.innerHTML = "";
  for (const p of PANELS) {
    const written = (texts.get(p.panel_id) || "").trim().length > 0;
    const dot = document.createElement("div");
    dot.className = "nav-dot" + (written ? " is-written" : "");
    dot.title = `${p.panel_id}${written ? " — written" : " — empty"}`;
    dot.addEventListener("click", () => jumpToPanel(p.panel_id));
    navDots.set(p.panel_id, dot);
    nav.appendChild(dot);
  }
}

function setNavWritten(panelId, written) {
  const dot = navDots.get(panelId);
  if (!dot) return;
  dot.classList.toggle("is-written", written);
  dot.title = `${panelId}${written ? " — written" : " — empty"}`;
}

function setActiveNav(panelId) {
  if (panelId === activePanelId) return;
  const prev = navDots.get(activePanelId);
  if (prev) prev.classList.remove("active");
  const next = navDots.get(panelId);
  if (next) next.classList.add("active");
  activePanelId = panelId;
}

// Jumps to any panel by id, re-windowing the virtual list around it first if
// it isn't currently mounted (nav can point at a panel far outside the
// current render range).
function jumpToPanel(panelId) {
  const idx = PANELS.findIndex((p) => p.panel_id === panelId);
  if (idx === -1) return;

  if (idx < renderStart || idx >= renderEnd) {
    const half = Math.floor(MAX_RENDERED / 2);
    const newStart = Math.max(0, Math.min(idx - half, PANELS.length - MAX_RENDERED));
    const newEnd = Math.min(PANELS.length, Math.max(newStart, 0) + MAX_RENDERED);
    remountRange(Math.max(0, newStart), newEnd);
  }

  const card = panelListEl.querySelector(`.panel-card[data-panel-id="${CSS.escape(panelId)}"]`);
  if (card) card.scrollIntoView({ block: "start", behavior: "auto" });
}

// ---- Virtual sliding window -------------------------------------------
function initVirtualList() {
  panelListEl = document.getElementById("panel-list");
  panelListEl.innerHTML = "";

  topSentinel = document.createElement("div");
  topSentinel.className = "scroll-sentinel";
  bottomSentinel = document.createElement("div");
  bottomSentinel.className = "scroll-sentinel";
  panelListEl.appendChild(topSentinel);
  panelListEl.appendChild(bottomSentinel);

  // A big rootMargin on both edges means "start loading/unloading well
  // before the sentinel is actually on screen" - keeps scrolling smooth
  // instead of popping in a chunk right at the visible edge.
  topObserver = new IntersectionObserver(onTopVisible, { rootMargin: "1000px 0px 1000px 0px" });
  bottomObserver = new IntersectionObserver(onBottomVisible, { rootMargin: "1000px 0px 1000px 0px" });
  topObserver.observe(topSentinel);
  bottomObserver.observe(bottomSentinel);

  centerObserver = new IntersectionObserver(onCenterVisible, { rootMargin: "-40% 0px -55% 0px", threshold: 0 });

  renderStart = 0;
  renderEnd = 0;
  mountRange(0, Math.min(PANELS.length, CHUNK * 2));
}

function buildCard(p) {
  const text = texts.get(p.panel_id) || "";
  const card = document.createElement("div");
  card.className = "panel-card" + (text.trim() ? "" : " empty");
  card.dataset.panelId = p.panel_id;

  const thumbHtml = p.image
    ? `<img src="/api/panels/${encodeURIComponent(p.image)}" loading="lazy" alt="${p.panel_id}" data-action="zoom">`
    : `<div class="missing">No image file found for this panel.</div>`;

  card.innerHTML = `
    <div class="panel-thumb">${thumbHtml}</div>
    <div class="panel-body">
      <div class="panel-id-row">
        <span class="panel-id">${p.panel_id}</span>
        <span class="status-pill ${text.trim() ? "is-written" : "is-empty"}">${text.trim() ? "✓ written" : "○ empty"}</span>
      </div>
      <label class="text-label" for="text-${p.panel_id}">Narration</label>
      <textarea id="text-${p.panel_id}" placeholder="Type the narration line for this panel - leave empty for a silent beat.">${escapeHtml(text)}</textarea>
      <div class="ocr-row">
        <button type="button" class="ocr-btn" data-action="ocr">🔎 OCR this panel</button>
        <span class="ocr-status"></span>
      </div>
      <div class="ocr-result" hidden></div>
    </div>
  `;

  const textField = card.querySelector("textarea");
  textField.addEventListener("input", (e) => {
    updateText(p.panel_id, e.target.value, card);
    scheduleSave(p.panel_id, card);
  });
  // A debounce timer only fires after typing pauses - a field left
  // mid-word when the tab is closed/killed needs its own immediate save,
  // not a wait that never comes.
  textField.addEventListener("blur", () => flushSave(p.panel_id, card));

  const img = card.querySelector('img[data-action="zoom"]');
  if (img) img.addEventListener("click", () => openLightbox(img.src, p.panel_id));

  card.querySelector('[data-action="ocr"]').addEventListener("click", () => runOcr(p.panel_id, card));

  centerObserver.observe(card);
  return card;
}

// "OCR this panel" - runs DeepSeek-OCR-2 (see remanga/ocr/engine.py; GPU
// preferred, falls back to CPU) on this panel's cropped image and offers
// the recognized text as a starting draft, never silently overwriting
// anything already typed:
//   - empty field: filled in directly (nothing to lose) and autosaved.
//   - field already has text: recognized text shows in a small panel with
//     Replace/Append/Dismiss instead of touching the textarea on its own.
// The worker loads the model on its first call in this session (can take a
// while, and downloads the weights first if they aren't already on disk -
// see ModelManager) - every call after that reuses the same loaded model
// and is fast.
async function runOcr(panelId, card) {
  const btn = card.querySelector('[data-action="ocr"]');
  const statusEl = card.querySelector(".ocr-status");
  const resultEl = card.querySelector(".ocr-result");
  const textField = card.querySelector("textarea");

  btn.disabled = true;
  statusEl.textContent = "Reading panel… (first run this session loads the model, can take a bit)";
  statusEl.className = "ocr-status";
  resultEl.hidden = true;

  try {
    const res = await fetch(`/api/ocr/${encodeURIComponent(panelId)}`, { method: "POST" });
    const result = await res.json();
    if (!result.ok) throw new Error(result.error || `HTTP ${res.status}`);

    const recognized = (result.text || "").trim();
    statusEl.textContent = result.device === "cuda" ? "✓ read on GPU" : "✓ read on CPU (no GPU available)";
    statusEl.className = "ocr-status ocr-ok";

    if (!recognized) {
      statusEl.textContent += " - no text found on this panel.";
      return;
    }

    if (!textField.value.trim()) {
      // Nothing typed yet - just fill it in directly, same as if the user
      // had typed it, so it autosaves through the normal path.
      textField.value = recognized;
      updateText(panelId, recognized, card);
      scheduleSave(panelId, card);
      return;
    }

    // Something's already there - never overwrite it without asking.
    resultEl.hidden = false;
    resultEl.innerHTML = `
      <div class="ocr-result-text">${escapeHtml(recognized)}</div>
      <div class="ocr-result-actions">
        <button type="button" class="ocr-mini" data-act="replace">Replace</button>
        <button type="button" class="ocr-mini" data-act="append">Append</button>
        <button type="button" class="ocr-mini" data-act="dismiss">Dismiss</button>
      </div>
    `;
    resultEl.querySelector('[data-act="replace"]').addEventListener("click", () => {
      textField.value = recognized;
      updateText(panelId, recognized, card);
      scheduleSave(panelId, card);
      resultEl.hidden = true;
    });
    resultEl.querySelector('[data-act="append"]').addEventListener("click", () => {
      const merged = `${textField.value.trim()} ${recognized}`.trim();
      textField.value = merged;
      updateText(panelId, merged, card);
      scheduleSave(panelId, card);
      resultEl.hidden = true;
    });
    resultEl.querySelector('[data-act="dismiss"]').addEventListener("click", () => {
      resultEl.hidden = true;
    });
  } catch (err) {
    statusEl.textContent = `OCR failed: ${err.message || err}`;
    statusEl.className = "ocr-status ocr-failed";
    console.error(`OCR failed for panel ${panelId}:`, err);
  } finally {
    btn.disabled = false;
  }
}

// Appends cards for [start, end) right before the bottom sentinel.
function mountRange(start, end) {
  for (let i = start; i < end; i++) {
    panelListEl.insertBefore(buildCard(PANELS[i]), bottomSentinel);
  }
  renderStart = start;
  renderEnd = end;
  updateCounts();
}

// Wipes every mounted card and mounts a fresh [start, end) range - used by
// jumpToPanel() when the target isn't anywhere near what's currently mounted,
// where incremental extend/trim wouldn't make sense.
function remountRange(start, end) {
  while (panelListEl.children.length > 2) {
    const node = panelListEl.children[1];
    centerObserver.unobserve(node);
    node.remove();
  }
  mountRange(start, end);
}

function onBottomVisible(entries) {
  if (!entries[0].isIntersecting || renderEnd >= PANELS.length) return;
  const newEnd = Math.min(PANELS.length, renderEnd + CHUNK);
  for (let i = renderEnd; i < newEnd; i++) {
    panelListEl.insertBefore(buildCard(PANELS[i]), bottomSentinel);
  }
  renderEnd = newEnd;
  trimTopIfNeeded();
}

function onTopVisible(entries) {
  if (!entries[0].isIntersecting || renderStart <= 0) return;
  const newStart = Math.max(0, renderStart - CHUNK);
  const inserted = [];
  for (let i = renderStart - 1; i >= newStart; i--) {
    const card = buildCard(PANELS[i]);
    panelListEl.insertBefore(card, topSentinel.nextSibling);
    inserted.push(card);
  }
  renderStart = newStart;

  // Compensate scroll position: content just appeared ABOVE the viewport,
  // which would otherwise shove everything the user is looking at downward
  // by the same amount - so scroll down by exactly what was inserted to
  // keep the same content under the viewport.
  let insertedHeight = 0;
  for (const node of inserted) insertedHeight += node.getBoundingClientRect().height;
  if (insertedHeight > 0) window.scrollBy(0, insertedHeight);

  trimBottomIfNeeded();
}

// Removes the oldest (topmost) mounted cards once the window has grown past
// MAX_RENDERED via bottom-extension - those cards are above the viewport
// (the user just scrolled down to trigger this), so removing them shifts
// everything below UP; compensate by scrolling up the same amount.
function trimTopIfNeeded() {
  const overflow = (renderEnd - renderStart) - MAX_RENDERED;
  if (overflow <= 0) return;
  let removedHeight = 0;
  for (let i = 0; i < overflow; i++) {
    const node = panelListEl.children[1]; // first card after topSentinel
    removedHeight += node.getBoundingClientRect().height;
    centerObserver.unobserve(node);
    node.remove();
  }
  renderStart += overflow;
  if (removedHeight > 0) window.scrollBy(0, -removedHeight);
}

// Removes the newest (bottommost) mounted cards once the window has grown
// past MAX_RENDERED via top-extension - those cards are below the viewport,
// so removing them doesn't move anything currently visible; no scroll
// compensation needed.
function trimBottomIfNeeded() {
  const overflow = (renderEnd - renderStart) - MAX_RENDERED;
  if (overflow <= 0) return;
  for (let i = 0; i < overflow; i++) {
    const node = panelListEl.children[panelListEl.children.length - 2]; // last card before bottomSentinel
    centerObserver.unobserve(node);
    node.remove();
  }
  renderEnd -= overflow;
}

function onCenterVisible(entries) {
  for (const entry of entries) {
    if (entry.isIntersecting) {
      setActiveNav(entry.target.dataset.panelId);
      break;
    }
  }
}

// ---- Per-panel state / autosave -------------------------------------------
function updateText(panelId, value, card) {
  texts.set(panelId, value);
  const written = value.trim().length > 0;
  card.classList.toggle("empty", !written);
  const pill = card.querySelector(".status-pill");
  pill.className = "status-pill " + (written ? "is-written" : "is-empty");
  pill.textContent = written ? "✓ written" : "○ empty";
  setNavWritten(panelId, written);
  updateCounts();
}

// Aggressive autosave: every panel's text hits narration.json on disk within
// SAVE_DEBOUNCE_MS of the user pausing (or immediately on blur/tab-away),
// not only when Save is clicked - so a closed tab, killed server, or crash
// mid-session loses at most the last half-second of typing in the field
// that was focused, never everything since the last explicit save. The
// server persists the *entire* narration.json on each call (see
// writer_routes.py's /api/text handler), so this only needs to fire per
// edited panel, not resend every panel every time.
function scheduleSave(panelId, card) {
  clearTimeout(saveTimers.get(panelId));
  saveTimers.set(
    panelId,
    setTimeout(() => {
      saveTimers.delete(panelId); // no longer pending - wireUnloadFlush only re-sends what's still queued
      saveText(panelId, card);
    }, SAVE_DEBOUNCE_MS),
  );
}

function flushSave(panelId, card) {
  clearTimeout(saveTimers.get(panelId));
  saveTimers.delete(panelId);
  saveText(panelId, card);
}

async function saveText(panelId, card) {
  const pill = card?.querySelector(".status-pill");
  const savedText = texts.get(panelId) || "";
  try {
    const res = await fetch(`/api/text/${encodeURIComponent(panelId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: savedText }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (pill) pill.classList.remove("save-failed");
  } catch (err) {
    // Autosave failing shouldn't interrupt typing - just flag it visibly so
    // an unnoticed connection drop doesn't silently lose progress. The next
    // successful save (this panel or any other keystroke) clears the flag.
    if (pill) pill.classList.add("save-failed");
    console.error(`Autosave failed for panel ${panelId}:`, err);
  }
}

// Belt-and-suspenders for a tab closed mid-debounce (before the 600ms timer
// fires): a regular fetch() isn't guaranteed to complete once the page is
// unloading, so use sendBeacon - fire-and-forget, but the browser keeps it
// alive past navigation. Only for panels with a still-pending save; anything
// already saved or mid-typing-but-not-yet-scheduled has nothing new to flush.
function wireUnloadFlush() {
  window.addEventListener("beforeunload", () => {
    for (const panelId of saveTimers.keys()) {
      navigator.sendBeacon(
        `/api/text/${encodeURIComponent(panelId)}`,
        new Blob([JSON.stringify({ text: texts.get(panelId) || "" })], { type: "application/json" }),
      );
    }
  });
}

function updateCounts() {
  const written = [...texts.values()].filter((t) => t.trim()).length;
  document.getElementById("counts").innerHTML = `<b>${written}</b> / ${PANELS.length} written`;
}

function openLightbox(src, alt) {
  const lb = document.getElementById("lightbox");
  const img = document.getElementById("lightbox-img");
  img.src = src;
  img.alt = alt;
  lb.classList.add("open");
}

function closeLightbox() {
  document.getElementById("lightbox").classList.remove("open");
}

function wireLightbox() {
  document.getElementById("lightbox").addEventListener("click", closeLightbox);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeLightbox();
  });
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

async function saveNarration() {
  const emptyCount = PANELS.length - [...texts.values()].filter((t) => t.trim()).length;
  if (emptyCount > 0) {
    if (!confirm(`${emptyCount} panel(s) still have no narration text. Save anyway?`)) return;
  }

  // Push every panel's latest text to the server before finishing - reads
  // straight from the `texts` map (holds every panel's text regardless of
  // whether it's currently mounted in the virtual window), not from the DOM.
  for (const p of PANELS) {
    await fetch(`/api/text/${encodeURIComponent(p.panel_id)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: texts.get(p.panel_id) || "" }),
    });
  }

  const res = await fetch("/api/finish", { method: "POST" });
  const result = await res.json();
  if (result.ok) {
    document.body.innerHTML = `<main><h1 style="padding-top:60px;text-align:center">
      ✓ Saved ${result.written}/${result.total_panels} panel(s) to narration.json — you can close this tab.
    </h1></main>`;
  }
}

function wireFooter() {
  document.getElementById("btn-save").addEventListener("click", saveNarration);
}

main();
