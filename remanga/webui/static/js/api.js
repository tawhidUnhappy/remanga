// Thin fetch() wrapper shared by every module that talks to the Flask
// backend (remanga/webui/server.py) - just adds a consistent error on a
// non-2xx response and JSON-decodes the body.

export async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.json();
}
