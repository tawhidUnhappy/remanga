// Narration Reviewer: one flat list of panel cards, each showing the panel's
// cropped image, its narration line, and a review field. No canvas or drag
// state to manage - see the marker's static/js/ for that pattern; this UI
// only ever needs a list editor.
//
// This file is the boot and the wiring; everything else is in its own module.

import { fetchNarration } from "./api.js";
import { buildCard } from "./card.js";
import { updateCounts } from "./counts.js";
import { wireFooter } from "./finish.js";
import { chapter, loadChapter, onFlagsChanged, panels, roundNumber } from "./state.js";
import { wireLightbox } from "/shared/js/lightbox.js";

async function main() {
  let data;
  try {
    data = await fetchNarration();
  } catch {
    document.getElementById("loading").textContent = "Failed to load narration.json.";
    return;
  }
  loadChapter(data);

  document.getElementById("chapter-meta").textContent =
    `Chapter ${chapter} — round ${roundNumber} — ${panels.length} panel(s)`;
  document.title = `Narration Reviewer — Ch. ${chapter}`;
  document.getElementById("loading").style.display = "none";
  document.getElementById("hint").style.display = "block";
  document.getElementById("general-note-wrap").style.display = "block";
  document.getElementById("footer").style.display = "flex";

  onFlagsChanged(updateCounts);

  const list = document.getElementById("panel-list");
  list.innerHTML = "";
  for (const panel of panels) list.appendChild(buildCard(panel));

  updateCounts();
  wireFooter();
  wireLightbox();
}

main();
