// The three buttons, over whatever scope is chosen (assist-scope.js).
//
// Detect fills in the pages nobody has marked; a page that has been edited is
// refused by the server (MarkerState.apply_detected). Reorder only renumbers,
// and happens immediately. Remark is the one that REPLACES marks, hand-drawn
// ones included, so it is the one that asks first - in numbers, from a dry run.

import { assistBtn, assistStatus, remarkBtn, reorderBtn } from "./dom.js";
import { postJson } from "./api.js";
import { describeScope, scopeBody } from "./assist-scope.js";
import { notice, pollDetectStatus } from "./assist-status.js";
import { flushSave } from "./marks.js";
import { refreshOutline } from "./outline.js";
import { reloadMarks } from "./reload-marks.js";

export async function runDetect() {
  const body = scopeBody();
  assistBtn.disabled = true;
  // Whatever is on screen reaches the server first, so a page edited a second
  // ago counts as edited when MAGI gets to it.
  await flushSave(true);
  assistStatus.textContent = `Detecting ${describeScope(body)}…`;
  try {
    const res = await postJson("/api/detect", body);
    if (!res.accepted.length) notice("Nothing to detect - already done this session");
  } catch (e) {
    notice("Couldn't start: " + e.message);
  }
  // Straight away, not at the next tick: the button stays disabled and the
  // bar says what's running until the server says otherwise.
  pollDetectStatus();
}

// Reorder is immediate (MarkerSession.reorder) - the new order is already in
// place when the response arrives, so the tab takes it right then instead of
// waiting for a poll, and it never queues behind a detection pass.
export async function runReorder() {
  const body = scopeBody();
  reorderBtn.disabled = true;
  await flushSave(true);
  try {
    const res = await postJson("/api/reorder", body);
    const changed = res.changed || {};
    const pages = Object.values(changed).reduce((n, count) => n + count, 0);
    const chapters = Object.keys(changed).length;
    await reloadMarks();
    refreshOutline();
    const where = describeScope(body);
    notice(pages
      ? `Reordered ${pages} page(s)${chapters > 1 ? ` across ${chapters} chapters` : ""}`
      : `${where[0].toUpperCase()}${where.slice(1)} is already in reading order`);
  } catch (e) {
    notice("Couldn't reorder: " + e.message);
  } finally {
    reorderBtn.disabled = false;
  }
}

export async function runRemark() {
  const body = scopeBody();
  remarkBtn.disabled = true;
  await flushSave(true);
  try {
    const plan = await postJson("/api/remark", { ...body, dry_run: true });
    const where = describeScope(body);
    const lines = [];
    if (plan.marked) {
      lines.push(`• ${plan.marked} page(s) have marks now and get new ones` +
        (plan.hand_made ? ` - ${plan.hand_made} of them with marks you drew or edited.` : "."));
    }
    if (plan.emptied) lines.push(`• ${plan.emptied} page(s) you emptied on purpose get marked again.`);
    if (plan.narrated.length) {
      const list = plan.narrated.length > 8
        ? `${plan.narrated.slice(0, 8).join(", ")} and ${plan.narrated.length - 8} more`
        : plan.narrated.join(", ");
      lines.push(`• Already narrated: ch ${list}. New marks mean new panel numbers, and the narration won't match them.`);
    }
    if (lines.length) {
      const go = confirm(
        `Remark ${where} with AI?\n\n` +
        `MAGI marks ${plan.pages} page(s) again and replaces what's on them:\n` +
        `${lines.join("\n")}\n\nThis can't be undone.`);
      if (!go) {
        notice("Remark cancelled - nothing changed");
        return;
      }
    }
    const res = await postJson("/api/remark", body);
    if (!res.accepted.length) notice("That's already waiting to be remarked");
  } catch (e) {
    notice("Couldn't remark: " + e.message);
  } finally {
    // The button comes back when the poll says the worker is free.
    pollDetectStatus();
  }
}
