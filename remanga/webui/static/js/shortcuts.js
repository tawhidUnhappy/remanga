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

import { isMac, saveKbd, hintSaveKbd, toolDrawBtn, toolAdjustBtn } from "./dom.js";
import { api } from "./api.js";
import { state } from "./state.js";

export const ACTIONS = [
  { id: "save", label: "Save all & exit" },
  { id: "mark_full_page", label: "Mark whole page as one panel" },
  { id: "tool_draw", label: "Draw tool" },
  { id: "tool_adjust", label: "Adjust tool" },
  { id: "prev_page", label: "Previous page" },
  { id: "next_page", label: "Next page" },
  { id: "delete_mark", label: "Delete selected mark" },
  { id: "split_mark", label: "Split the mark under the mouse (way set in Options)" },
  { id: "undo", label: "Undo the last change on this page" },
  { id: "reset_view", label: "Reset zoom & position" },
];

// action id -> [combo, ...], the source matchAction() reads. Populated from
// the server; every module reads bindings through matchAction() rather than
// importing this directly, so a rebind takes effect immediately, no reload.
let bindings = {};
let defaults = {};

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
export function normalize(e) {
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

export function prettyCombo(combo) {
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

// What the Shortcuts menu (shortcuts-menu.js) reads and saves.
export const currentBindings = () => bindings;
export const defaultBindings = () => defaults;
export function adoptBindings(saved) {
  bindings = saved;
  updateHints();
}
