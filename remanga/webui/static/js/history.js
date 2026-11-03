// Ctrl+Z for the Panel Marker: each page's earlier states, recorded as its
// marks change. Every edit goes through marks.js:markDirty, which calls
// recordChange here, so every kind of edit is undoable without each gesture
// knowing about it.

import { state, currentFilename } from "./state.js";
import { render } from "./render.js";
import { notice } from "./assist-status.js";
import { markDirty } from "./marks.js";

// Per page: the states it was in before each change, oldest first, and the
// state it was last left in. Every edit goes through markDirty, so recording
// there makes every kind of edit undoable without each gesture knowing about
// it. Marks that arrive from outside (Detect, Remark, a server reorder) go
// through settleHistory, which records them as a step of their own - so an
// undo can take back a Detect as well as a drag. A page seen for the first
// time only starts its history there.
const HISTORY_LIMIT = 100;
const history = {};   // filename -> [JSON of marks], oldest first
const settled = {};   // filename -> JSON of the marks as last left

export function settleHistory(filename = currentFilename()) {
  const now = JSON.stringify(state.pageMarksCache[filename] || []);
  const before = settled[filename];
  // Marks the server put on this page are a step of their own: undoable,
  // like an edit.
  if (before !== undefined && before !== now) remember(filename, before);
  settled[filename] = now;
}

function remember(filename, snapshot) {
  const stack = (history[filename] ||= []);
  stack.push(snapshot);
  if (stack.length > HISTORY_LIMIT) stack.shift();
}

export function undo() {
  if (state.readOnly) return;
  const filename = currentFilename();
  const stack = history[filename];
  if (!stack?.length) { notice("Nothing to undo on this page"); return; }
  state.marks = JSON.parse(stack.pop());
  state.pageMarksCache[filename] = state.marks;
  if (!state.marks.some(m => m.id === state.selectedId)) state.selectedId = null;
  // Settled first, so the markDirty below saves this state without
  // recording it as a new change to undo.
  settled[filename] = JSON.stringify(state.marks);
  markDirty();
  render();
}


// Called by markDirty with the page just edited: its state before the edit
// becomes an undo step. A click that moved nothing records nothing.
export function recordChange(filename) {
  const now = JSON.stringify(state.marks);   // the page on screen - the one markDirty is for
  if (settled[filename] !== undefined && settled[filename] !== now) remember(filename, settled[filename]);
  settled[filename] = now;
}
