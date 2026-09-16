// The action bar: one scope control for all three buttons (assist-scope.js),
// the buttons themselves (assist-actions.js), the worker's status line
// (assist-status.js) and the Options fold (assist-settings.js).
//
// What's left here is the wiring - which DOM events call what - and the one
// call chapter-nav.js makes whenever a chapter is applied.

import { assistBtn, autoOrderToggle, autoSaveToggle, remarkBtn, reorderBtn, scopeSelect } from "./dom.js";
import { runDetect, runRemark, runReorder } from "./assist-actions.js";
import { fillRangeSelects, syncScopeUi } from "./assist-scope.js";
import { restoreOptionsFold, saveSetting, syncOptionsSummary } from "./assist-settings.js";
import { state } from "./state.js";

export { pollDetectStatus } from "./assist-status.js";

// Called whenever a chapter is applied, so the bar describes the session it
// is actually looking at (see chapter-nav.js).
export function syncAssistCard() {
  if (!state.chapter) return;
  scopeSelect.value = state.chapter.detect_scope || "chapter";
  autoSaveToggle.checked = state.chapter.auto_save !== false;
  state.autoOrder = !!state.chapter.auto_order;
  autoOrderToggle.checked = state.autoOrder;
  assistBtn.disabled = remarkBtn.disabled = !state.magiEnabled;
  fillRangeSelects();
  syncScopeUi();
  syncOptionsSummary();
}

restoreOptionsFold();

assistBtn.addEventListener("click", runDetect);
reorderBtn.addEventListener("click", runReorder);
remarkBtn.addEventListener("click", runRemark);
scopeSelect.addEventListener("change", () => { syncScopeUi(); saveSetting({ scope: scopeSelect.value }); });
autoSaveToggle.addEventListener("change", () => saveSetting({ auto_save: autoSaveToggle.checked }));
autoOrderToggle.addEventListener("change", () => saveSetting({ auto_order: autoOrderToggle.checked }));
