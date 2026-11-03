// Every request this UI makes (see remanga/webui/reviewer_routes.py).

export async function fetchNarration() {
  const res = await fetch("/api/narration");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function postFlag(panelId, flag) {
  const res = await fetch(`/api/flag/${encodeURIComponent(panelId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(flag),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

export async function finishReview(approved, generalNote) {
  const res = await fetch("/api/finish", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ approved, general_note: generalNote }),
  });
  return res.json();
}
