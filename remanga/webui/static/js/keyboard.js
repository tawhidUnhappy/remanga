// Global keyboard shortcuts and the Draw/Select tool toggle they (and the
// toolbar buttons) share. Which keys trigger which action is configurable -
// see shortcuts.js (matchAction) and ShortcutsConfig in remanga/config.py -
// this file just dispatches whatever action comes back.

import { stage, toolDrawBtn, toolSelectBtn } from "./dom.js";
import { state } from "./state.js";
import { deleteMark, markFullPage } from "./marks.js";
import { loadPage, saveAndContinue } from "./page-nav.js";
import { resetView } from "./zoom-pan.js";
import { matchAction } from "./shortcuts.js";

export function setMode(next) {
  state.mode = next;
  toolDrawBtn.classList.toggle("active", state.mode === "draw");
  toolSelectBtn.classList.toggle("active", state.mode === "select");
  stage.classList.toggle("select-mode", state.mode === "select");
}
toolDrawBtn.addEventListener("click", () => setMode("draw"));
toolSelectBtn.addEventListener("click", () => setMode("select"));

const ACTION_HANDLERS = {
  save: (e) => { e.preventDefault(); saveAndContinue(); },
  mark_full_page: (e) => { e.preventDefault(); markFullPage(); },
  tool_draw: () => setMode("draw"),
  tool_select: () => setMode("select"),
  prev_page: () => loadPage(state.pageIndex - 1),
  next_page: () => loadPage(state.pageIndex + 1),
  delete_mark: () => { if (state.selectedId !== null) deleteMark(state.selectedId); },
  reset_view: (e) => { e.preventDefault(); resetView(); },
};

document.addEventListener("keydown", (e) => {
  const action = matchAction(e);
  if (action) ACTION_HANDLERS[action](e);
});
