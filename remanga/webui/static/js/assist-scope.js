// Which pages the action bar acts on: the scope control, and what it turns
// into on the wire.
//
// One scope drives Detect, Remark and Reorder, because "chapters 4 to 9"
// means the same pages whether MAGI is filling in the unmarked ones, marking
// every one of them again, or they are being put into reading order.

import { assistRange, rangeFrom, rangeTo, scopeSelect } from "./dom.js";
import { currentFilename, state } from "./state.js";

export function fillRangeSelects() {
  const chapters = (state.chapter && state.chapter.chapters) || [];
  for (const select of [rangeFrom, rangeTo]) {
    const previous = select.value;
    select.replaceChildren();
    for (const chapter of chapters) {
      const option = document.createElement("option");
      option.value = chapter;
      option.textContent = `Ch ${chapter}`;
      select.appendChild(option);
    }
    if (chapters.includes(previous)) select.value = previous;
  }
  // Opens on "from here to the end", which is the answer whenever the reason
  // you came to this control is that something stopped part-way.
  if (!chapters.includes(rangeFrom.value)) rangeFrom.value = state.chapter.chapter;
  if (!chapters.includes(rangeTo.value)) rangeTo.value = chapters[chapters.length - 1] || "";
}

export function syncScopeUi() {
  assistRange.hidden = scopeSelect.value !== "range";
}

export function scopeBody() {
  const scope = scopeSelect.value;
  const body = { scope };
  if (scope === "page") body.filename = currentFilename();
  if (scope === "range") { body.from = rangeFrom.value; body.to = rangeTo.value; }
  return body;
}

export function describeScope(body) {
  if (body.scope === "page") return "this page";
  if (body.scope === "range") return `ch ${body.from}–${body.to}`;
  if (body.scope === "all") return "all chapters";
  return "this chapter";
}
