// Narration Writer: one flat list of panel cards, each showing the panel's
// cropped image and a field you type its narration line into. No flag/issue
// concept here (see the Reviewer for that) - this UI writes narration.json.
//
// This file is the boot and the wiring: load the chapter, fill the header,
// and connect the parts - the navigator jumps the list, the list reports
// which panel is centered, and a text change repaints the dot and the
// counter. Everything else is in its own module.

import { fetchNarration } from "./api.js";
import { flushOnUnload } from "./autosave.js";
import { updateCounts } from "./counts.js";
import { wireFooter } from "./finish.js";
import { wireLightbox } from "./lightbox.js";
import { buildNav, setActiveNav, setNavWritten } from "./nav.js";
import { chapter, loadChapter, onTextChanged, panels } from "./state.js";
import { initVirtualList, jumpToPanel } from "./virtual-list.js";

async function main() {
  let data;
  try {
    data = await fetchNarration();
  } catch {
    document.getElementById("loading").textContent = "Failed to load panels.";
    return;
  }
  loadChapter(data);

  document.getElementById("chapter-meta").textContent = `Chapter ${chapter} — ${panels.length} panel(s)`;
  document.title = `Narration Writer — Ch. ${chapter}`;
  document.getElementById("loading").style.display = "none";
  document.getElementById("hint").style.display = "block";
  document.getElementById("footer").style.display = "flex";

  onTextChanged(setNavWritten);
  onTextChanged(updateCounts);

  buildNav(jumpToPanel);
  initVirtualList({ onActive: setActiveNav });
  updateCounts();
  wireFooter();
  wireLightbox();
  flushOnUnload();
}

main();
