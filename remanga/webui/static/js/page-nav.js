// Loading the chapter, moving between pages, and the final "Save & Continue"
// that writes crops.json server-side and closes the tab.

import { pageImg, pageNumEl, pageTotalEl, prevPageBtn, nextPageBtn, assistCard, assistBtn, assistStatus, saveOverlay, saveBtn } from "./dom.js";
import { state, currentPage } from "./state.js";
import { api } from "./api.js";
import { flushSave } from "./marks.js";
import { resetView } from "./zoom-pan.js";
import { pollDetectStatus } from "./magi.js";
import { loadShortcuts } from "./shortcuts.js";
import { setMode } from "./keyboard.js";

export async function loadPage(idx) {
  // On the very first call, pageIndex is already 0 (its initial value), so
  // flushing "the page we're leaving" here would flush *this same* page with
  // its still-empty marks array and mark it touched server-side - which then
  // makes the server permanently refuse to apply MAGI's detections to it
  // (apply_detected() never overwrites a touched page). Only flush when we're
  // actually navigating away from a page that was on screen.
  if (state.pageLoaded) flushSave(true);
  state.pageIndex = Math.max(0, Math.min(state.chapter.pages.length - 1, idx));
  const page = currentPage();
  state.marks = state.pageMarksCache[page.filename];
  state.selectedId = null;

  pageNumEl.textContent = String(page.index).padStart(2, "0");
  prevPageBtn.disabled = state.pageIndex === 0;
  nextPageBtn.disabled = state.pageIndex === state.chapter.pages.length - 1;

  await new Promise(resolve => {
    pageImg.onload = resolve;
    pageImg.src = `/api/pages/${page.filename}`;
  });

  resetView();
  state.pageLoaded = true;
}

export async function init() {
  await loadShortcuts();
  state.chapter = await api("/api/chapter");
  state.magiEnabled = state.chapter.magi_enabled;
  state.clickToSelect = state.chapter.click_to_select;
  pageTotalEl.textContent = state.chapter.pages.length;
  for (const p of state.chapter.pages) state.pageMarksCache[p.filename] = state.chapter.marks[p.filename] || [];

  if (!state.magiEnabled) {
    assistCard.classList.add("disabled");
    assistBtn.disabled = true;
    assistStatus.textContent = "Disabled in config.json";
  }

  // Start in Select mode instead of the usual Draw default whenever this
  // chapter already has marks (crops.json was pre-loaded server-side - see
  // marker_state.py:_load_existing_crops, used by a "remark" restart and by
  // simply reopening the marker on an already-marked chapter). With
  // click_to_select on, Draw mode makes every existing mark non-interactive
  // on purpose (so drawing over one never nudges it - see drag-resize.js) -
  // exactly wrong when there's nothing left to draw and the whole point of
  // the session is adjusting what's already there. A genuinely fresh
  // chapter has no marks yet, so it's unaffected and still starts in Draw.
  const hasExistingMarks = Object.values(state.pageMarksCache).some(marks => marks.length > 0);
  if (hasExistingMarks) setMode("select");

  await loadPage(0);
  pollDetectStatus();
  setInterval(pollDetectStatus, 1200);
}

export async function saveAndContinue() {
  await flushSave(true);
  try {
    await api("/api/finish", { method: "POST" });
    saveOverlay.classList.add("visible");
    setTimeout(() => { try { window.close(); } catch {} }, 400);
  } catch (e) {
    alert("Failed to save: " + e.message);
  }
}

prevPageBtn.addEventListener("click", () => loadPage(state.pageIndex - 1));
nextPageBtn.addEventListener("click", () => loadPage(state.pageIndex + 1));
saveBtn.addEventListener("click", saveAndContinue);
window.addEventListener("beforeunload", () => flushSave(true));
window.addEventListener("resize", resetView);
