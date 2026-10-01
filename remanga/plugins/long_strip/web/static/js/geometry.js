// Strip rows <-> display pixels. Each run (images of one width) is scaled to
// the display width, so a cover of another width lines up with the rest.

import { state } from "./state.js";

const BASE_WIDTH = 760;

export function layout(readerWidth) {
  state.width = Math.round(Math.min(BASE_WIDTH, Math.max(320, readerWidth - 48)) * state.zoom);
  let dTop = 0;
  for (const run of state.runs) {
    run.scale = state.width / run.width;
    run.dTop = dTop;
    run.dHeight = run.height * run.scale;
    dTop += run.dHeight;
  }
  return dTop;   // the strip's display height
}

function runForRow(row) {
  for (const run of state.runs) if (row < run.top + run.height) return run;
  return state.runs[state.runs.length - 1];
}

function runForY(y) {
  for (const run of state.runs) if (y < run.dTop + run.dHeight) return run;
  return state.runs[state.runs.length - 1];
}

export function rowToY(row) {
  const run = runForRow(row);
  return run.dTop + (row - run.top) * run.scale;
}

export function yToRow(y) {
  const run = runForY(y);
  return Math.round(run.top + (y - run.dTop) / run.scale);
}

// How many rows a distance on screen is, around a row.
export const pxToRows = (px, row) => px / runForRow(row).scale;
