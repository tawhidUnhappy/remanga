// Everything the Strip Marker's modules share. Rows are rows of the WHOLE
// chapter (the downloaded images stacked, each at its natural size); a mark's
// left/right are shares of the width, always 0 and 1 - a mark is full width.
// See remanga/plugins/long_strip/marks.py.

export const state = {
  chapter: null,        // the /api/strip payload
  runs: [],             // per run: {top, height, width, tile_rows, tiles, dTop, dHeight, scale}
  totalHeight: 0,
  marks: [],            // [{id, top, bottom, left, right}], sorted top to bottom
  selected: null,       // id of the selected mark
  activeEdge: "move",   // what the arrow keys move: "top" | "bottom" | "move"
  hover: null,          // id of the mark under the mouse
  pointer: null,        // {row, frac} under the mouse, or null off the strip
  pending: null,        // a started line (N), in rows
  mode: "select",       // "new" after the New panel button: the next drag draws
  zoom: 1,
  width: 760,           // display width of the strip, px
  showGutters: true,
  guide: null,          // row a snapping edge is on, for the guide line
  readout: null,        // {x, y, text} next to the mouse while dragging
  dragBox: null,        // {x0, y0, x1, y1} stage px: the box being dragged out
  nextId: 1,
  finished: false,
};

export const MIN_ROWS = 20;        // remanga/plugins/long_strip/marks.py MIN_MARK_ROWS
export const SNAP_PX = 10;         // how near (on screen) an edge snaps to a gutter
export const GRAB_PX = 8;          // how near (on screen) an edge is grabbed

export function newMark(top, bottom) {
  return { id: state.nextId++, top, bottom, left: 0, right: 1 };
}

export const markById = (id) => state.marks.find(m => m.id === id) || null;

// Every change of selection goes through here, so the panel list follows it.
export function select(id, edge = "move") {
  state.selected = id;
  state.activeEdge = edge;
  document.dispatchEvent(new Event("strip:select"));
}
