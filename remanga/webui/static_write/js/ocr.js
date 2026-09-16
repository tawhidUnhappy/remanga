// "OCR this panel" - runs DeepSeek-OCR-2 (see remanga/ocr/engine.py; GPU
// preferred, falls back to CPU) over this panel's cropped image and offers
// what it reads as a starting draft, never silently overwriting anything
// already typed:
//   - empty field: filled in directly, nothing to lose.
//   - field with text in it: what was read appears below with
//     Replace/Append/Dismiss, instead of touching the textarea on its own.
// The worker loads the model on its first call in this session (and downloads
// the weights first if they aren't on disk yet - see ModelManager); every
// call after that reuses the loaded model and is fast.

import { requestOcr } from "./api.js";
import { escapeHtml } from "./dom.js";

export function wireOcr(card, panelId, applyText) {
  card.querySelector('[data-action="ocr"]').addEventListener("click", () => runOcr(card, panelId, applyText));
}

async function runOcr(card, panelId, applyText) {
  const btn = card.querySelector('[data-action="ocr"]');
  const statusEl = card.querySelector(".ocr-status");
  const resultEl = card.querySelector(".ocr-result");
  const textField = card.querySelector("textarea");

  btn.disabled = true;
  statusEl.textContent = "Reading panel… (first run this session loads the model, can take a bit)";
  statusEl.className = "ocr-status";
  resultEl.hidden = true;

  try {
    const result = await requestOcr(panelId);
    const recognized = (result.text || "").trim();
    statusEl.textContent = result.device === "cuda" ? "✓ read on GPU" : "✓ read on CPU (no GPU available)";
    statusEl.className = "ocr-status ocr-ok";

    if (!recognized) {
      statusEl.textContent += " - no text found on this panel.";
      return;
    }
    if (!textField.value.trim()) {
      // Nothing typed yet - fill it in exactly as if it had been typed, so it
      // autosaves through the normal path.
      applyText(recognized);
      return;
    }
    offerChoices(resultEl, textField, recognized, applyText);
  } catch (err) {
    statusEl.textContent = `OCR failed: ${err.message || err}`;
    statusEl.className = "ocr-status ocr-failed";
    console.error(`OCR failed for panel ${panelId}:`, err);
  } finally {
    btn.disabled = false;
  }
}

// Something is already written here - never overwrite it without asking.
function offerChoices(resultEl, textField, recognized, applyText) {
  resultEl.hidden = false;
  resultEl.innerHTML = `
      <div class="ocr-result-text">${escapeHtml(recognized)}</div>
      <div class="ocr-result-actions">
        <button type="button" class="ocr-mini" data-act="replace">Replace</button>
        <button type="button" class="ocr-mini" data-act="append">Append</button>
        <button type="button" class="ocr-mini" data-act="dismiss">Dismiss</button>
      </div>
    `;
  resultEl.querySelector('[data-act="replace"]').addEventListener("click", () => {
    applyText(recognized);
    resultEl.hidden = true;
  });
  resultEl.querySelector('[data-act="append"]').addEventListener("click", () => {
    applyText(`${textField.value.trim()} ${recognized}`.trim());
    resultEl.hidden = true;
  });
  resultEl.querySelector('[data-act="dismiss"]').addEventListener("click", () => {
    resultEl.hidden = true;
  });
}
