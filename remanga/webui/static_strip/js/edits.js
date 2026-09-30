// Editing the panels from the keys and the selection bar: split where the
// mouse is, merge with the next panel (the fix for one cut in half), delete.

import { state, newMark, markById, select, MIN_ROWS } from "./state.js";
import { commit } from "./history.js";
import { markAt } from "./hit.js";
import { status } from "./status.js";

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

export function mergeWithNext() {
  const m = markById(state.selected);
  if (!m) { status("Select a panel first - M joins it with the next one."); return; }
  const next = state.marks.filter(x => x !== m && x.top >= m.top).sort((a, b) => a.top - b.top)[0];
  if (!next) { status("That is the last panel - nothing after it to join."); return; }
  const merged = newMark(Math.min(m.top, next.top), Math.max(m.bottom, next.bottom),
                         Math.min(m.left, next.left), Math.max(m.right, next.right));
  commit([...state.marks.filter(x => x !== m && x !== next), merged]);
  select(merged.id);
  status("Joined with the next panel - Ctrl+Z splits them again.");
}

export function deleteSelected() {
  const m = markById(state.selected);
  if (!m) return;
  select(null);
  commit(state.marks.filter(x => x !== m));
  status("Panel deleted - Ctrl+Z brings it back.");
}
