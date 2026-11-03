// Fitting a panel to the art under the mouse (double click on an unmarked
// stretch): from the nearest border above to the nearest below - a gutter's
// edge, a border the detector found with no gutter, or a neighbouring panel.

import { state, MIN_ROWS } from "./state.js";

export function fitAt(row) {
  const { gutters, borders } = state.chapter;
  if (gutters.some(g => row >= g.top && row < g.bottom)) return null;   // that is gutter, not art
  let top = 0, bottom = state.totalHeight;
  const consider = (y) => {
    if (y <= row && y > top) top = y;
    if (y > row && y < bottom) bottom = y;
  };
  for (const g of gutters) { consider(g.bottom); consider(g.top); }
  for (const y of borders) consider(y);
  for (const m of state.marks) { consider(m.bottom); consider(m.top); }
  return bottom - top >= MIN_ROWS ? [top, bottom] : null;
}
