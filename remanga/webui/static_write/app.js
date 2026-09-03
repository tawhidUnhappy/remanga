// Narration Writer frontend: one flat list of panel cards, each showing the
// panel's cropped image and a text field the user types the narration line
// into directly. No flag/issue concept here (see the Reviewer's app.js for
// that pattern) - this UI writes narration.json itself.

let PANELS = [];
let CHAPTER = null;
const texts = new Map(); // panel_id -> text

async function main() {
  const res = await fetch("/api/narration");
  if (!res.ok) {
    document.getElementById("loading").textContent = "Failed to load panels.";
    return;
  }
  const data = await res.json();
  PANELS = data.panels;
  CHAPTER = data.chapter;

  for (const p of PANELS) texts.set(p.panel_id, p.text || "");

  document.getElementById("chapter-meta").textContent = `Chapter ${CHAPTER} — ${PANELS.length} panel(s)`;
  document.title = `Narration Writer — Ch. ${CHAPTER}`;
  document.getElementById("loading").style.display = "none";
  document.getElementById("hint").style.display = "block";
  document.getElementById("footer").style.display = "flex";

  render();
  wireFooter();
  wireLightbox();
}

function render() {
  const list = document.getElementById("panel-list");
  list.innerHTML = "";
  for (const p of PANELS) {
    const text = texts.get(p.panel_id) || "";
    const card = document.createElement("div");
    card.className = "panel-card" + (text.trim() ? "" : " empty");
    card.dataset.panelId = p.panel_id;

    const thumbHtml = p.image
      ? `<img src="/api/panels/${encodeURIComponent(p.image)}" loading="lazy" alt="${p.panel_id}" data-action="zoom">`
      : `<div class="missing">No image file found for this panel.</div>`;

    card.innerHTML = `
      <div class="panel-thumb">${thumbHtml}</div>
      <div class="panel-body">
        <div class="panel-id-row">
          <span class="panel-id">${p.panel_id}</span>
          <span class="status-pill ${text.trim() ? "is-written" : "is-empty"}">${text.trim() ? "✓ written" : "○ empty"}</span>
        </div>
        <label class="text-label" for="text-${p.panel_id}">Narration</label>
        <textarea id="text-${p.panel_id}" placeholder="Type the narration line for this panel - leave empty for a silent beat.">${escapeHtml(text)}</textarea>
      </div>
    `;

    const textField = card.querySelector("textarea");
    textField.addEventListener("input", (e) => updateText(p.panel_id, e.target.value, card));

    const img = card.querySelector('img[data-action="zoom"]');
    if (img) img.addEventListener("click", () => openLightbox(img.src, p.panel_id));

    list.appendChild(card);
  }
  updateCounts();
}

function updateText(panelId, value, card) {
  texts.set(panelId, value);
  const written = value.trim().length > 0;
  card.classList.toggle("empty", !written);
  const pill = card.querySelector(".status-pill");
  pill.className = "status-pill " + (written ? "is-written" : "is-empty");
  pill.textContent = written ? "✓ written" : "○ empty";
  updateCounts();
}

function updateCounts() {
  const written = [...texts.values()].filter((t) => t.trim()).length;
  document.getElementById("counts").innerHTML = `<b>${written}</b> / ${PANELS.length} written`;
}

function openLightbox(src, alt) {
  const lb = document.getElementById("lightbox");
  const img = document.getElementById("lightbox-img");
  img.src = src;
  img.alt = alt;
  lb.classList.add("open");
}

function closeLightbox() {
  document.getElementById("lightbox").classList.remove("open");
}

function wireLightbox() {
  document.getElementById("lightbox").addEventListener("click", closeLightbox);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeLightbox();
  });
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

async function saveNarration() {
  const emptyCount = PANELS.length - [...texts.values()].filter((t) => t.trim()).length;
  if (emptyCount > 0) {
    if (!confirm(`${emptyCount} panel(s) still have no narration text. Save anyway?`)) return;
  }

  // Push every panel's latest text to the server before finishing - the
  // per-keystroke handler above only updates local state.
  for (const p of PANELS) {
    await fetch(`/api/text/${encodeURIComponent(p.panel_id)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: texts.get(p.panel_id) || "" }),
    });
  }

  const res = await fetch("/api/finish", { method: "POST" });
  const result = await res.json();
  if (result.ok) {
    document.body.innerHTML = `<main><h1 style="padding-top:60px;text-align:center">
      ✓ Saved ${result.written}/${result.total_panels} panel(s) to narration.json — you can close this tab.
    </h1></main>`;
  }
}

function wireFooter() {
  document.getElementById("btn-save").addEventListener("click", saveNarration);
}

main();
