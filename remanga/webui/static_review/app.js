// Narration Reviewer frontend: one flat list of panel cards, each toggleable
// between "ok" (no flag) and "flagged" (issue note + optional tag). No
// canvas/drag state to manage - see marker's static/js/ for that pattern;
// this UI only ever needs a list editor.

let PANELS = [];
let CHAPTER = null;
let ROUND = null;
const flags = new Map(); // panel_id -> {issue, tag}

const TAGS = [
  ["", "No specific category"],
  ["wrong_detail", "Wrong/invented detail (doesn't match the art)"],
  ["wrong_speaker", "Wrong speaker attribution"],
  ["dropped_content", "Dropped dialogue/action"],
  ["spoiler", "Spoiler / name used too early"],
  ["punctuation", "Punctuation overplayed or flat"],
  ["word_budget", "Too long / too short"],
  ["continuity", "Contradicts memory.json continuity"],
  ["other", "Other"],
];

async function main() {
  const res = await fetch("/api/narration");
  if (!res.ok) {
    document.getElementById("loading").textContent = "Failed to load narration.json.";
    return;
  }
  const data = await res.json();
  PANELS = data.panels;
  CHAPTER = data.chapter;
  ROUND = data.round;

  for (const p of PANELS) {
    if (p.flag) flags.set(p.panel_id, { issue: p.flag.issue || "", tag: p.flag.tag || "" });
  }

  document.getElementById("chapter-meta").textContent = `Chapter ${CHAPTER} — round ${ROUND} — ${PANELS.length} panel(s)`;
  document.title = `Narration Reviewer — Ch. ${CHAPTER}`;
  document.getElementById("loading").style.display = "none";
  document.getElementById("hint").style.display = "block";
  document.getElementById("general-note-wrap").style.display = "block";
  document.getElementById("footer").style.display = "flex";

  render();
  wireFooter();
}

function tagOptionsHtml(selected) {
  return TAGS.map(([v, label]) => `<option value="${v}" ${v === selected ? "selected" : ""}>${label}</option>`).join("");
}

function render() {
  const list = document.getElementById("panel-list");
  list.innerHTML = "";
  for (const p of PANELS) {
    const flagged = flags.has(p.panel_id);
    const card = document.createElement("div");
    card.className = "panel-card" + (flagged ? " flagged" : "");
    card.dataset.panelId = p.panel_id;

    const thumbHtml = p.image
      ? `<img src="/api/panels/${encodeURIComponent(p.image)}" loading="lazy" alt="${p.panel_id}">`
      : `<div class="missing">no cropped image found for ${p.panel_id}</div>`;

    const textHtml = p.text
      ? escapeHtml(p.text)
      : `<span class="silent">(silent beat — empty text)</span>`;

    const current = flags.get(p.panel_id) || { issue: "", tag: "" };

    card.innerHTML = `
      <div class="panel-thumb">${thumbHtml}</div>
      <div class="panel-body">
        <div class="panel-id">${p.panel_id}</div>
        <div class="panel-text${p.text ? "" : " silent"}">${textHtml}</div>
        <div class="flag-row">
          <button class="toggle-btn ${flagged ? "is-flagged" : "is-ok"}" data-action="toggle">
            ${flagged ? "⚑ Flagged" : "✓ Looks correct"}
          </button>
        </div>
        <div class="issue-box ${flagged ? "open" : ""}">
          <select data-field="tag">${tagOptionsHtml(current.tag)}</select>
          <textarea data-field="issue" placeholder="What's wrong, specifically? e.g. 'This is attributed to the wrong character - the speech bubble tail points to the girl on the right, not Lloyd.'">${escapeHtml(current.issue)}</textarea>
        </div>
      </div>
    `;

    card.querySelector('[data-action="toggle"]').addEventListener("click", () => toggleFlag(p.panel_id, card));
    const issueBox = card.querySelector(".issue-box");
    issueBox.querySelector('[data-field="issue"]').addEventListener("input", (e) => updateFlag(p.panel_id, "issue", e.target.value));
    issueBox.querySelector('[data-field="tag"]').addEventListener("change", (e) => updateFlag(p.panel_id, "tag", e.target.value));

    list.appendChild(card);
  }
  updateCounts();
}

function toggleFlag(panelId, card) {
  if (flags.has(panelId)) {
    flags.delete(panelId);
  } else {
    flags.set(panelId, { issue: "", tag: "" });
  }
  const flagged = flags.has(panelId);
  card.classList.toggle("flagged", flagged);
  const btn = card.querySelector('[data-action="toggle"]');
  btn.className = "toggle-btn " + (flagged ? "is-flagged" : "is-ok");
  btn.textContent = flagged ? "⚑ Flagged" : "✓ Looks correct";
  card.querySelector(".issue-box").classList.toggle("open", flagged);
  if (flagged) card.querySelector('[data-field="issue"]').focus();
  updateCounts();
}

function updateFlag(panelId, field, value) {
  const current = flags.get(panelId) || { issue: "", tag: "" };
  current[field] = value;
  flags.set(panelId, current);
}

function updateCounts() {
  document.getElementById("counts").innerHTML = `<b>${flags.size}</b> / ${PANELS.length} flagged`;
  document.getElementById("btn-approve").disabled = flags.size > 0;
}

function escapeHtml(s) {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

async function submitReview(approved) {
  const general_note = document.getElementById("general-note").value;

  // Push every flag's latest issue text to the server before finishing -
  // the per-keystroke handlers above only update local state.
  for (const [panelId, data] of flags.entries()) {
    await fetch(`/api/flag/${encodeURIComponent(panelId)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
  }

  const res = await fetch("/api/finish", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, general_note }),
  });
  const result = await res.json();
  if (result.ok) {
    document.body.innerHTML = `<main><h1 style="padding-top:60px;text-align:center">
      ${approved ? "✓ Approved — you can close this tab." : `✓ ${result.flagged_count} issue(s) saved to narration_review.json — you can close this tab.`}
    </h1></main>`;
  }
}

function wireFooter() {
  document.getElementById("btn-approve").addEventListener("click", () => {
    if (flags.size > 0) return;
    submitReview(true);
  });
  document.getElementById("btn-submit").addEventListener("click", () => {
    if (flags.size === 0) {
      if (!confirm("No panels are flagged. Submit anyway (equivalent to Approve)?")) return;
    }
    submitReview(false);
  });
}

main();
