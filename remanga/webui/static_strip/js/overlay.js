// What is drawn over the strip: the verified gutters (ticks at the left), the
// rows no panel covers (hatched - what would be left out), and the panels -
// each in its own colour with a big number, the selected one in focus with
// everything else dimmed.

import { state } from "./state.js";
import { rowToY } from "./geometry.js";

const guttersLayer = document.getElementById("gutters"), marksLayer = document.getElementById("marks");
export const PALETTE = ["#4ebf71", "#4aa3ff", "#f0c14b", "#e16bd6", "#50d6c9", "#ff8a5c", "#a78bfa", "#c5e063"];
export const colorOf = (index) => PALETTE[index % PALETTE.length];

function box(layer, cls, top, height, extra = {}) {
  const el = document.createElement("div");
  el.className = cls;
  Object.assign(el.style, { top: top + "px", height: Math.max(2, height) + "px", ...extra });
  layer.appendChild(el);
  return el;
}

export function drawGutters(lo, hi) {
  guttersLayer.replaceChildren();
  if (!state.chapter) return;
  if (state.showGutters) {
    for (const g of state.chapter.gutters) {
      const top = rowToY(g.top), bottom = rowToY(g.bottom);
      if (bottom < lo || top > hi) continue;
      box(guttersLayer, `gutter ${g.strength}`, top, bottom - top).title =
        `${g.strength} gutter, rgb(${g.color.join(", ")}) - rows ${g.top}-${g.bottom}`;
    }
  }
  // Rows no panel covers: what the video would leave out.
  let covered = 0;
  const gap = (from, to) => {
    const top = rowToY(from), bottom = rowToY(to);
    if (to - from >= 8 && bottom > lo && top < hi) box(guttersLayer, "gap", top, bottom - top);
  };
  for (const m of state.marks) {
    if (m.top > covered) gap(covered, m.top);
    covered = Math.max(covered, m.bottom);
  }
  if (covered < state.totalHeight) gap(covered, state.totalHeight);
}

export function drawMarks(lo, hi) {
  marksLayer.replaceChildren();
  state.marks.forEach((m, i) => {
    const selected = m.id === state.selected;
    const top = rowToY(m.top), bottom = rowToY(m.bottom);
    if (!selected && (bottom < lo || top > hi)) return;
    const el = box(marksLayer, "band" + (selected ? " selected" : "") + (m.id === state.hover ? " hover" : ""),
                   top, bottom - top,
                   { left: m.left * state.width + "px", width: (m.right - m.left) * state.width + "px" });
    el.style.setProperty("--c", colorOf(i));
    const label = document.createElement("span");
    label.className = "label mono";
    label.textContent = String(i + 1);
    el.appendChild(label);
    if (selected) {
      for (const edge of ["top", "bottom", "left", "right"]) {
        const h = document.createElement("div");
        h.className = `handle ${edge}` + (state.activeEdge === edge ? " active" : "");
        el.appendChild(h);
      }
    }
  });
}
