// MAGI v3 panel-detection assist: choosing how much to detect, starting it,
// and reporting what the session's detection queue is doing.
//
// The scope control is the whole point of this card now. "Re-run on all
// pages" could only ever mean the chapter in front of you, so a project
// interrupted at chapter 9 meant opening chapter 10, waiting, opening
// chapter 11, waiting - or redetecting a manga that was already three
// quarters done. A from/to says that in one go, and "keep marking every
// chapter" says it once and for every project after this one.
//
// None of it can undo anyone's work: the server refuses to apply a
// detection to a page that has been edited (MarkerState.apply_detected), so
// the widest scope here is still safe on a half-marked project.

import {
  assistBtn, assistProgressBar, assistStatus, scopeSelect, assistRange,
  rangeFrom, rangeTo, autoAllToggle, autoSaveToggle,
} from "./dom.js";
import { state, currentFilename } from "./state.js";
import { api } from "./api.js";
import { render } from "./render.js";
import { refreshOutline } from "./outline.js";

function fillRangeSelects() {
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

function syncScopeUi() {
  assistRange.hidden = scopeSelect.value !== "range";
}

// Called whenever a chapter is applied, so the card describes the session it
// is actually looking at (see chapter-nav.js).
export function syncAssistCard() {
  if (!state.chapter) return;
  scopeSelect.value = state.chapter.detect_scope || "chapter";
  autoAllToggle.checked = !!state.chapter.auto_all;
  autoSaveToggle.checked = state.chapter.auto_save !== false;
  fillRangeSelects();
  syncScopeUi();
}

export async function runDetect() {
  const scope = scopeSelect.value;
  const body = { scope };
  if (scope === "page") body.filename = currentFilename();
  if (scope === "range") { body.from = rangeFrom.value; body.to = rangeTo.value; }

  assistBtn.disabled = true;
  try {
    const res = await api("/api/detect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    // Nothing accepted is a real answer, not a failure: every chapter asked
    // for has already been detected this session, or every page in it has
    // been edited. Saying so beats a progress bar that never moves.
    if (!res.accepted.length) {
      assistStatus.textContent = "Nothing to detect - already marked";
    }
  } catch (e) {
    assistStatus.textContent = "Couldn't start: " + e.message;
  } finally {
    assistBtn.disabled = false;
  }
}

async function saveSetting(values) {
  try {
    const res = await api("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    // The payload the tab is holding is what syncAssistCard reads on the next
    // chapter change, so it has to learn what was just saved too.
    if (state.chapter) Object.assign(state.chapter, {
      auto_all: res.auto_all, auto_save: res.auto_save,
      detect_scope: values.scope ?? state.chapter.detect_scope,
    });
  } catch (e) {
    assistStatus.textContent = "Couldn't save that setting: " + e.message;
  }
}

// The chapter the worker was on at the last poll. When it changes, a
// chapter has just finished - which is the moment the outline's counts for
// it stopped being right, and the only moment worth refetching them.
let lastActive = null;

export async function pollDetectStatus() {
  if (!state.magiEnabled || state.readOnly) return;
  let status;
  try { status = await api("/api/detect/status"); } catch { return; }

  const queued = status.queued || [];
  if (status.active !== lastActive) {
    lastActive = status.active;
    refreshOutline();
  }
  assistBtn.disabled = !!status.active;
  if (status.active) {
    const pct = status.active_total ? Math.round((status.active_done / status.active_total) * 100) : 0;
    assistProgressBar.style.width = pct + "%";
    assistStatus.textContent =
      `Detecting ch ${status.active} · ${status.active_done}/${status.active_total} pages`
      + (queued.length ? ` · ${queued.length} chapter(s) queued` : "");
  } else if (status.error) {
    assistStatus.textContent = "Error: " + status.error;
  } else if (queued.length) {
    assistStatus.textContent = `${queued.length} chapter(s) queued`;
  } else if (status.total) {
    assistProgressBar.style.width = "100%";
    assistStatus.textContent = `Done · ${status.total} page(s) processed`;
  }

  // Unsaved chapters are worth stating continuously, not only at the end -
  // with auto-save off, "3 chapters unsaved" sitting in front of you is the
  // difference between a deliberate choice and a nasty surprise on the way
  // out.
  if (!status.auto_save && (status.unsaved || []).length) {
    assistStatus.textContent += ` · ${status.unsaved.length} unsaved`;
  }

  // Page filenames repeat across chapters (every chapter has a page_001), so
  // a status response that was in flight while the tab switched chapters
  // would write the previous chapter's marks straight into this one's cache
  // under matching names. The response says which chapter it describes;
  // anything but the one on screen is dropped.
  if (status.chapter !== state.chapter.chapter) return;

  let currentPageChanged = false;
  for (const [filename, serverMarks] of Object.entries(status.marks || {})) {
    if (state.touchedPages.has(filename)) continue;
    state.pageMarksCache[filename] = serverMarks;
    if (state.chapter.pages[state.pageIndex].filename === filename) currentPageChanged = true;
  }
  if (currentPageChanged) {
    state.marks = state.pageMarksCache[currentFilename()];
    render();
  }
}

assistBtn.addEventListener("click", runDetect);
scopeSelect.addEventListener("change", () => { syncScopeUi(); saveSetting({ scope: scopeSelect.value }); });
autoAllToggle.addEventListener("change", () => saveSetting({ auto_all: autoAllToggle.checked }));
autoSaveToggle.addEventListener("change", () => saveSetting({ auto_save: autoSaveToggle.checked }));
