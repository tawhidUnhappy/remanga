// The DOM helper every module here needs: text into markup, safely.

export function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}
