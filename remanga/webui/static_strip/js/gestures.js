// The mouse on the strip, the way the Panel Marker works: a click selects the
// mark under it (the smallest, where marks overlap); only the selected mark
// moves (drag inside) or resizes (drag an edge - top, bottom, or a side);
// dragging anywhere else draws a new mark, full width (Alt: only as wide as
// the drag). Edges snap to verified gutters and to other marks (Shift: don't).
// Right-click deletes. After N, a click finishes the started line.

import { state, newMark, markById, select, MIN_ROWS, MIN_WIDTH } from "./state.js";
import { at, edgeAt, markAt, snap } from "./hit.js";
import { commit, snapshot } from "./history.js";
import { draw } from "./viewport.js";
import { status } from "./status.js";
import { fitAt } from "./fit.js";

const stage = document.getElementById("stage");
const DRAG_START_PX = 4;
const CURSORS = { top: "ns-resize", bottom: "ns-resize", left: "ew-resize", right: "ew-resize" };
let drag = null;

const clampFrac = (v) => Math.max(0, Math.min(1, v));

function readout(p, m) {
  state.readout = { x: p.x, y: p.y, text: `${m.top} → ${m.bottom} · ${m.bottom - m.top} rows` };
}

stage.addEventListener("pointerdown", (evt) => {
  if (evt.button !== 0 || state.finished) return;
  const p = at(evt);
  stage.setPointerCapture(evt.pointerId);
  const selected = state.mode === "new" ? null : markById(state.selected);
  const edge = selected && edgeAt(selected, p);
  const before = snapshot();
  if (selected && edge) {
    drag = { kind: "edge", edge, mark: selected, before };
    state.activeEdge = edge;
  } else if (selected && markAt(p) === selected) {
    drag = { kind: "move", mark: selected, start: p, orig: { ...selected }, before };
    state.activeEdge = "move";
  } else {
    drag = { kind: "press", start: p, before };
  }
  evt.preventDefault();
});

stage.addEventListener("pointermove", (evt) => {
  const p = at(evt);
  state.pointer = p;
  if (!drag) { hoverCursor(p); return; }
  if (drag.kind === "press" && Math.hypot(p.x - drag.start.x, p.y - drag.start.y) > DRAG_START_PX) {
    drag.mark = newMark(drag.start.row, drag.start.row);
    drag.kind = "draw";
    drag.alt = evt.altKey;
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
  else if (edge === "bottom") m.bottom = Math.max(snap(p.row, evt, m.id), m.top + MIN_ROWS);
  else if (edge === "left") m.left = Math.min(clampFrac(p.frac), m.right - MIN_WIDTH);
  else m.right = Math.max(clampFrac(p.frac), m.left + MIN_WIDTH);
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
  if (orig.left > 0 || orig.right < 1) {   // a narrowed mark moves sideways too
    const width = orig.right - orig.left;
    m.left = clampFrac(Math.min(1 - width, orig.left + (p.frac - start.frac)));
    m.right = m.left + width;
  }
}

function drawMark(p, evt) {
  const m = drag.mark, start = drag.start;
  const row = snap(p.row, evt, m.id);
  const startRow = snap(start.row, evt, m.id);
  m.top = Math.min(startRow, row);
  m.bottom = Math.max(startRow, row);
  if (drag.alt) { m.left = Math.min(start.frac, p.frac); m.right = Math.max(start.frac, p.frac); }
}

stage.addEventListener("pointerup", (evt) => {
  if (!drag) return;
  const p = at(evt), d = drag;
  drag = null;
  state.guide = null;
  state.readout = null;
  if (d.kind === "press") {
    if (state.mode === "new") status("Drag down (or up) the strip to mark the new panel - Esc cancels.");
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

stage.addEventListener("pointerleave", () => {
  if (drag) return;
  state.pointer = null;
  if (state.hover !== null) { state.hover = null; draw(); }
});

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
