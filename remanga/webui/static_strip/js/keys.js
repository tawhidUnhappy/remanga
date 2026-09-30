// The keyboard. Arrow keys move the selected mark's active edge (Tab picks
// top / bottom / the whole mark) one row, ten with Shift.

import { state, newMark, markById, select, MIN_ROWS } from "./state.js";
import { commit, undo, redo } from "./history.js";
import { draw, relayout, scrollToRow } from "./viewport.js";
import { markAt } from "./hit.js";
import { status } from "./status.js";
import { autoMarks, finish } from "./actions.js";

const EDGES = ["move", "top", "bottom"];

export function splitAtPointer() {
  const p = state.pointer;
  const selected = markById(state.selected);
  const m = p && (selected && p.row > selected.top && p.row < selected.bottom ? selected : markAt(p));
  if (!m) { status("Point at a panel to split it there."); return; }
  const row = p.row;
  if (row - m.top < MIN_ROWS || m.bottom - row < MIN_ROWS) { status("Too close to the edge to split."); return; }
  const lower = newMark(row, m.bottom, m.left, m.right);
  commit([...state.marks.filter(x => x !== m), { ...m, bottom: row }, lower]);
  status("Panel split.");
}

function nudge(amount) {
  const m = markById(state.selected);
  if (!m) return;
  const next = { ...m };
  if (state.activeEdge === "top") next.top = Math.min(m.top + amount, m.bottom - MIN_ROWS);
  else if (state.activeEdge === "bottom") next.bottom = Math.max(m.bottom + amount, m.top + MIN_ROWS);
  else { next.top += amount; next.bottom += amount; }
  if (next.top < 0 || next.bottom > state.totalHeight) return;
  commit(state.marks.map(x => (x === m ? next : x)));
}

function step(direction) {
  if (!state.marks.length) return;
  const index = state.marks.findIndex(m => m.id === state.selected);
  const next = state.marks[Math.max(0, Math.min(state.marks.length - 1,
    index < 0 ? 0 : index + direction))];
  select(next.id);
  scrollToRow(next.top);
  draw();
}

function lineAfterLast() {
  if (!state.marks.length) return;
  state.pending = Math.min(Math.max(...state.marks.map(m => m.bottom)) + 1, state.totalHeight - 1);
  scrollToRow(state.pending);
  status("Line started after the last panel - click to mark down to there. Esc drops it.");
  draw();
}

function zoom(factor) {
  state.zoom = factor === 0 ? 1 : Math.max(0.4, Math.min(3, state.zoom * factor));
  relayout();
}

document.addEventListener("keydown", (evt) => {
  if (state.finished || evt.target.closest("input, select, textarea")) return;
  const key = evt.key.toLowerCase(), mod = evt.ctrlKey || evt.metaKey;
  const handled = () => evt.preventDefault();
  if (mod && key === "z") { handled(); if (!(evt.shiftKey ? redo() : undo())) status("Nothing to " + (evt.shiftKey ? "redo." : "undo.")); return; }
  if (mod && key === "y") { handled(); if (!redo()) status("Nothing to redo."); return; }
  if (mod && key === "s") { handled(); finish(); return; }
  if (mod || evt.altKey) return;
  switch (key) {
    case "s": splitAtPointer(); break;
    case "n": lineAfterLast(); break;
    case "r": autoMarks(); break;
    case "c": commit([]); status("Cleared - Ctrl+Z brings them back."); break;
    case "g":
      state.showGutters = !state.showGutters;
      document.getElementById("gutterToggle").checked = state.showGutters;
      draw(); break;
    case "j": step(1); break;
    case "k": step(-1); break;
    case "+": case "=": zoom(1.25); break;
    case "-": zoom(0.8); break;
    case "0": zoom(0); break;
    case "delete": case "backspace": {
      const m = markById(state.selected);
      if (m) { select(null); commit(state.marks.filter(x => x !== m)); status("Panel deleted."); }
      break;
    }
    case "tab":
      if (state.selected === null) return;
      state.activeEdge = EDGES[(EDGES.indexOf(state.activeEdge) + (evt.shiftKey ? 2 : 1)) % 3];
      status(`Arrow keys move: ${state.activeEdge === "move" ? "the whole panel" : "its " + state.activeEdge + " edge"}`);
      draw(); break;
    case "arrowup": nudge(evt.shiftKey ? -10 : -1); break;
    case "arrowdown": nudge(evt.shiftKey ? 10 : 1); break;
    case "escape":
      if (state.pending !== null) { state.pending = null; status("Line dropped."); }
      else select(null);
      draw(); break;
    default: return;
  }
  handled();
});
