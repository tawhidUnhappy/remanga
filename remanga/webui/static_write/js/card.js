// One panel's card: its image, the field you type the narration into, and
// what that field's state looks like - written/empty pill, dimmed card, and
// the flag an autosave raises when it couldn't reach the server.

import { flushSave, scheduleSave } from "./autosave.js";
import { escapeHtml } from "./dom.js";
import { openLightbox } from "./lightbox.js";
import { wireOcr } from "./ocr.js";
import { setText, textOf } from "./state.js";

export function buildCard(panel) {
  const panelId = panel.panel_id;
  const text = textOf(panelId);
  const card = document.createElement("div");
  card.className = "panel-card" + (text.trim() ? "" : " empty");
  card.dataset.panelId = panelId;

  const thumbHtml = panel.image
    ? `<img src="/api/panels/${encodeURIComponent(panel.image)}" loading="lazy" alt="${panelId}" data-action="zoom">`
    : `<div class="missing">No image file found for this panel.</div>`;

  card.innerHTML = `
    <div class="panel-thumb">${thumbHtml}</div>
    <div class="panel-body">
      <div class="panel-id-row">
        <span class="panel-id">${panelId}</span>
        <span class="status-pill ${text.trim() ? "is-written" : "is-empty"}">${text.trim() ? "✓ written" : "○ empty"}</span>
      </div>
      <label class="text-label" for="text-${panelId}">Narration</label>
      <textarea id="text-${panelId}" placeholder="Type the narration line for this panel - leave empty for a silent beat.">${escapeHtml(text)}</textarea>
      <div class="ocr-row">
        <button type="button" class="ocr-btn" data-action="ocr">🔎 OCR this panel</button>
        <span class="ocr-status"></span>
      </div>
      <div class="ocr-result" hidden></div>
    </div>
  `;

  const textField = card.querySelector("textarea");
  const saved = (ok) => flagSaveState(card, ok);
  const take = (value) => {
    setText(panelId, value);
    paint(card, value);
    scheduleSave(panelId, saved);
  };

  // Written into the field as well - this is what OCR uses to fill an empty
  // panel or to replace/append to what is there.
  const applyText = (value) => {
    textField.value = value;
    take(value);
  };

  textField.addEventListener("input", (e) => take(e.target.value));
  // A debounce timer only fires after typing pauses - a field left mid-word
  // needs its own immediate save.
  textField.addEventListener("blur", () => flushSave(panelId, saved));

  const img = card.querySelector('img[data-action="zoom"]');
  if (img) img.addEventListener("click", () => openLightbox(img.src, panelId));
  wireOcr(card, panelId, applyText);

  return card;
}

function paint(card, value) {
  const written = value.trim().length > 0;
  card.classList.toggle("empty", !written);
  const pill = card.querySelector(".status-pill");
  pill.className = "status-pill " + (written ? "is-written" : "is-empty");
  pill.textContent = written ? "✓ written" : "○ empty";
}

function flagSaveState(card, ok) {
  const pill = card.querySelector(".status-pill");
  if (pill) pill.classList.toggle("save-failed", !ok);
}
