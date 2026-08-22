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
  pageLoaded: false,        // false until the very first loadPage() has completed
  spaceHeld: false,         // hand-tool (pan) key held down
  panning: null,            // { startX, startY, startScrollLeft, startScrollTop } while dragging to pan
};

export function currentPage() {
  return state.chapter.pages[state.pageIndex];
}

export function currentFilename() {
  return currentPage().filename;
}
