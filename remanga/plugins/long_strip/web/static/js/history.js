// Every change to the marks goes through commit(): tidied, remembered for
// undo/redo, drawn, and saved a moment later (so a closed tab loses nothing).

import { state, MIN_ROWS, MIN_WIDTH } from "./state.js";
import { postJson } from "./api.js";

const LIMIT = 100;
const undoStack = [], redoStack = [];
let listeners = [], saveTimer = null;

export const onChange = (fn) => listeners.push(fn);
const notify = () => listeners.forEach(fn => fn());

export const snapshot = () => JSON.stringify(state.marks);

// Nonsense cleaned up, overlaps kept - the same rules as marks.py:normalize.
export function tidy(marks) {
  const out = [];
  for (const m of marks) {
    const top = Math.max(0, Math.round(Math.min(m.top, m.bottom)));
    const bottom = Math.min(state.totalHeight, Math.round(Math.max(m.top, m.bottom)));
    const left = Math.max(0, Math.min(m.left, m.right)), right = Math.min(1, Math.max(m.left, m.right));
    if (bottom - top >= MIN_ROWS && right - left >= MIN_WIDTH) out.push({ ...m, top, bottom, left, right });
  }
  return out.sort((a, b) => a.top - b.top || a.left - b.left || a.bottom - b.bottom);
}

export function commit(next, before = snapshot()) {
  state.marks = tidy(next);
  if (snapshot() === before) { notify(); return false; }
  undoStack.push(before);
  if (undoStack.length > LIMIT) undoStack.shift();
  redoStack.length = 0;
  changed();
  return true;
}

function restore(json) {
  state.marks = JSON.parse(json);
  if (!state.marks.some(m => m.id === state.selected)) state.selected = null;
  changed();
}

export function undo() {
  if (!undoStack.length) return false;
  redoStack.push(snapshot());
  restore(undoStack.pop());
  return true;
}

export function redo() {
  if (!redoStack.length) return false;
  undoStack.push(snapshot());
  restore(redoStack.pop());
  return true;
}

export const canUndo = () => undoStack.length > 0;
export const canRedo = () => redoStack.length > 0;

function changed() {
  notify();
  clearTimeout(saveTimer);
  saveTimer = setTimeout(save, 500);
}

export const asRows = () => state.marks.map(m => [m.top, m.bottom, m.left, m.right]);

export async function save() {
  clearTimeout(saveTimer);
  if (state.finished) return;
  await postJson("/api/marks", { panels: asRows() });
}
