// The mouse on the strip, the way the Panel Marker works: a click selects the
// mark under it (the smallest, where marks overlap); only the selected mark
// moves (drag inside) or resizes (drag its top or bottom edge); dragging
// anywhere else draws a new mark. Marks are always the strip's full width -
// only rows are marked, the strip is never cut down its width. Edges snap to
// verified gutters and to other marks (Shift: don't). Right-click deletes.
// After N, a click finishes the started line. On the empty canvas around the
// strip a drag draws a new mark the same way, and a click lets go of the
// selection. While drawing, the box being dragged out is shown from where the
// drag started to the mouse, the mark it makes as a band across the strip.

import { state, newMark, markById, select, MIN_ROWS } from "./state.js";
import { at, edgeAt, markAt, snap } from "./hit.js";
import { commit, snapshot } from "./history.js";
import { draw } from "./viewport.js";
import { status } from "./status.js";
import { fitAt } from "./fit.js";

const stage = document.getElementById("stage");
const reader = document.getElementById("reader");
const DRAG_START_PX = 4;
const CURSORS = { top: "ns-resize", bottom: "ns-resize" };
let drag = null;

function readout(p, m) {
  state.readout = { x: p.x, y: p.y, text: `${m.top} → ${m.bottom} · ${m.bottom - m.top} rows` };
}

// Pressing on the canvas (not its scrollbars): on the strip it may grab the
// selected mark; beside it, it only ever draws or deselects.
reader.addEventListener("pointerdown", (evt) => {
  if (evt.button !== 0 || state.finished) return;
  const rect = reader.getBoundingClientRect();
  if (evt.clientX - rect.left >= reader.clientWidth || evt.clientY - rect.top >= reader.clientHeight) return;
  const p = at(evt), onStrip = stage.contains(evt.target);
  reader.setPointerCapture(evt.pointerId);
  const selected = state.mode === "new" || !onStrip ? null : markById(state.selected);
  const edge = selected && edgeAt(selected, p);
  const before = snapshot();
  if (selected && edge) {
    drag = { kind: "edge", edge, mark: selected, before };
    state.activeEdge = edge;
  } else if (selected && markAt(p) === selected) {
    drag = { kind: "move", mark: selected, start: p, orig: { ...selected }, before };
    state.activeEdge = "move";
  } else {
    drag = { kind: "press", start: p, onStrip, before };
  }
  evt.preventDefault();
});

reader.addEventListener("pointermove", (evt) => {
  if (!drag && !stage.contains(evt.target)) { offStrip(); return; }
  const p = at(evt);
  state.pointer = p;
  if (!drag) { hoverCursor(p); return; }
  if (drag.kind === "press" && Math.hypot(p.x - drag.start.x, p.y - drag.start.y) > DRAG_START_PX) {
    drag.mark = newMark(drag.start.row, drag.start.row);
    drag.kind = "draw";
    state.marks.push(drag.mark);
    select(drag.mark.id);
  }
  if (drag.kind === "edge") moveEdge(drag.mark, drag.edge, p, evt);
  else if (drag.kind === "move") moveMark(p, evt);
  else if (drag.kind === "draw") drawMark(p, evt);
  if (drag.mark) readout(p, drag.mark);
  draw();
});

function moveEdge(m, edge, p, evt) {
  if (edge === "top") m.top = Math.min(snap(p.row, evt, m.id), m.bottom - MIN_ROWS);
  else m.bottom = Math.max(snap(p.row, evt, m.id), m.top + MIN_ROWS);
}

function moveMark(p, evt) {
  const { mark: m, orig, start } = drag;
  const height = orig.bottom - orig.top;
  let top = orig.top + (p.row - start.row);
  const snappedTop = snap(top, evt, m.id);
  if (state.guide !== null) top = snappedTop;
  else {
    const snappedBottom = snap(top + height, evt, m.id);
    if (state.guide !== null) top = snappedBottom - height;
  }
  m.top = Math.max(0, Math.min(state.totalHeight - height, top));
  m.bottom = m.top + height;
}

function drawMark(p, evt) {
  const m = drag.mark, start = drag.start;
  const row = snap(p.row, evt, m.id);
  const startRow = snap(start.row, evt, m.id);
  m.top = Math.min(startRow, row);
  m.bottom = Math.max(startRow, row);
  state.dragBox = { x0: start.x, y0: start.y, x1: p.x, y1: p.y };
}

reader.addEventListener("pointerup", (evt) => {
  if (!drag) return;
  const p = at(evt), d = drag;
  drag = null;
  state.guide = null;
  state.readout = null;
  state.dragBox = null;
  if (d.kind === "press") {
    if (!d.onStrip) deselectAll();
    else if (state.mode === "new") status("Drag down (or up) the strip to mark the new panel - Esc cancels.");
    else click(p, evt);
  } else {
    if (d.kind === "draw") setMode("select");
    if (commit(state.marks, d.before)) status(d.kind === "draw" ? "Panel drawn." : "Panel adjusted.");
  }
  draw();
});

function click(p, evt) {
  if (state.pending !== null) {
    const row = snap(p.row, evt), top = Math.min(state.pending, row), bottom = Math.max(state.pending, row);
    state.pending = null;
    if (bottom - top < MIN_ROWS) { status("Too short for a panel."); return; }
    const m = newMark(top, bottom);
    select(m.id);
    commit([...state.marks, m]);
    status("Panel added.");
    return;
  }
  const m = markAt(p);
  select(m ? m.id : null);
}

function hoverCursor(p) {
  const selected = markById(state.selected);
  const edge = selected && edgeAt(selected, p);
  const hovered = markAt(p);
  stage.style.cursor = edge ? CURSORS[edge] : hovered && hovered === selected ? "move" : "crosshair";
  const id = hovered ? hovered.id : null;
  if (id !== state.hover) { state.hover = id; draw(); }
}

function offStrip() {
  state.pointer = null;
  if (state.hover !== null) { state.hover = null; draw(); }
}

stage.addEventListener("pointerleave", () => { if (!drag) offStrip(); });

stage.addEventListener("contextmenu", (evt) => {
  evt.preventDefault();
  const m = markAt(at(evt));
  if (!m) return;
  commit(state.marks.filter(x => x !== m));
  if (state.selected === m.id) select(null);
  status("Panel deleted - Ctrl+Z brings it back.");
});

// The New panel button (and A): the next drag draws a panel, even over others.
export function setMode(mode) {
  state.mode = mode;
  document.getElementById("newBtn")?.classList.toggle("active", mode === "new");
  if (mode === "new") status("New panel: drag down (or up) the strip over its art - Esc cancels.");
  draw();
}

// Double click on art no panel covers: a panel fitted to it.
stage.addEventListener("dblclick", (evt) => {
  const p = at(evt);
  if (markAt(p)) return;
  const fit = fitAt(p.row);
  if (!fit) { status("Nothing to fit there - that is gutter. Drag to draw a panel instead."); return; }
  const m = newMark(fit[0], fit[1]);
  commit([...state.marks, m]);
  select(m.id);
  status(`Panel fitted to rows ${fit[0]}-${fit[1]}.`);
});

// A click on the empty canvas around the strip (not the strip itself, not
// the selection bar) lets go of the selection - and of a started line or New
// panel mode, the same as Esc.
function deselectAll() {
  if (state.selected === null && state.pending === null && state.mode !== "new") return;
  state.pending = null;
  if (state.mode === "new") setMode("select");
  select(null);
  status("Deselected.");
  draw();
}
