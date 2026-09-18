// The chapter level of the app: loading a chapter into the open tab, moving
// between the chapters in this session (the chapter arrows, and page-nav.js's
// stepPage past either end of a chapter), and the Save button - save every
// chapter and exit.
//
// Nothing in this file reloads the page. A chapter change is a fetch and a
// re-render, so the zoom, the tool, the shortcuts and the scroll position all
// survive it, and a session over twenty chapters is one browser tab that
// never blinks.
//
// page-nav.js is the level below (pages within one chapter) and is imported
// one-way from here - never the reverse, so there's no cycle between them.

import {
  saveOverlay, saveOverlayTitle, saveOverlayText, saveBtn, saveLabel,
  chapterNav, chapterName, chapterPos, prevChapterBtn, nextChapterBtn, pageTotalEl,
  assistCard, assistStatus, assistProgressBar,
  toolbar, viewBadge, hintToast, sidebarFooter,
} from "./dom.js";
import { state, currentFilename } from "./state.js";
import { api } from "./api.js";
import { flushSave } from "./marks.js";
import { loadPage } from "./page-nav.js";
import { pollDetectStatus, syncAssistCard } from "./magi.js";
import { loadShortcuts } from "./shortcuts.js";
import { setMode } from "./keyboard.js";
import { refreshOutline, renderOutline } from "./outline.js";
import { render } from "./render.js";

// Applies a chapter payload (/api/chapter or /api/goto - both return the same
// shape) to the running app.
//
// pageLoaded is cleared BEFORE loadPage(0): loadPage flushes "the page we're
// leaving" whenever a page is already up, and after a chapter change that
// flush would post the previous chapter's marks to the new chapter's state,
// under whatever filename happened to match. The page being left was already
// flushed by whoever asked for the chapter change.
export async function applyChapter(payload, startPage = 0) {
  state.chapter = payload;
  state.readOnly = !!payload.read_only;
  state.magiEnabled = payload.magi_enabled;
  state.clickToSelect = payload.click_to_select;
  state.pageMarksCache = {};
  state.touchedPages = new Set(payload.touched || []);
  state.decidedPages = new Set(payload.decided || []);
  state.chapterRevision = payload.revision || 0;
  state.editSeq = {};
  state.autoOrder = !!payload.auto_order;
  state.selectedId = null;
  state.pageLoaded = false;
  for (const p of payload.pages) state.pageMarksCache[p.filename] = payload.marks[p.filename] || [];
  pageTotalEl.textContent = payload.pages.length;

  updateChapterUi();
  updateReadOnlyChrome();
  resetAssistCard();

  // Adjust rather than Draw whenever this chapter already has marks (loaded
  // from its crops.json server-side, or made earlier in this same session and
  // come back to). Re-evaluated per chapter, because chapter 4 being freshly
  // downloaded says nothing about chapter 3 having been marked an hour ago.
  const hasMarks = Object.values(state.pageMarksCache).some(marks => marks.length > 0);
  setMode(hasMarks ? "adjust" : "draw");

  await loadPage(startPage);
  refreshOutline();
}

function updateChapterUi() {
  const { chapter, chapter_index: index, chapter_total: total, has_next: hasNext } = state.chapter;
  // A one-chapter session is every single-chapter caller (`mark`, the
  // pipeline's mark step, a "remark" restart): no chapter arrows.
  chapterNav.hidden = total <= 1;
  chapterName.textContent = chapter;
  chapterPos.textContent = `${index + 1}/${total}`;
  prevChapterBtn.disabled = index === 0;
  nextChapterBtn.disabled = !hasNext;
  // One button, one meaning, on every chapter: Save writes everything and
  // exits. Going to the next chapter is the arrows' job.
  saveLabel.textContent = state.readOnly ? "Close" : "Save";
  saveBtn.title = state.readOnly ? "Close the viewer" : "Save every chapter and exit";
}

// A viewer keeps everything that helps you look and drops everything that
// implies you can change something: no Draw/Adjust, no "drag to mark" hints,
// no reorder footnote - and a badge saying so, because a UI that has quietly
// stopped accepting edits is worse than one that says it won't.
function updateReadOnlyChrome() {
  toolbar.hidden = state.readOnly;
  viewBadge.hidden = !state.readOnly;
  hintToast.hidden = state.readOnly;
  sidebarFooter.hidden = state.readOnly;
}

function resetAssistCard() {
  // A read-only session never runs detection (it would write marks nobody
  // saved - see MarkerSession.queue_detection), so the card has nothing to
  // report and no button worth showing.
  assistCard.hidden = state.readOnly;
  if (state.readOnly) return;
  // Per chapter, because the card reports one chapter's detection pass and a
  // stale "Done · 18 page(s) processed" from the chapter before it is a
  // statement about the wrong chapter.
  assistProgressBar.style.width = "0%";
  // MAGI being off greys out Detect and Remark only (syncAssistCard). Reorder
  // needs no model at all, so disabling the whole bar with it would take it too.
  assistCard.classList.remove("disabled");
  assistStatus.textContent = state.magiEnabled ? "Idle" : "MAGI is off in config.json - Reorder still works";
  syncAssistCard();
}

// Takes the server's marks for the chapter on screen without leaving the page
// you're on, the tool you're holding or the zoom you set - for when a reorder
// rewrote them server-side. A full applyChapter would reset all of those for
// what is, from the user's side, just the panel numbers moving.
export async function reloadChapterMarks() {
  let payload;
  try { payload = await api("/api/chapter"); } catch { return; }
  if (!state.chapter || payload.chapter !== state.chapter.chapter) return;
  state.chapter.marks = payload.marks;
  state.chapterRevision = payload.revision || 0;
  state.touchedPages = new Set(payload.touched || []);
  state.decidedPages = new Set(payload.decided || []);
  state.editSeq = {};
  for (const p of payload.pages) state.pageMarksCache[p.filename] = payload.marks[p.filename] || [];
  state.marks = state.pageMarksCache[currentFilename()];
  if (state.selectedId !== null && !state.marks.some(m => m.id === state.selectedId)) state.selectedId = null;
  render();
  renderOutline();
}

export async function gotoChapter(index, startPage = 0) {
  if (!state.chapter || index === state.chapter.chapter_index) return;
  if (index < 0 || index >= state.chapter.chapter_total) return;
  await flushSave(true);
  try {
    const payload = await api("/api/goto", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index }),
    });
    await applyChapter(payload, startPage);
  } catch (e) {
    alert("Couldn't switch chapter: " + e.message);
  }
}

// Save: the chapter on screen and every chapter with unsaved marks are
// written, the session ends, and the terminal carries on. Pressed twice (a
// double Ctrl+S) it saves once - the second request would reach a server
// that is already shutting down and report a failure that isn't one.
let exiting = false;

export async function saveAndExit() {
  if (exiting || !state.chapter) return;
  exiting = true;
  await flushSave(true);
  let res;
  try {
    res = await api("/api/finish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
  } catch (e) {
    exiting = false;
    alert("Failed to save: " + e.message);
    return;
  }
  if (state.readOnly) {
    saveOverlayTitle.textContent = "Closed";
    saveOverlayText.innerHTML =
      "Nothing was changed - this was a read-only session.<br>You can close this tab now.";
  } else {
    const saved = res.saved_chapters || [];
    const list = saved.length > 12 ? `${saved.slice(0, 12).join(", ")} and ${saved.length - 12} more` : saved.join(", ");
    saveOverlayTitle.textContent = state.chapter.chapter_total > 1 ? `Saved — ${saved.length} chapter(s)` : "Saved";
    saveOverlayText.innerHTML =
      (state.chapter.chapter_total > 1 && saved.length ? `crops.json written for ch ${list}.<br>` : "crops.json is written.<br>") +
      "The pipeline will continue in your terminal - you can close this tab now.";
  }
  saveOverlay.classList.add("visible");
  setTimeout(() => { try { window.close(); } catch {} }, 400);
}

export async function init() {
  await loadShortcuts();
  await applyChapter(await api("/api/chapter"));
  pollDetectStatus();
  setInterval(pollDetectStatus, 1200);
}

prevChapterBtn.addEventListener("click", () => gotoChapter(state.chapter.chapter_index - 1));
nextChapterBtn.addEventListener("click", () => gotoChapter(state.chapter.chapter_index + 1));
saveBtn.addEventListener("click", saveAndExit);
window.addEventListener("beforeunload", () => flushSave(true));
