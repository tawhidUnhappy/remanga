// What is under the mouse, and where an edge snaps to.

import { state, GRAB_PX, SNAP_PX } from "./state.js";
import { pxToRows, yToRow } from "./geometry.js";

const stage = document.getElementById("stage");

// {row, frac, x, y} of a mouse event, in strip rows / width share / stage px.
export function at(evt) {
  const rect = stage.getBoundingClientRect();
  const x = evt.clientX - rect.left, y = evt.clientY - rect.top;
  return { x, y, row: yToRow(y), frac: Math.max(0, Math.min(1, x / state.width)) };
}

const contains = (m, p) => p.row >= m.top && p.row <= m.bottom && p.frac >= m.left && p.frac <= m.right;
const area = (m) => (m.bottom - m.top) * (m.right - m.left);

// The mark under the point: where marks overlap, the smallest - the one you
// can only reach there.
export function markAt(p) {
  const under = state.marks.filter(m => contains(m, p));
  return under.length ? under.reduce((a, b) => (area(b) < area(a) ? b : a)) : null;
}

// Which edge of `m` the point is on, if any: "top" | "bottom" | "left" | "right".
export function edgeAt(m, p) {
  const rows = pxToRows(GRAB_PX, p.row), frac = GRAB_PX / state.width;
  const inX = p.frac >= m.left - frac && p.frac <= m.right + frac;
  const inY = p.row >= m.top - rows && p.row <= m.bottom + rows;
  if (inX && Math.abs(p.row - m.top) <= rows) return "top";
  if (inX && Math.abs(p.row - m.bottom) <= rows) return "bottom";
  if (inY && Math.abs(p.frac - m.left) <= frac) return "left";
  if (inY && Math.abs(p.frac - m.right) <= frac) return "right";
  return null;
}

// Rows an edge snaps to: every verified gutter's edges, and every other mark's.
function snapRows(skipId) {
  const rows = [];
  for (const g of state.chapter.gutters) rows.push(g.top, g.bottom);
  for (const m of state.marks) if (m.id !== skipId) rows.push(m.top, m.bottom);
  return rows;
}

// `row`, pulled onto the nearest snap row within SNAP_PX on screen (Shift
// held = no snapping). Sets state.guide to show it.
export function snap(row, evt, skipId) {
  state.guide = null;
  if (evt.shiftKey) return row;
  const reach = pxToRows(SNAP_PX, row);
  let best = null;
  for (const r of snapRows(skipId)) {
    if (Math.abs(r - row) <= reach && (best === null || Math.abs(r - row) < Math.abs(best - row))) best = r;
  }
  if (best === null) return row;
  state.guide = best;
  return best;
}
