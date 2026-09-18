// All mutable app state lives on this one object so every module reads/writes
// the same source of truth instead of juggling its own copy. Marks are kept
// in NATURAL image pixel space (the resolution of the source page file);
// `state.scale` maps that to on-screen display pixels for rendering and
// mouse-event math only.

export const state = {
  chapter: null,            // the /api/chapter payload: { project, chapter, chapter_index,
                            // chapter_total, chapters, has_next, pages, marks, touched, ... }
  pageMarksCache: {},       // filename -> [{id,x,y,w,h,src}] in NATURAL pixel space
  touchedPages: new Set(),
  // Pages the user deliberately emptied - a decision, drawn differently in
  // the outline from a page that simply hasn't been marked yet. Narrower
  // than touchedPages on purpose: navigating past a page touches it (the
  // autosave posts the page you leave) but decides nothing.
  decidedPages: new Set(),
  // The server's revision of the chapter on screen. It moves when a reorder
  // rewrites marks server-side; the tab sends it with every autosave
  // and reloads when the two disagree (see marks.js flushSave, magi.js poll).
  chapterRevision: 0,
  // Per page, how many edits have been made - so an autosave's reply (which
  // may carry the page back in reading order) is only adopted if nothing was
  // drawn while that request was out.
  editSeq: {},
  // The auto-order switch. On, pages are kept in reading order by the server
  // and the panel list has no drag handles; off, the order is the user's.
  autoOrder: false,
  opNotice: null,           // { text, until } - a short-lived assist card message
  pageIndex: 0,
  marks: [],                // current page's marks (same array objects as in cache)
  selectedId: null,
  mode: "draw",
  scale: 1,
  nextLocalId: 1,
  saveDebounce: null,
  magiEnabled: false,
  readOnly: false,          // a `view-marks` session: look, navigate, change nothing.
                            // The server refuses writes too - this only shapes the UI
  clickToSelect: true,      // see MarkerConfig.click_to_select; set from /api/chapter in chapter-nav.js
  pageLoaded: false,        // false until the very first loadPage() has completed
  spaceHeld: false,         // hand-tool (pan) key held down
  panning: null,            // { startX, startY, startPanX, startPanY } while dragging to pan
  panX: 0,                  // page-stage position in canvasWrap, screen px (top-left corner)
  panY: 0,
  shortcutsModalOpen: false, // true while the Shortcuts menu is open, so keyboard.js
                              // doesn't also act on keys being recorded there
};

export function currentPage() {
  return state.chapter.pages[state.pageIndex];
}

export function currentFilename() {
  return currentPage().filename;
}
