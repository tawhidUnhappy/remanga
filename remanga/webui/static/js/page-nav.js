// Moving between pages. Within a chapter that's loadPage; past either end of
// one, stepPage carries on into the neighbouring chapter, so a session reads
// as one run of pages: → on a chapter's last page is the next chapter's first
// page, ← on its first page is the previous chapter's last.
//
// The chapter level - loading one, switching to another, saving - is
// chapter-nav.js, which imports this file. The chapter switch here is reached
// through a dynamic import (as outline.js does), so the static dependency
// still points one way only.

import { pageImg, pageNumEl, prevPageBtn, nextPageBtn } from "./dom.js";
import { state, currentPage } from "./state.js";
import { flushSave } from "./marks.js";
import { resetView } from "./zoom-pan.js";

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
  // Only the very first page of the session and the very last one are ends.
  const { chapter_index: chapterIndex, chapter_total: chapterTotal } = state.chapter;
  prevPageBtn.disabled = state.pageIndex === 0 && chapterIndex === 0;
  nextPageBtn.disabled = state.pageIndex === state.chapter.pages.length - 1 && chapterIndex >= chapterTotal - 1;

  await new Promise(resolve => {
    pageImg.onload = resolve;
    pageImg.src = `/api/pages/${page.filename}`;
  });

  resetView();
  state.pageLoaded = true;
}

// One chapter switch at a time: a held arrow key on a chapter's last page
// would otherwise fire a switch per key repeat while the first is in flight.
let crossing = false;

export async function stepPage(delta) {
  if (!state.chapter || crossing) return;
  const target = state.pageIndex + delta;
  if (target >= 0 && target < state.chapter.pages.length) {
    await loadPage(target);
    return;
  }
  const index = state.chapter.chapter_index + (delta > 0 ? 1 : -1);
  if (index < 0 || index >= state.chapter.chapter_total) return;
  crossing = true;
  try {
    const { gotoChapter } = await import("./chapter-nav.js");
    // Back lands on the previous chapter's LAST page - the page just before
    // this one in reading order - not its first.
    await gotoChapter(index, delta > 0 ? 0 : Number.MAX_SAFE_INTEGER);
  } finally {
    crossing = false;
  }
}

prevPageBtn.addEventListener("click", () => stepPage(-1));
nextPageBtn.addEventListener("click", () => stepPage(1));
window.addEventListener("resize", resetView);
