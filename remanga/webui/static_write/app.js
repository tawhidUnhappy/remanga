// Narration Writer frontend: one flat list of panel cards, each showing the
// panel's cropped image and a text field the user types the narration line
// into directly. No flag/issue concept here (see the Reviewer's app.js for
// that pattern) - this UI writes narration.json itself.

let PANELS = [];
let CHAPTER = null;
const texts = new Map(); // panel_id -> text
const saveTimers = new Map(); // panel_id -> debounce timer, so a burst of
// keystrokes doesn't fire one POST per character - see scheduleSave() below.
const SAVE_DEBOUNCE_MS = 600;

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

  render();
  wireFooter();
  wireLightbox();
  wireUnloadFlush();
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

function render() {
  const list = document.getElementById("panel-list");
  list.innerHTML = "";
  for (const p of PANELS) {
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

    list.appendChild(card);
  }
  updateCounts();
}

function updateText(panelId, value, card) {
  texts.set(panelId, value);
  const written = value.trim().length > 0;
  card.classList.toggle("empty", !written);
  const pill = card.querySelector(".status-pill");
  pill.className = "status-pill " + (written ? "is-written" : "is-empty");
  pill.textContent = written ? "✓ written" : "○ empty";
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

  // Push every panel's latest text to the server before finishing - the
  // per-keystroke handler above only updates local state.
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
