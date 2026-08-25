// Mutating the current page's mark list: persisting to the server (debounced
// autosave, same as the old flushSave/markDirty pair), deleting a mark, and
// the two "add a mark" shortcuts that don't come from a mouse drag
// (clampBoxToPage is shared math, markFullPage is the Ctrl/Cmd+F shortcut).

import { state, currentFilename } from "./state.js";
import { api } from "./api.js";
import { render } from "./render.js";

// Flags the current page as user-touched, synchronously, with none of
// markDirty()'s other side effects (caching, debounced autosave). Call this
// the instant an edit GESTURE STARTS - a mark's mousedown, not its mouseup -
// so there's no window for a MAGI detection poll to land mid-gesture and
// still think the page is fair game to overwrite.
//
// magi.js's pollDetectStatus() runs every ~1.2s and merges freshly-detected
// AI boxes into state.marks for any page not yet in touchedPages. If that
// flag isn't set until markDirty() fires on mouseup (the old behavior), a
// poll landing during the drag itself - between mousedown and mouseup, on a
// page's very first edit - replaces state.marks (and re-renders) out from
// under the drag: the mark div drag-resize.js is holding a reference to gets
// torn down and rebuilt, so the rest of that drag's mousemoves silently stop
// doing anything visible, and the mark appears to snap back to its last AI
// position mid-gesture.
export function markTouched() {
  state.touchedPages.add(currentFilename());
}

export function markDirty() {
  state.pageMarksCache[currentFilename()] = state.marks;
  markTouched();
  clearTimeout(state.saveDebounce);
  state.saveDebounce = setTimeout(() => flushSave(false), 400);
}

export async function flushSave(immediate) {
  const filename = state.chapter?.pages[state.pageIndex]?.filename;
  if (!filename) return;
  clearTimeout(state.saveDebounce);
  try {
    await api(`/api/marks/${encodeURIComponent(filename)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state.pageMarksCache[filename] || []),
    });
  } catch (e) {
    if (immediate) console.error("Failed to save marks for", filename, e);
  }
}

export function deleteMark(id) {
  state.marks = state.marks.filter(m => m.id !== id);
  state.pageMarksCache[currentFilename()] = state.marks;
  if (state.selectedId === id) state.selectedId = null;
  markDirty();
  render();
}

// Clips a dragged box to the page - the mark becomes whatever part of the
// drag actually landed inside the page (the intersection), same as
// Canva/Illustrator when a drag starts outside the artboard. Computed from
// the box's actual edges (x+w, y+h), not by clamping the origin and then
// reusing the original, un-clipped width/height - doing that instead would
// keep the box's full dragged size but slide its origin to the page edge,
// so a drag that started above/left of the page would land bigger than
// what was actually dragged over the page.
export function clampBoxToPage(x, y, w, h) {
  const page = state.chapter.pages[state.pageIndex];
  const left = Math.max(0, x), top = Math.max(0, y);
  const right = Math.min(page.width, x + w), bottom = Math.min(page.height, y + h);
  return {
    x: left, y: top,
    w: Math.max(4, right - left),
    h: Math.max(4, bottom - top),
  };
}

// Ctrl/Cmd+F: wipe every mark on the current page and replace them with a
// single panel covering the whole page - for pages that are just one big
// panel (splash pages, single-panel spreads), so no per-panel drawing is
// needed for those at all.
export function markFullPage() {
  const page = state.chapter.pages[state.pageIndex];
  const full = { id: "local-" + (state.nextLocalId++), x: 0, y: 0, w: page.width, h: page.height, src: "manual" };
  state.marks = [full];
  state.pageMarksCache[currentFilename()] = state.marks;
  state.selectedId = full.id;
  markDirty();
  render();
}
