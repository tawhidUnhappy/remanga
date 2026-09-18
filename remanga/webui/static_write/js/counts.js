// "12 / 40 written" in the header - recomputed from the text map, so it is
// right whether a panel was typed here or came from a card that is no
// longer even mounted.

import { panels, writtenCount } from "./state.js";

export function updateCounts() {
  document.getElementById("counts").innerHTML = `<b>${writtenCount()}</b> / ${panels.length} written`;
}
