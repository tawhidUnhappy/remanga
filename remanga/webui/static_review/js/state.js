// The chapter under review, and what has been flagged on it.
//
// A panel is flagged if and only if its review field has text in it - there
// is no separate toggle to keep in sync, so the two can never disagree.

export const panels = [];
export let chapter = null;
export let roundNumber = null;

const flags = new Map(); // panel_id -> { issue, tag }
const listeners = [];

export function loadChapter(data) {
  panels.length = 0;
  panels.push(...data.panels);
  chapter = data.chapter;
  roundNumber = data.round;
  flags.clear();
  // A flag carried over from the previous round, for a panel whose text the
  // LLM did not change (see ReviewerState._preload_previous_round).
  for (const panel of panels) {
    if (panel.flag) flags.set(panel.panel_id, { issue: panel.flag.issue || "", tag: panel.flag.tag || "" });
  }
}

export function flagOf(panelId) {
  return flags.get(panelId) || { issue: "", tag: "" };
}

export function isFlagged(panelId) {
  return flags.has(panelId);
}

export function flaggedCount() {
  return flags.size;
}

export function setFlagField(panelId, field, value) {
  const current = { ...flagOf(panelId), [field]: value };
  if (current.issue.trim()) flags.set(panelId, current);
  else flags.delete(panelId);

  for (const listener of listeners) listener(panelId, flags.has(panelId));
  return flags.has(panelId);
}

export function onFlagsChanged(listener) {
  listeners.push(listener);
}
