// The Save button: every panel's text to the server, then end the session.

import { finishSession, postText } from "./api.js";
import { panels, textOf, writtenCount } from "./state.js";
import { hideLoading, showDone, showLoading } from "/shared/js/screens.js";

async function saveNarration() {
  const emptyCount = panels.length - writtenCount();
  if (emptyCount > 0 && !confirm(`${emptyCount} panel(s) still have no narration text. Save anyway?`)) return;

  // Read from the text map, not the DOM: it holds every panel's text whether
  // or not that panel's card is currently mounted.
  try {
    for (const panel of panels) await postText(panel.panel_id, textOf(panel.panel_id));
  } catch (err) {
    alert(`Couldn't save every panel: ${err.message || err}\n\nNothing was finished - try again.`);
    return;
  }

  showLoading("Saving the narration");
  const result = await finishSession();
  if (result.ok) {
    showDone({
      title: "Narration saved",
      facts: [["Panels written", `${result.written} of ${result.total_panels}`], ["Saved to", "narration.json"]],
      next: "Make video in the chapter's menu.",
    });
  } else hideLoading();
}

export function wireFooter() {
  document.getElementById("btn-save").addEventListener("click", saveNarration);
}
