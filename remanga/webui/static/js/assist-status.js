// What the session's detection worker is doing, as one line on the action
// bar - plus the short-lived notice a button press leaves there.

import { assistBtn, assistProgressBar, assistStatus, remarkBtn } from "./dom.js";
import { api } from "./api.js";
import { currentFilename, state } from "./state.js";
import { refreshOutline } from "./outline.js";
import { reloadMarks } from "./reload-marks.js";
import { render } from "./render.js";

export const MAGI_OFF = "MAGI is off in config.json - Reorder still works";

// A one-off message that outranks the idle summary for a few seconds - the
// answer to "I pressed it and nothing happened", which the next poll would
// otherwise overwrite before anyone had read it.
export function notice(text) {
  state.opNotice = { text, until: Date.now() + 4000 };
  assistStatus.textContent = text;
}

// The chapter the worker was on at the last poll. When it changes, a chapter
// has just finished - which is the moment the outline's counts for it stopped
// being right, and the only moment worth refetching them.
let lastActive = null;

export async function pollDetectStatus() {
  if (state.readOnly || !state.chapter) return;
  let status;
  try { status = await api("/api/detect/status"); } catch { return; }

  if (status.active !== lastActive) {
    lastActive = status.active;
    refreshOutline();
  }

  const queued = status.queued || [];
  const busy = !!status.active || queued.length > 0;
  assistBtn.disabled = remarkBtn.disabled = busy || !state.magiEnabled;

  // Everything below reads the RUN (run_done / run_total, last_run), never the
  // chapter on screen. Reading the current chapter's own counters is what left
  // "Detecting ch 4 · 2/3 pages" on the bar forever once a range finished:
  // the chapter on screen had nothing to report, so nothing replaced the text.
  if (busy) {
    const within = status.active_total ? status.active_done / status.active_total : 0;
    const overall = status.run_total ? Math.min(1, (status.run_done + within) / status.run_total) : 0;
    assistProgressBar.style.width = Math.round(overall * 100) + "%";
    const verb = status.active_kind === "remark" ? "Remarking" : "Detecting";
    let text = status.active ? `${verb} ch ${status.active}` : "Starting…";
    if (status.active && status.active_total) text += ` · page ${status.active_done}/${status.active_total}`;
    if (status.run_total > 1) text += ` · ${Math.min(status.run_done + 1, status.run_total)} of ${status.run_total}`;
    assistStatus.textContent = text;
  } else if (state.opNotice && Date.now() < state.opNotice.until) {
    assistStatus.textContent = state.opNotice.text;
  } else if (status.error) {
    assistStatus.textContent = "Error: " + status.error;
  } else if (status.last_run && status.last_run.jobs) {
    assistProgressBar.style.width = "100%";
    const chapters = status.last_run.chapters || [];
    const kinds = status.last_run.kinds || [];
    const verb = !kinds.includes("remark") ? "detected"
      : kinds.includes("detect") ? "detected & remarked" : "remarked";
    assistStatus.textContent =
      `Done · ${verb} ${chapters.length === 1 ? "ch " + chapters[0] : chapters.length + " chapters"}`;
  } else {
    assistProgressBar.style.width = "0%";
    assistStatus.textContent = state.magiEnabled ? "Idle" : MAGI_OFF;
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

  // A reorder rewrote this chapter on the server (the background one that
  // turning auto-order on starts, say). The tab's copy is now the old order,
  // and would be autosaved straight back - so take the server's instead.
  if (typeof status.revision === "number" && status.revision !== state.chapterRevision) {
    await reloadMarks();
    return;
  }

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
