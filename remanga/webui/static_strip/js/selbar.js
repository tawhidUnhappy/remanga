// The bar over the strip while a panel is selected: which one, its rows, and
// what can be done to it - so what is in focus is never a guess.

import { state, markById, select } from "./state.js";
import { colorOf } from "./overlay.js";
import { deleteSelected, mergeWithNext, splitAtPointer } from "./edits.js";

const bar = document.getElementById("selbar");

export function renderSelbar() {
  const m = markById(state.selected);
  bar.classList.toggle("visible", !!m);
  if (!m) return;
  const index = state.marks.indexOf(m);
  const sides = m.left > 0 || m.right < 1 ? ` · ${Math.round(m.left * 100)}–${Math.round(m.right * 100)}% of the width` : "";
  document.getElementById("selTitle").textContent = `Panel ${index + 1}`;
  document.getElementById("selTitle").style.color = colorOf(index);
  document.getElementById("selRows").textContent = `rows ${m.top}–${m.bottom} · ${m.bottom - m.top} tall${sides}`;
}

document.getElementById("selSplit").addEventListener("click", () => {
  const m = markById(state.selected);
  if (m && !state.pointer) state.pointer = { row: Math.round((m.top + m.bottom) / 2), frac: 0.5 };
  splitAtPointer();
});
document.getElementById("selMerge").addEventListener("click", mergeWithNext);
document.getElementById("selDelete").addEventListener("click", deleteSelected);
document.getElementById("selDone").addEventListener("click", () => select(null));
