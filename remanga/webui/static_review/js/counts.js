// "2 / 40 flagged" in the header, and what it means for the buttons: Approve
// is only available while nothing is flagged.

import { flaggedCount, panels } from "./state.js";

export function updateCounts() {
  document.getElementById("counts").innerHTML = `<b>${flaggedCount()}</b> / ${panels.length} flagged`;
  document.getElementById("btn-approve").disabled = flaggedCount() > 0;
}
