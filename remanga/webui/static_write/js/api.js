// Every request this UI makes (see remanga/webui/writer_routes.py).
//
// The server rewrites the whole narration.json on each text POST, so saving
// is per edited panel rather than resending the chapter each time.

export async function fetchNarration() {
  const res = await fetch("/api/narration");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function postText(panelId, text) {
  const res = await fetch(`/api/text/${encodeURIComponent(panelId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
}

// For a tab that is closing: a fetch() isn't guaranteed to complete once the
// page is unloading, but the browser keeps a beacon alive past navigation.
export function beaconText(panelId, text) {
  navigator.sendBeacon(
    `/api/text/${encodeURIComponent(panelId)}`,
    new Blob([JSON.stringify({ text })], { type: "application/json" }),
  );
}

export async function requestOcr(panelId) {
  const res = await fetch(`/api/ocr/${encodeURIComponent(panelId)}`, { method: "POST" });
  const result = await res.json();
  if (!result.ok) throw new Error(result.error || `HTTP ${res.status}`);
  return result;
}

export async function finishSession() {
  const res = await fetch("/api/finish", { method: "POST" });
  return res.json();
}
