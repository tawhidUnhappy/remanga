// The Options fold: auto-save, auto-order, and the scope the buttons default
// to. All three describe how someone works rather than anything about today's
// manga, so they are saved to config.json as well as to this session.

import { actionsOptions, autoOrderToggle, autoSaveToggle, optSummary } from "./dom.js";
import { postJson } from "./api.js";
import { notice } from "./assist-status.js";
import { reloadMarks } from "./reload-marks.js";
import { render } from "./render.js";
import { state } from "./state.js";

const OPTIONS_OPEN_KEY = "remanga.marker.optionsOpen";

// What's switched on, readable with Options folded away - so folding them
// never hides that auto-order is quietly re-sorting every page.
export function syncOptionsSummary() {
  const on = [];
  if (autoOrderToggle.checked) on.push("auto-order");
  if (!autoSaveToggle.checked) on.push("auto-save off");
  optSummary.textContent = on.length ? `· ${on.join(" · ")}` : "";
}

export async function saveSetting(values) {
  try {
    const res = await postJson("/api/settings", values);
    // The payload the tab is holding is what syncAssistCard reads on the next
    // chapter change, so it has to learn what was just saved too.
    if (state.chapter) Object.assign(state.chapter, {
      auto_save: res.auto_save, auto_order: res.auto_order,
      detect_scope: values.scope ?? state.chapter.detect_scope,
    });
    syncOptionsSummary();
    if ("auto_order" in values) {
      state.autoOrder = !!res.auto_order;
      // Turning it on reorders the chapter on screen before the response comes
      // back (and every other chapter behind it): take that order now, and let
      // the panel list drop or bring back its drag handles.
      await reloadMarks();
      render();
      notice(state.autoOrder
        ? "Auto-order on - every chapter is kept in reading order"
        : "Auto-order off - drag panels in the list to order them yourself");
    }
  } catch (e) {
    notice("Couldn't save that setting: " + e.message);
  }
}

// Options stays however it was left, per browser - it's a fold, not a setting
// anyone else needs to share, and it must work with no storage at all.
export function restoreOptionsFold() {
  try { actionsOptions.open = localStorage.getItem(OPTIONS_OPEN_KEY) === "1"; } catch {}
  actionsOptions.addEventListener("toggle", () => {
    try { localStorage.setItem(OPTIONS_OPEN_KEY, actionsOptions.open ? "1" : "0"); } catch {}
  });
}
