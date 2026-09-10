// The chapter level of the app: loading a chapter into the open tab, moving
// between the chapters in this session, and the Save button - which is what
// "next chapter" actually is (save this one server-side, get the next one
// back, draw it here).
//
// Nothing in this file reloads the page. A chapter change is a fetch and a
// re-render, so the zoom, the tool, the shortcuts and the scroll position all
// survive it, and a session over twenty chapters is one browser tab that
// never blinks.
//
// page-nav.js is the level below (pages within one chapter) and is imported
// one-way from here - never the reverse, so there's no cycle between them.

import {
  saveOverlay, saveOverlayTitle, saveOverlayText, saveBtn, saveLabel, finishBtn,
  chapterNav, chapterName, chapterPos, prevChapterBtn, nextChapterBtn, pageTotalEl,
  assistCard, assistBtn, assistStatus, assistProgressBar,
  toolbar, viewBadge, hintToast, sidebarFooter,
} from "./dom.js";
import { state } from "./state.js";
import { api } from "./api.js";
import { flushSave } from "./marks.js";
import { loadPage } from "./page-nav.js";
import { pollDetectStatus, syncAssistCard } from "./magi.js";
import { loadShortcuts } from "./shortcuts.js";
import { setMode } from "./keyboard.js";
import { refreshOutline } from "./outline.js";

// Applies a chapter payload (/api/chapter, /api/goto, or /api/finish's
// advance - all three return the same shape) to the running app.
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
  // pipeline's mark step, a "remark" restart). It gets the screen it always
  // had: no chapter arrows, and a Save button that says what it does.
  chapterNav.hidden = total <= 1;
  chapterName.textContent = chapter;
  chapterPos.textContent = `${index + 1}/${total}`;
  prevChapterBtn.disabled = index === 0;
  nextChapterBtn.disabled = !hasNext;
  if (state.readOnly) {
    saveLabel.textContent = hasNext ? "Next chapter" : "Close viewer";
    finishBtn.hidden = true;
    return;
  }
  saveLabel.textContent = total <= 1 ? "Save & Continue"
    : hasNext ? "Save & Next chapter" : "Save & Finish";
  // Only worth offering while there are chapters left to skip.
  finishBtn.hidden = !hasNext;
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
  // saved - see MarkerSession.start_detection), so the card has nothing to
  // report and no button worth showing.
  assistCard.hidden = state.readOnly;
  if (state.readOnly) return;
  // Per chapter, because the card reports one chapter's detection pass and a
  // stale "Done · 18 page(s) processed" from the chapter before it is a
  // statement about the wrong chapter.
  assistProgressBar.style.width = "0%";
  if (!state.magiEnabled) {
    assistCard.classList.add("disabled");
    assistBtn.disabled = true;
    assistStatus.textContent = "Disabled in config.json";
    return;
  }
  assistCard.classList.remove("disabled");
  assistBtn.disabled = false;
  assistStatus.textContent = "Idle";
  syncAssistCard();
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

// Save this chapter. `end` forces the session to stop here instead of
// advancing - the "I'm done, don't walk me through the rest" answer, which
// has to exist because the terminal is blocked on this session and closing
// the tab tells it nothing.
export async function saveAndContinue(end = false, saveAll = false) {
  await flushSave(true);
  try {
    const res = await api("/api/finish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ end, save_all: saveAll }),
    });
    if (!res.done) {
      await applyChapter(res);
      return;
    }
    // With auto-save off, chapters edited or detected along the way are
    // still only in the session. This is the last moment anyone can be
    // asked, so they are - rather than the switch quietly costing an
    // afternoon, or overriding it and making the switch a lie.
    const unsaved = res.unsaved || [];
    if (unsaved.length && !saveAll) {
      const write = confirm(
        `${unsaved.length} chapter(s) still have marks that were never saved: ` +
        `${unsaved.join(", ")}.\n\nWrite their crops.json now?`);
      if (write) { await saveAndContinue(true, true); return; }
    }
    const done = state.chapter.chapter_index + 1;
    const total = state.chapter.chapter_total;
    if (state.readOnly) {
      saveOverlayTitle.textContent = "Closed";
      saveOverlayText.innerHTML =
        "Nothing was changed - this was a read-only session.<br>You can close this tab now.";
    } else {
      saveOverlayTitle.textContent = total > 1 ? `Saved — ${done} of ${total} chapters` : "Saved";
      saveOverlayText.innerHTML =
        "crops.json is written and the pipeline will continue in your terminal.<br>You can close this tab now.";
    }
    saveOverlay.classList.add("visible");
    setTimeout(() => { try { window.close(); } catch {} }, 400);
  } catch (e) {
    alert("Failed to save: " + e.message);
  }
}

export async function init() {
  await loadShortcuts();
  await applyChapter(await api("/api/chapter"));
  pollDetectStatus();
  setInterval(pollDetectStatus, 1200);
}

prevChapterBtn.addEventListener("click", () => gotoChapter(state.chapter.chapter_index - 1));
nextChapterBtn.addEventListener("click", () => gotoChapter(state.chapter.chapter_index + 1));
saveBtn.addEventListener("click", () => saveAndContinue(false));
finishBtn.addEventListener("click", () => {
  const left = state.chapter.chapter_total - state.chapter.chapter_index - 1;
  if (confirm(`Save this chapter and end the session? ${left} chapter(s) after it will be left unmarked.`)) {
    saveAndContinue(true);
  }
});
window.addEventListener("beforeunload", () => flushSave(true));
