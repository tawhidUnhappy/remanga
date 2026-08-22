// Global keyboard shortcuts and the Draw/Select tool toggle they (and the
// toolbar buttons) share.

import { isMac, stage, toolDrawBtn, toolSelectBtn } from "./dom.js";
import { state } from "./state.js";
import { deleteMark, markFullPage } from "./marks.js";
import { loadPage, saveAndContinue } from "./page-nav.js";

export function setMode(next) {
  state.mode = next;
  toolDrawBtn.classList.toggle("active", state.mode === "draw");
  toolSelectBtn.classList.toggle("active", state.mode === "select");
  stage.classList.toggle("select-mode", state.mode === "select");
}
toolDrawBtn.addEventListener("click", () => setMode("draw"));
toolSelectBtn.addEventListener("click", () => setMode("select"));

document.addEventListener("keydown", (e) => {
  const cmd = isMac ? e.metaKey : e.ctrlKey;
  if (cmd && e.key.toLowerCase() === "s") { e.preventDefault(); saveAndContinue(); return; }
  if (cmd && e.key.toLowerCase() === "f") { e.preventDefault(); markFullPage(); return; }
  if (e.key === "d" || e.key === "D") setMode("draw");
  if (e.key === "v" || e.key === "V") setMode("select");
  if (e.key === "ArrowLeft") loadPage(state.pageIndex - 1);
  if (e.key === "ArrowRight") loadPage(state.pageIndex + 1);
  if ((e.key === "Delete" || e.key === "Backspace") && state.selectedId !== null) deleteMark(state.selectedId);
});
