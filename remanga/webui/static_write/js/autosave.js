// Aggressive autosave: a panel's text reaches narration.json within
// SAVE_DEBOUNCE_MS of you pausing, immediately when the field loses focus,
// and on the way out of the tab - not only when Save is clicked. A closed
// tab, a killed server or a crash loses at most the last half-second of
// typing in the field that was focused, never the session.

import { beaconText, postText } from "./api.js";
import { textOf } from "./state.js";

const SAVE_DEBOUNCE_MS = 600;
// panel_id -> debounce timer, so a burst of keystrokes doesn't fire one POST
// per character.
const saveTimers = new Map();

export function scheduleSave(panelId, onSaveState) {
  clearTimeout(saveTimers.get(panelId));
  saveTimers.set(panelId, setTimeout(() => {
    // No longer pending - flushOnUnload only re-sends what is still queued.
    saveTimers.delete(panelId);
    saveText(panelId, onSaveState);
  }, SAVE_DEBOUNCE_MS));
}

// A debounce timer only fires after typing pauses - a field left mid-word
// when the tab is closed needs its own immediate save, not a wait that never
// comes.
export function flushSave(panelId, onSaveState) {
  clearTimeout(saveTimers.get(panelId));
  saveTimers.delete(panelId);
  saveText(panelId, onSaveState);
}

async function saveText(panelId, onSaveState) {
  try {
    await postText(panelId, textOf(panelId));
    onSaveState(true);
  } catch (err) {
    // Autosave failing shouldn't interrupt typing - just flag it visibly, so
    // an unnoticed connection drop doesn't silently lose progress. The next
    // successful save clears the flag.
    onSaveState(false);
    console.error(`Autosave failed for panel ${panelId}:`, err);
  }
}

// Belt-and-suspenders for a tab closed mid-debounce, before the timer fires.
// Only panels with a save still pending have anything new to flush.
export function flushOnUnload() {
  window.addEventListener("beforeunload", () => {
    for (const panelId of saveTimers.keys()) beaconText(panelId, textOf(panelId));
  });
}
