// The two ways out: Approve (nothing is wrong) and Submit (here is what is).
//
// Either way every panel's flag is pushed first - including the empty ones,
// which is what clears a panel that was flagged in a previous round and has
// since been emptied back out in this session.

import { finishReview, postFlag } from "./api.js";
import { flagOf, flaggedCount, panels } from "./state.js";
import { hideLoading, showDone, showLoading } from "/shared/js/screens.js";

async function submitReview(approved) {
  const generalNote = document.getElementById("general-note").value;

  try {
    for (const panel of panels) await postFlag(panel.panel_id, flagOf(panel.panel_id));
  } catch (err) {
    alert(`Couldn't save every panel: ${err.message || err}\n\nNothing was submitted - try again.`);
    return;
  }

  showLoading("Saving the review");
  const result = await finishReview(approved, generalNote);
  if (!result.ok) { hideLoading(); return; }
  showDone(approved
    ? { title: "Narration approved", facts: [["Issues", "none"]], next: "Make video in the chapter's menu." }
    : { title: "Review saved", facts: [["Issues flagged", result.flagged_count], ["Saved to", "narration_review.json"]],
        next: "Give narration_review.json and prompts/narration_review.md to the LLM, and paste its new reply into narration.json." });
}

export function wireFooter() {
  document.getElementById("btn-approve").addEventListener("click", () => {
    if (flaggedCount() > 0) return;
    submitReview(true);
  });
  document.getElementById("btn-submit").addEventListener("click", () => {
    if (flaggedCount() === 0) {
      if (!confirm("No panels are flagged. Submit anyway (equivalent to Approve)?")) return;
    }
    submitReview(false);
  });
}
