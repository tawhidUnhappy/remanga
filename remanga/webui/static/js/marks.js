// Mutating the current page's mark list: persisting to the server (debounced
// autosave, same as the old flushSave/markDirty pair), deleting a mark, and
// the two "add a mark" shortcuts that don't come from a mouse drag
// (clampBoxToPage is shared math, markFullPage is the Ctrl/Cmd+F shortcut).

import { state, currentFilename } from "./state.js";
import { api } from "./api.js";
import { render } from "./render.js";

export function markDirty() {
  state.pageMarksCache[currentFilename()] = state.marks;
  state.touchedPages.add(currentFilename());
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

export function clampBoxToPage(x, y, w, h) {
  const page = state.chapter.pages[state.pageIndex];
  x = Math.max(0, Math.min(x, page.width - 1));
  y = Math.max(0, Math.min(y, page.height - 1));
  w = Math.max(4, Math.min(w, page.width - x));
  h = Math.max(4, Math.min(h, page.height - y));
  return { x, y, w, h };
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
