// Thin fetch() wrapper shared by every module that talks to the Flask
// backend (remanga/webui/server.py) - just adds a consistent error on a
// non-2xx response and JSON-decodes the body.

export async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    // The server explains its refusals in the body ({"error": ...}); that
    // sentence is what belongs in front of the user, not "-> 400". The status
    // rides along so callers can tell a stale write (409) from a real failure.
    let detail = "";
    try { detail = (await res.json()).error || ""; } catch {}
    const err = new Error(detail || `${path} -> ${res.status}`);
    err.status = res.status;
    throw err;
  }
  return res.json();
}
