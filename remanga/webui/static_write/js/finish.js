// The Save button: every panel's text to the server, then end the session.

import { finishSession, postText } from "./api.js";
import { panels, textOf, writtenCount } from "./state.js";

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

  const result = await finishSession();
  if (result.ok) {
    document.body.innerHTML = `<main><h1 style="padding-top:60px;text-align:center">
      ✓ Saved ${result.written}/${result.total_panels} panel(s) to narration.json — you can close this tab.
    </h1></main>`;
  }
}

export function wireFooter() {
  document.getElementById("btn-save").addEventListener("click", saveNarration);
}
