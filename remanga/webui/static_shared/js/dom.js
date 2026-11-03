// The DOM helper the panel-list UIs share: text into markup, safely.

export function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}
