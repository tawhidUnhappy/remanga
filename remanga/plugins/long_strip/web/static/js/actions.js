// The toolbar's actions that talk to the server: auto marks and finishing.

import { state, newMark, select } from "./state.js";
import { postJson } from "./api.js";
import { asRows, commit, snapshot } from "./history.js";
import { status } from "./status.js";
import { hideLoading, showDone, showLoading } from "/shared/js/screens.js";

export const fromRows = (rows) => rows.map(([top, bottom, left = 0, right = 1]) => newMark(top, bottom, left, right));

export async function autoMarks() {
  status("Finding the panels...");
  const before = snapshot();
  try {
    const data = await postJson("/api/auto");
    commit(fromRows(data.panels), before);
    select(null);
    status(`Proposed again: ${state.marks.length} panels. Ctrl+Z takes it back.`);
  } catch (e) { status("Auto marks failed: " + e.message); }
}

export async function finish() {
  if (state.finished) return;
  const button = document.getElementById("finishBtn");
  button.disabled = true;
  showLoading("Saving and cutting the strip", "the panels become strip pages and crops.json");
  try {
    const data = await postJson("/api/finish", { panels: asRows() });
    state.finished = true;
    showDone({
      title: `Chapter ${data.chapter} is marked`,
      facts: [["Panels", data.panels], ["Strip pages cut", data.pages], ["Saved to", "strip_marks.json, crops.json"]],
      next: "Make PDF in the chapter's menu - the panels are cut from these marks.",
    });
  } catch (e) {
    hideLoading();
    button.disabled = false;
    status("Couldn't finish: " + e.message);
  }
}
