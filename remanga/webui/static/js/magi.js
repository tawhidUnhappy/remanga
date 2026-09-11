// The action bar: choosing which pages, running Detect / Reorder / Recrop on
// them, the saved switches, and reporting what the session's detection and
// crop workers are doing.
//
// One scope control drives all three buttons, because "chapters 4 to 9" means
// the same pages whether MAGI is finding panels in them, they are being put
// into reading order, or their panels are being cut again. None of them can
// undo anyone's drawing: Detect is refused on a page that has been edited
// (MarkerState.apply_detected), Reorder only renumbers, and Recrop cuts images
// from the marks without changing a single one.

import {
  assistBtn, reorderBtn, recropBtn, assistProgressBar, assistStatus, scopeSelect,
  assistRange, rangeFrom, rangeTo, autoAllToggle, autoSaveToggle, autoOrderToggle,
  cropRow, cropProgressBar, cropStatus, optSummary, actionsOptions,
} from "./dom.js";
import { state, currentFilename } from "./state.js";
import { api } from "./api.js";
import { render } from "./render.js";
import { refreshOutline } from "./outline.js";
import { flushSave } from "./marks.js";

const MAGI_OFF = "MAGI is off in config.json - Reorder and Recrop still work";
const OPTIONS_OPEN_KEY = "remanga.marker.optionsOpen";

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

// Recrop can't do "This page" - the cropper works a chapter at a time and
// wipes its panels first - so on that scope the button says why instead of
// doing something wider than was asked.
let cropBusy = false;
function syncRecropButton() {
  const pageScope = scopeSelect.value === "page";
  recropBtn.disabled = cropBusy || pageScope;
  recropBtn.title = pageScope
    ? "Recrop works on whole chapters - pick This chapter or wider"
    : "Recrop - save the marks and cut fresh panel images from them. Whole chapters only.";
}

function syncScopeUi() {
  assistRange.hidden = scopeSelect.value !== "range";
  syncRecropButton();
}

// What's switched on, readable with Options folded away - so folding them
// never hides that auto-order is quietly re-sorting every page.
function syncOptionsSummary() {
  const on = [];
  if (autoAllToggle.checked) on.push("keep marking");
  if (autoOrderToggle.checked) on.push("auto-order");
  if (!autoSaveToggle.checked) on.push("auto-save off");
  optSummary.textContent = on.length ? `· ${on.join(" · ")}` : "";
}

// Called whenever a chapter is applied, so the bar describes the session it
// is actually looking at (see chapter-nav.js).
export function syncAssistCard() {
  if (!state.chapter) return;
  scopeSelect.value = state.chapter.detect_scope || "chapter";
  autoAllToggle.checked = !!state.chapter.auto_all;
  autoSaveToggle.checked = state.chapter.auto_save !== false;
  state.autoOrder = !!state.chapter.auto_order;
  autoOrderToggle.checked = state.autoOrder;
  assistBtn.disabled = !state.magiEnabled;
  fillRangeSelects();
  syncScopeUi();
  syncOptionsSummary();
}

function scopeBody() {
  const scope = scopeSelect.value;
  const body = { scope };
  if (scope === "page") body.filename = currentFilename();
  if (scope === "range") { body.from = rangeFrom.value; body.to = rangeTo.value; }
  return body;
}

function describeScope(body) {
  if (body.scope === "page") return "this page";
  if (body.scope === "range") return `ch ${body.from}–${body.to}`;
  if (body.scope === "all") return "all chapters";
  return "this chapter";
}

// A one-off message that outranks the idle summary for a few seconds - the
// answer to "I pressed it and nothing happened", which the next poll would
// otherwise overwrite before anyone had read it.
function notice(text) {
  state.opNotice = { text, until: Date.now() + 4000 };
  assistStatus.textContent = text;
}

async function reloadMarks() {
  const { reloadChapterMarks } = await import("./chapter-nav.js");
  await reloadChapterMarks();
}

async function postJson(path, body) {
  return api(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

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

// Recrop asks the server what it would do first (dry_run), and only then does
// it. The question that matters is narration: cutting a narrated chapter's
// panels again changes nothing if its marks haven't changed, but if a mark was
// moved, added, removed or renumbered since it was narrated, its narration now
// names panels that don't exist and TTS/render will refuse it. That is worth
// one confirm, asked before - not a warning discovered after.
export async function runRecrop() {
  const body = scopeBody();
  if (body.scope === "page") return;
  recropBtn.disabled = true;
  await flushSave(true);
  try {
    const plan = await postJson("/api/recrop", { ...body, dry_run: true });
    if (!plan.chapters.length) {
      notice(`Nothing to recrop - ${describeScope(body)} has no marks yet`);
      return;
    }
    if (plan.narrated.length) {
      const list = plan.narrated.length > 8
        ? `${plan.narrated.slice(0, 8).join(", ")} and ${plan.narrated.length - 8} more`
        : plan.narrated.join(", ");
      const go = confirm(
        `${plan.narrated.length} of the ${plan.chapters.length} chapter(s) to recrop already have narration ` +
        `(ch ${list}).\n\n` +
        "Recropping replaces their panel images. If a chapter's marks changed since it was narrated - " +
        "a panel moved, added, removed or reordered - its narration will no longer match, and TTS and " +
        "render will stop on it until the narration is updated.\n\n" +
        `Recrop ${plan.chapters.length} chapter(s)?`);
      if (!go) {
        notice("Recrop cancelled - nothing changed");
        return;
      }
    }
    await postJson("/api/recrop", body);
  } catch (e) {
    notice("Couldn't recrop: " + e.message);
  } finally {
    pollDetectStatus();
  }
}

async function saveSetting(values) {
  try {
    const res = await postJson("/api/settings", values);
    // The payload the tab is holding is what syncAssistCard reads on the next
    // chapter change, so it has to learn what was just saved too.
    if (state.chapter) Object.assign(state.chapter, {
      auto_all: res.auto_all, auto_save: res.auto_save, auto_order: res.auto_order,
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

function renderCropStatus(status) {
  cropBusy = !!status.crop_active || (status.crop_queued || []).length > 0;
  syncRecropButton();
  const result = cropBusy ? status.crop_result : status.crop_last_run;
  if (!cropBusy && !result) {
    cropRow.hidden = true;
    return;
  }
  cropRow.hidden = false;

  if (cropBusy) {
    const total = status.crop_run_total || 0;
    cropProgressBar.style.width = total ? Math.round((status.crop_run_done / total) * 100) + "%" : "0%";
    cropStatus.className = "assist-status";
    cropStatus.title = "";
    // Right after the button, the chapter is still queued rather than active.
    const chapter = status.crop_active || (status.crop_queued || [])[0];
    cropStatus.textContent =
      `Recropping ch ${chapter}${total > 1 ? ` · ${Math.min(status.crop_run_done + 1, total)} of ${total}` : ""}`;
    return;
  }

  // The finished run stays on screen until the next Recrop: a warning that
  // narration no longer matches is the one thing here nobody should miss.
  cropProgressBar.style.width = "100%";
  const done = result.chapters || [];
  const parts = [];
  if (done.length) {
    parts.push(`Recropped ${done.length === 1 ? "ch " + done[0] : done.length + " chapters"} · ${result.panels} panels`);
  } else {
    parts.push("Nothing was recropped");
  }
  if ((result.failed || []).length) parts.push(`failed: ch ${result.failed.map(f => f.chapter).join(", ")}`);
  if ((result.mismatched || []).length) {
    parts.push(`narration no longer matches: ch ${result.mismatched.map(m => m.chapter).join(", ")}`);
  }
  const warn = (result.failed || []).length || (result.mismatched || []).length;
  cropStatus.className = "assist-status" + (warn ? " warn" : "");
  cropStatus.textContent = parts.join(" · ");
  cropStatus.title = [
    ...(result.failed || []).map(f => `ch ${f.chapter}: ${f.error}`),
    ...(result.mismatched || []).map(m => `ch ${m.chapter}: ${m.issue}`),
  ].join("\n");
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

  renderCropStatus(status);

  const queued = status.queued || [];
  const busy = !!status.active || queued.length > 0;
  assistBtn.disabled = busy || !state.magiEnabled;

  // Everything below reads the RUN (run_done / run_total, last_run), never the
  // chapter on screen. Reading the current chapter's own counters is what left
  // "Detecting ch 4 · 2/3 pages" on the bar forever once a range finished:
  // the chapter on screen had nothing to report, so nothing replaced the text.
  if (busy) {
    const within = status.active_total ? status.active_done / status.active_total : 0;
    const overall = status.run_total ? Math.min(1, (status.run_done + within) / status.run_total) : 0;
    assistProgressBar.style.width = Math.round(overall * 100) + "%";
    let text = status.active ? `Detecting ch ${status.active}` : "Starting…";
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
    assistStatus.textContent =
      `Done · detected ${chapters.length === 1 ? "ch " + chapters[0] : chapters.length + " chapters"}`;
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

// Options stays however it was left, per browser - it's a fold, not a setting
// anyone else needs to share, and it must work with no storage at all.
try { actionsOptions.open = localStorage.getItem(OPTIONS_OPEN_KEY) === "1"; } catch {}
actionsOptions.addEventListener("toggle", () => {
  try { localStorage.setItem(OPTIONS_OPEN_KEY, actionsOptions.open ? "1" : "0"); } catch {}
});

assistBtn.addEventListener("click", runDetect);
reorderBtn.addEventListener("click", runReorder);
recropBtn.addEventListener("click", runRecrop);
scopeSelect.addEventListener("change", () => { syncScopeUi(); saveSetting({ scope: scopeSelect.value }); });
autoAllToggle.addEventListener("change", () => saveSetting({ auto_all: autoAllToggle.checked }));
autoSaveToggle.addEventListener("change", () => saveSetting({ auto_save: autoSaveToggle.checked }));
autoOrderToggle.addEventListener("change", () => saveSetting({ auto_order: autoOrderToggle.checked }));
