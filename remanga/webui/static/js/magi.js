// MAGI v3 panel-detection assist: kicks off /api/detect and polls its
// progress, merging newly-detected boxes into any page the user hasn't
// touched yet (touched pages are never clobbered - see remanga/webui/server.py).

import { assistBtn, assistProgressBar, assistStatus } from "./dom.js";
import { state, currentFilename } from "./state.js";
import { api } from "./api.js";
import { render } from "./render.js";

export async function runDetect() {
  try {
    await api("/api/detect", { method: "POST" });
  } catch (e) {
    console.error(e);
  }
}
assistBtn.addEventListener("click", runDetect);

export async function pollDetectStatus() {
  if (!state.magiEnabled) return;
  let status;
  try { status = await api("/api/detect/status"); } catch { return; }

  assistBtn.disabled = status.running;
  if (status.running) {
    assistProgressBar.style.width = status.total ? Math.round((status.done / status.total) * 100) + "%" : "0%";
    assistStatus.textContent = `Detecting… ${status.done}/${status.total} pages`;
  } else if (status.error) {
    assistStatus.textContent = "Error: " + status.error;
  } else if (status.total) {
    assistProgressBar.style.width = "100%";
    assistStatus.textContent = `Done · ${status.total} page(s) processed`;
  }

  let currentPageChanged = false;
  for (const [filename, serverMarks] of Object.entries(status.marks || {})) {
    if (state.touchedPages.has(filename)) continue;
    state.pageMarksCache[filename] = serverMarks;
    if (state.chapter.pages[state.pageIndex].filename === filename) currentPageChanged = true;
  }
  if (currentPageChanged) {
    state.marks = state.pageMarksCache[currentFilename()];
    render();
  }
}
