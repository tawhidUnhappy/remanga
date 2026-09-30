// The one-line status in the top bar.

const el = document.getElementById("status");
export const status = (text) => { el.textContent = text; el.title = text; };
