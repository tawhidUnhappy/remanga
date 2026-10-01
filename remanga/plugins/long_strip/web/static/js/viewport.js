// The strip on screen, as a sliding window: only the tiles and marks within
// about a screen of what is visible exist in the page - a 90,000-row chapter
// is a handful of small images at any moment, never all of them.

import { state } from "./state.js";
import { layout, rowToY } from "./geometry.js";
import { drawGutters, drawMarks } from "./overlay.js";

const $ = (id) => document.getElementById(id);
const reader = $("reader"), stage = $("stage");
const tilesLayer = $("tiles");
const mounted = new Map();   // "run-number" -> <img>
let frame = null;

export function relayout() {
  const height = layout(reader.clientWidth);
  stage.style.width = state.width + "px";
  stage.style.height = Math.ceil(height) + "px";
  for (const img of mounted.values()) img.remove();
  mounted.clear();
  draw();
}

export function draw() {
  if (frame) return;
  frame = requestAnimationFrame(() => { frame = null; drawNow(); });
}

function windowRange() {
  const view = reader.clientHeight;
  return [reader.scrollTop - view, reader.scrollTop + 2 * view];
}

function drawNow() {
  const [lo, hi] = windowRange();
  drawTiles(lo, hi);
  drawGutters(lo, hi);
  drawMarks(lo, hi);
  drawLines();
}

function drawTiles(lo, hi) {
  const wanted = new Set();
  state.runs.forEach((run, r) => {
    if (run.dTop > hi || run.dTop + run.dHeight < lo) return;
    for (let n = 0; n < run.tiles; n++) {
      const top = run.dTop + n * run.tile_rows * run.scale;
      const rows = Math.min(run.tile_rows, run.height - n * run.tile_rows);
      const height = rows * run.scale;
      if (top > hi || top + height < lo) continue;
      const key = `${r}-${n}`;
      wanted.add(key);
      if (mounted.has(key)) continue;
      const img = document.createElement("img");
      img.src = `/api/tile/${r}/${n}.jpg`;
      img.draggable = false;
      Object.assign(img.style, { top: top + "px", height: height + "px" });
      tilesLayer.appendChild(img);
      mounted.set(key, img);
    }
  });
  for (const [key, img] of mounted) if (!wanted.has(key)) { img.remove(); mounted.delete(key); }
}

function drawLines() {
  document.getElementById("stage").classList.toggle("new-mode", state.mode === "new");
  const line = (id, row) => {
    const el = $(id);
    el.style.display = row === null ? "none" : "block";
    if (row !== null) el.style.top = rowToY(row) + "px";
  };
  line("guide", state.guide);
  line("pendingLine", state.pending);
  const readout = $("readout");
  readout.style.display = state.readout ? "block" : "none";
  if (state.readout) {
    Object.assign(readout.style, { left: state.readout.x + 14 + "px", top: state.readout.y + 14 + "px" });
    readout.textContent = state.readout.text;
  }
}

// Scrolls so `row` sits a third of the way down the window.
export function scrollToRow(row) {
  reader.scrollTo({ top: rowToY(row) - reader.clientHeight / 3, behavior: "smooth" });
}

reader.addEventListener("scroll", draw, { passive: true });
window.addEventListener("resize", relayout);
