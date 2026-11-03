// Every panel's narration text, for the whole chapter.
//
// The map holds every panel whether its card is mounted or not: the virtual
// list (virtual-list.js) drops cards out of the DOM as you scroll, and what
// you typed must never go with them. Changing a panel's text here is also how
// everything that DRAWS it - the nav dot, the counter - hears about it.

export const panels = [];
export let chapter = null;

const texts = new Map();
const listeners = [];

export function loadChapter(data) {
  panels.length = 0;
  panels.push(...data.panels);
  chapter = data.chapter;
  for (const panel of panels) texts.set(panel.panel_id, panel.text || "");
}

export function textOf(panelId) {
  return texts.get(panelId) || "";
}

export function setText(panelId, value) {
  texts.set(panelId, value);
  for (const listener of listeners) listener(panelId, value.trim().length > 0);
}

export function onTextChanged(listener) {
  listeners.push(listener);
}

export function writtenCount() {
  return [...texts.values()].filter((text) => text.trim()).length;
}
