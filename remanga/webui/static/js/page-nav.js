// Moving between the pages of the chapter that's currently open. The chapter
// level - loading one, switching to another, saving - is chapter-nav.js,
// which imports this; keep the dependency pointing that way only.

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
  prevPageBtn.disabled = state.pageIndex === 0;
  nextPageBtn.disabled = state.pageIndex === state.chapter.pages.length - 1;

  await new Promise(resolve => {
    pageImg.onload = resolve;
    pageImg.src = `/api/pages/${page.filename}`;
  });

  resetView();
  state.pageLoaded = true;
}

prevPageBtn.addEventListener("click", () => loadPage(state.pageIndex - 1));
nextPageBtn.addEventListener("click", () => loadPage(state.pageIndex + 1));
window.addEventListener("resize", resetView);
