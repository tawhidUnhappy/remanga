// All mutable app state lives on this one object so every module reads/writes
// the same source of truth instead of juggling its own copy. Marks are kept
// in NATURAL image pixel space (the resolution of the source page file);
// `state.scale` maps that to on-screen display pixels for rendering and
// mouse-event math only.

export const state = {
  chapter: null,            // { chapter, pages, magi_enabled }
  pageMarksCache: {},       // filename -> [{id,x,y,w,h,src}] in NATURAL pixel space
  touchedPages: new Set(),
  pageIndex: 0,
  marks: [],                // current page's marks (same array objects as in cache)
  selectedId: null,
  mode: "draw",
  scale: 1,
  nextLocalId: 1,
  saveDebounce: null,
  magiEnabled: false,
  clickToSelect: true,      // see MarkerConfig.click_to_select; set from /api/chapter in page-nav.js:init()
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
