// One panel's card: the cropped image, the narration line written for it,
// and an always-visible review field.
//
// Leaving the review field empty means "this panel is fine"; typing anything
// in it flags the panel, with no separate click first.

import { escapeHtml } from "/shared/js/dom.js";
import { openLightbox } from "/shared/js/lightbox.js";
import { flagOf, isFlagged, setFlagField } from "./state.js";
import { tagOptionsHtml } from "./tags.js";

export function buildCard(panel) {
  const panelId = panel.panel_id;
  const card = document.createElement("div");
  card.className = "panel-card" + (isFlagged(panelId) ? " flagged" : "");
  card.dataset.panelId = panelId;

  // Missing usually means narration.json's panel_id doesn't exactly match a
  // filename in panels/ (e.g. an LLM typo dropping a zero-pad digit) - say so
  // explicitly rather than leaving a bare "not found" that reads like a UI bug.
  const thumbHtml = panel.image
    ? `<img src="/api/panels/${encodeURIComponent(panel.image)}" loading="lazy" alt="${panelId}" data-action="zoom">`
    : `<div class="missing">No file named <code>${panelId}.png/.jpg/.jpeg/.webp</code> in this chapter's <code>panels/</code> folder.<br>Check narration.json's panel_id for this entry against the actual cropped filename - a mismatch (e.g. missing zero-padding) is the usual cause.</div>`;

  const textHtml = panel.text
    ? escapeHtml(panel.text)
    : `<span class="silent">(silent beat — empty text)</span>`;

  const current = flagOf(panelId);

  card.innerHTML = `
      <div class="panel-thumb">${thumbHtml}</div>
      <div class="panel-body">
        <div class="panel-id-row">
          <span class="panel-id">${panelId}</span>
          <span class="status-pill ${isFlagged(panelId) ? "is-flagged" : "is-ok"}">${isFlagged(panelId) ? "⚑ flagged" : "✓ ok"}</span>
        </div>
        <div class="panel-text${panel.text ? "" : " silent"}">${textHtml}</div>
        <label class="review-label" for="issue-${panelId}">Review</label>
        <textarea id="issue-${panelId}" data-field="issue" placeholder="Leave empty if this panel is correct. Otherwise, say exactly what's wrong - e.g. 'This is attributed to the wrong character - the speech bubble tail points to the girl on the right, not Lloyd.'">${escapeHtml(current.issue)}</textarea>
        <select data-field="tag">${tagOptionsHtml(current.tag)}</select>
      </div>
    `;

  const take = (field) => (e) => paint(card, setFlagField(panelId, field, e.target.value));
  card.querySelector('[data-field="issue"]').addEventListener("input", take("issue"));
  card.querySelector('[data-field="tag"]').addEventListener("change", take("tag"));

  const img = card.querySelector('img[data-action="zoom"]');
  if (img) img.addEventListener("click", () => openLightbox(img.src, panelId));

  return card;
}

function paint(card, flagged) {
  card.classList.toggle("flagged", flagged);
  const pill = card.querySelector(".status-pill");
  pill.className = "status-pill " + (flagged ? "is-flagged" : "is-ok");
  pill.textContent = flagged ? "⚑ flagged" : "✓ ok";
}
