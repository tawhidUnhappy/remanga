// The Shortcuts menu (topbar button + modal): every action with its key
// combos, adding one by pressing it, removing one, and saving the lot to
// config.json. What the combos DO is keyboard.js; matching them, shortcuts.js.

import {
  shortcutsBtn, shortcutsOverlay, shortcutsList,
  shortcutsCloseBtn, shortcutsCancelBtn, shortcutsResetBtn, shortcutsSaveBtn,
} from "./dom.js";
import { api } from "./api.js";
import { state } from "./state.js";
import { ACTIONS, adoptBindings, currentBindings, defaultBindings, normalize, prettyCombo } from "./shortcuts.js";

let pending = null;       // working copy edited in the modal, not saved yet
let recordingId = null;   // action id currently capturing its next keydown

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
  pending = structuredClone(currentBindings());
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
  pending = structuredClone(defaultBindings());
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
    adoptBindings(res.shortcuts);
    closeModal();
  } catch (e) {
    alert("Failed to save shortcuts: " + e.message);
  }
});
shortcutsOverlay.addEventListener("mousedown", (e) => {
  if (e.target === shortcutsOverlay) closeModal();
});
