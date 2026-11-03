// The bar over the strip while a panel is selected: which one, its rows, and
// what can be done to it - so what is in focus is never a guess.

import { state, markById, select } from "./state.js";
import { colorOf } from "./overlay.js";
import { deleteSelected, mergeWithNext, splitAtPointer } from "./edits.js";

const bar = document.getElementById("selbar"), reader = document.getElementById("reader");

export function renderSelbar() {
  const m = markById(state.selected);
  // The bar sits above the strip: showing or hiding it would shift the strip
  // under the mouse (mid-drag, a new mark jumped) - scroll by its height so
  // the strip stays put on screen.
  const before = reader.getBoundingClientRect().top;
  bar.classList.toggle("visible", !!m);
  reader.scrollTop += reader.getBoundingClientRect().top - before;
  if (!m) return;
  const index = state.marks.indexOf(m);
  document.getElementById("selTitle").textContent = `Panel ${index + 1}`;
  document.getElementById("selTitle").style.color = colorOf(index);
  document.getElementById("selRows").textContent = `rows ${m.top}–${m.bottom} · ${m.bottom - m.top} tall`;
}

document.getElementById("selSplit").addEventListener("click", () => {
  const m = markById(state.selected);
  if (m && !state.pointer) state.pointer = { row: Math.round((m.top + m.bottom) / 2), frac: 0.5 };
  splitAtPointer();
});
document.getElementById("selMerge").addEventListener("click", mergeWithNext);
document.getElementById("selDelete").addEventListener("click", deleteSelected);
document.getElementById("selDone").addEventListener("click", () => select(null));
