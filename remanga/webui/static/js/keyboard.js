// Global keyboard shortcuts and the Draw/Adjust tool toggle they (and the
// toolbar buttons) share. Which keys trigger which action is configurable -
// see shortcuts.js (matchAction) and ShortcutsConfig in remanga/config.py -
// this file just dispatches whatever action comes back.

import { stage, toolDrawBtn, toolAdjustBtn } from "./dom.js";
import { state } from "./state.js";
import { deleteMark, markFullPage } from "./marks.js";
import { stepPage } from "./page-nav.js";
import { saveAndExit } from "./chapter-nav.js";
import { resetView } from "./zoom-pan.js";
import { matchAction } from "./shortcuts.js";

export function setMode(next) {
  state.mode = next;
  toolDrawBtn.classList.toggle("active", state.mode === "draw");
  toolAdjustBtn.classList.toggle("active", state.mode === "adjust");
  stage.classList.toggle("adjust-mode", state.mode === "adjust");
}
toolDrawBtn.addEventListener("click", () => setMode("draw"));
toolAdjustBtn.addEventListener("click", () => setMode("adjust"));

const ACTION_HANDLERS = {
  save: (e) => { e.preventDefault(); saveAndExit(); },
  mark_full_page: (e) => { e.preventDefault(); markFullPage(); },
  tool_draw: () => setMode("draw"),
  tool_adjust: () => setMode("adjust"),
  prev_page: () => stepPage(-1),
  next_page: () => stepPage(1),
  delete_mark: () => { if (state.selectedId !== null) deleteMark(state.selectedId); },
  reset_view: (e) => { e.preventDefault(); resetView(); },
};

// A read-only session keeps every navigation and view binding and drops the
// three that would change something. Save is dropped too: in a viewer its
// button means "close", and a reflex Ctrl+S should not end the session.
const READ_ONLY_BLOCKED = new Set(["save", "mark_full_page", "delete_mark"]);

document.addEventListener("keydown", (e) => {
  const action = matchAction(e);
  if (!action) return;
  if (state.readOnly && READ_ONLY_BLOCKED.has(action)) return;
  ACTION_HANDLERS[action](e);
});
