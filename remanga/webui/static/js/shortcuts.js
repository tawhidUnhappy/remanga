// Configurable keyboard shortcuts: loads the user's bindings from config.json
// (via GET /api/shortcuts, backed by ShortcutsConfig in remanga/config.py),
// exposes matchAction() for keyboard.js to use instead of hardcoding key
// combos, and runs the Shortcuts menu (topbar button + modal) that lets a
// user see/rebind every action and save it back to config.json so it's the
// same on the next run.
//
// Combo syntax: '+'-joined lowercase tokens, e.g. "mod+s", "arrowleft",
// "delete". "mod" means Ctrl on Windows/Linux and Cmd on macOS - it's what
// makes a saved binding still make sense on whichever OS opens it next,
// mirroring the isMac ? metaKey : ctrlKey check this file replaces.

import {
  isMac, shortcutsBtn, shortcutsOverlay, shortcutsList,
  shortcutsCloseBtn, shortcutsCancelBtn, shortcutsResetBtn, shortcutsSaveBtn,
  saveKbd, hintSaveKbd, toolDrawBtn, toolAdjustBtn,
} from "./dom.js";
import { api } from "./api.js";
import { state } from "./state.js";

export const ACTIONS = [
  { id: "save", label: "Save & continue" },
  { id: "mark_full_page", label: "Mark whole page as one panel" },
  { id: "tool_draw", label: "Draw tool" },
  { id: "tool_adjust", label: "Adjust tool" },
  { id: "prev_page", label: "Previous page" },
  { id: "next_page", label: "Next page" },
  { id: "delete_mark", label: "Delete selected mark" },
  { id: "reset_view", label: "Reset zoom & position" },
];

// action id -> [combo, ...], the source matchAction() reads. Populated from
// the server; every module reads bindings through matchAction() rather than
// importing this directly, so a rebind takes effect immediately, no reload.
let bindings = {};
let defaults = {};
let pending = null;       // working copy edited in the modal, not saved yet
let recordingId = null;   // action id currently capturing its next keydown

export async function loadShortcuts() {
  try {
    const res = await api("/api/shortcuts");
    bindings = res.shortcuts || {};
    defaults = res.defaults || {};
  } catch (e) {
    console.error("Failed to load shortcut bindings from the server - shortcuts are disabled until this loads", e);
    bindings = {};
    defaults = {};
  }
  updateHints();
}

// Keeps the few on-screen shortcut hints (toolbar D/V, the Save button, the
// bottom hint toast) truthful after a rebind - otherwise they'd keep
// showing whatever's hardcoded in index.html even once a user has moved
// that action to a different key.
function updateHints() {
  const saveCombo = (bindings.save || [])[0];
  if (saveCombo) {
    const text = prettyCombo(saveCombo);
    if (saveKbd) saveKbd.textContent = text;
    if (hintSaveKbd) hintSaveKbd.textContent = text;
  }
  const drawCombo = (bindings.tool_draw || [])[0];
  const drawKbd = toolDrawBtn?.querySelector("kbd");
  if (drawCombo && drawKbd) drawKbd.textContent = prettyCombo(drawCombo);
  const adjustCombo = (bindings.tool_adjust || [])[0];
  const adjustKbd = toolAdjustBtn?.querySelector("kbd");
  if (adjustCombo && adjustKbd) adjustKbd.textContent = prettyCombo(adjustCombo);
}

// Turns a keydown event into the same token format combos are stored in, or
// null for a bare modifier keypress (Ctrl/Cmd/Alt/Shift alone never matches
// anything - it's the combo that follows that does).
function normalize(e) {
  const key = e.key.toLowerCase();
  if (["control", "meta", "alt", "shift"].includes(key)) return null;
  const parts = [];
  if (isMac ? e.metaKey : e.ctrlKey) parts.push("mod");
  if (e.altKey) parts.push("alt");
  // Shift is only tracked as its own token for keys where it wouldn't
  // already show up in e.key - a single printable character (Shift+d ->
  // "D", Shift+1 -> "!") already encodes it once lowercased, so adding a
  // separate "shift" token there would make Shift+D normalize differently
  // from the default "d" binding instead of matching it. Non-printable
  // keys (ArrowLeft, Tab, Delete, ...) report the same e.key either way,
  // so shift has to be tracked explicitly for those.
  if (e.shiftKey && key.length > 1) parts.push("shift");
  parts.push(key);
  return parts.join("+");
}

// The action id bound to this keydown, or null. Gated on the modal being
// closed so recording a new combo there - including one, like "d", that
// would otherwise trigger an app action - never also fires that action in
// the background.
export function matchAction(e) {
  if (state.shortcutsModalOpen) return null;
  const combo = normalize(e);
  if (!combo) return null;
  for (const { id } of ACTIONS) {
    if ((bindings[id] || []).includes(combo)) return id;
  }
  return null;
}

function prettyCombo(combo) {
  return combo.split("+").map(tok => {
    if (tok === "mod") return isMac ? "⌘" : "Ctrl";
    if (tok === "shift") return isMac ? "⇧" : "Shift";
    if (tok === "alt") return isMac ? "⌥" : "Alt";
    if (tok === "arrowleft") return "←";
    if (tok === "arrowright") return "→";
    if (tok === "arrowup") return "↑";
    if (tok === "arrowdown") return "↓";
    if (tok.length === 1) return tok.toUpperCase();
    return tok[0].toUpperCase() + tok.slice(1);
  }).join(isMac ? "" : "+");
}

// The other action id already using this exact combo in the working copy, if
// any - used to refuse adding a duplicate instead of silently creating an
// ambiguous binding (matchAction() would just pick whichever action happens
// to come first in ACTIONS).
function conflictFor(actionId, combo) {
  for (const { id } of ACTIONS) {
    if (id !== actionId && (pending[id] || []).includes(combo)) return id;
  }
  return null;
}

function renderList() {
  shortcutsList.innerHTML = "";
  for (const { id, label } of ACTIONS) {
    const row = document.createElement("div");
    row.className = "shortcut-row";

    const labelEl = document.createElement("div");
    labelEl.className = "shortcut-label";
    labelEl.textContent = label;
    row.appendChild(labelEl);

    const combosEl = document.createElement("div");
    combosEl.className = "shortcut-combos";

    (pending[id] || []).forEach((combo, i) => {
      const chip = document.createElement("div");
      chip.className = "combo-chip";
      const text = document.createElement("span");
      text.textContent = prettyCombo(combo);
      chip.appendChild(text);
      const rm = document.createElement("button");
      rm.textContent = "✕";
      rm.title = "Remove this binding";
      rm.addEventListener("click", () => {
        pending[id] = pending[id].filter((_, j) => j !== i);
        renderList();
      });
      chip.appendChild(rm);
      combosEl.appendChild(chip);
    });

    const addBtn = document.createElement("button");
    addBtn.className = "combo-add" + (recordingId === id ? " recording" : "");
    addBtn.textContent = recordingId === id ? "Press a key… (Esc to cancel)" : "+";
    addBtn.title = "Add a key binding";
    addBtn.addEventListener("click", () => {
      recordingId = recordingId === id ? null : id;
      renderList();
    });
    combosEl.appendChild(addBtn);

    row.appendChild(combosEl);
    shortcutsList.appendChild(row);
  }
}

// While a row is "recording", the next keydown anywhere becomes its new
// binding instead of doing anything else - capture-phase + stopPropagation
// so it doesn't also reach keyboard.js or the browser (e.g. arrow-key
// scrolling, or Backspace navigating back).
document.addEventListener("keydown", (e) => {
  if (!recordingId) return;
  e.preventDefault();
  e.stopPropagation();

  if (e.key === "Escape") {
    recordingId = null;
    renderList();
    return;
  }
  const combo = normalize(e);
  if (!combo) return; // a bare modifier - keep waiting for the real key

  const actionId = recordingId;
  recordingId = null;
  const conflict = conflictFor(actionId, combo);
  if (conflict) {
    renderList();
    const row = [...shortcutsList.children][ACTIONS.findIndex(a => a.id === actionId)];
    const msg = document.createElement("div");
    msg.className = "shortcut-conflict";
    msg.textContent = `${prettyCombo(combo)} is already used by "${ACTIONS.find(a => a.id === conflict).label}"`;
    row.appendChild(msg);
    return;
  }
  if (!(pending[actionId] || []).includes(combo)) {
    pending[actionId] = [...(pending[actionId] || []), combo];
  }
  renderList();
}, { capture: true });

// Escape closes the modal itself when nothing is being recorded (the
// listener above already handles Escape-cancels-recording and returns
// before this would run for that case, since recordingId is checked there
// first and this one only cares about the modal-open, not-recording case).
document.addEventListener("keydown", (e) => {
  if (state.shortcutsModalOpen && !recordingId && e.key === "Escape") closeModal();
});

function openModal() {
  pending = structuredClone(bindings);
  recordingId = null;
  state.shortcutsModalOpen = true;
  shortcutsOverlay.classList.add("visible");
  renderList();
}

function closeModal() {
  state.shortcutsModalOpen = false;
  recordingId = null;
  pending = null;
  shortcutsOverlay.classList.remove("visible");
}

shortcutsBtn.addEventListener("click", openModal);
shortcutsCloseBtn.addEventListener("click", closeModal);
shortcutsCancelBtn.addEventListener("click", closeModal);
shortcutsResetBtn.addEventListener("click", () => {
  pending = structuredClone(defaults);
  recordingId = null;
  renderList();
});
shortcutsSaveBtn.addEventListener("click", async () => {
  try {
    const res = await api("/api/shortcuts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pending),
    });
    bindings = res.shortcuts;
    updateHints();
    closeModal();
  } catch (e) {
    alert("Failed to save shortcuts: " + e.message);
  }
});
shortcutsOverlay.addEventListener("mousedown", (e) => {
  if (e.target === shortcutsOverlay) closeModal();
});
