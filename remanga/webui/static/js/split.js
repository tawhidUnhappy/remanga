// The split key (S): the mark under the mouse cut in two where the mouse is.

import { state, currentFilename } from "./state.js";
import { render } from "./render.js";
import { stage } from "./dom.js";
import { notice } from "./assist-status.js";
import { isTooSmall, markDirty, markTouched, minMarkSize } from "./marks.js";

// Where the mouse last was over the page, in natural page pixels - the line
// `s` (splitMark) cuts along. Null while it is off the page.
let pointer = null;
document.addEventListener("mousemove", (e) => {
  const page = state.chapter?.pages[state.pageIndex];
  if (!page) return;
  const rect = stage.getBoundingClientRect();
  const x = (e.clientX - rect.left) / state.scale, y = (e.clientY - rect.top) / state.scale;
  pointer = x >= 0 && y >= 0 && x <= page.width && y <= page.height ? { x, y } : null;
});

// `s`: cuts the mark under the mouse in two where the mouse is - top and
// bottom (a line across, for a webtoon panel that ran two scenes together) or
// left and right (a line down, two panels side by side), as the Options'
// "S splits a mark" says. The selected mark wins where marks overlap. Both
// halves must clear the size floor, so a cut an inch from an edge is refused
// rather than leaving a sliver. Left/right halves are numbered in the manga's
// reading direction: right first for right-to-left.
export function splitMark() {
  if (state.readOnly) return;
  if (!pointer) { notice("Point at a mark on the page to split it there"); return; }
  const { x, y } = pointer;
  const inside = m => x > m.x && x < m.x + m.w && y > m.y && y < m.y + m.h;
  const selected = state.marks.find(m => m.id === state.selectedId);
  const target = selected && inside(selected) ? selected : state.marks.filter(inside).at(-1);
  if (!target) { notice("Point at a mark on the page to split it there"); return; }
  const vertical = state.chapter.split_direction === "vertical";
  const first = { ...target, src: "manual" };
  const second = { ...target, id: "local-" + (state.nextLocalId++), src: "manual" };
  if (vertical) {
    first.w = x - target.x;
    Object.assign(second, { x, w: target.x + target.w - x });
  } else {
    first.h = y - target.y;
    Object.assign(second, { y, h: target.y + target.h - y });
  }
  if (isTooSmall(first) || isTooSmall(second)) {
    notice(`Too close to the edge — each half needs at least ${minMarkSize()} px`);
    return;
  }
  const halves = vertical && state.chapter.reading_direction === "right_to_left" ? [second, first] : [first, second];
  markTouched();
  state.marks.splice(state.marks.indexOf(target), 1, ...halves);
  state.pageMarksCache[currentFilename()] = state.marks;
  state.selectedId = null;
  markDirty();
  render();
}
