// Moving or resizing an *existing* mark by dragging its body or one of its
// eight resize handles (drawing a brand-new mark lives in draw.js).

import { state } from "./state.js";
import { render } from "./render.js";
import { markDirty } from "./marks.js";
import { showGuides, clearGuides } from "./guides.js";

export function onMarkMouseDown(e, m) {
  if (e.button === 2) return;
  e.stopPropagation();
  state.selectedId = m.id;
  const handle = e.target.classList.contains("handle") ? [...e.target.classList].find(c => c !== "handle") : null;
  const startX = e.clientX, startY = e.clientY;
  const orig = { ...m };
  render();

  function onMove(ev) {
    const dxDisplay = ev.clientX - startX, dyDisplay = ev.clientY - startY;
    const dx = dxDisplay / state.scale, dy = dyDisplay / state.scale;
    let { x, y, w, h } = orig;

    if (handle) {
      if (handle.includes("e")) w = Math.max(4, orig.w + dx);
      if (handle.includes("s")) h = Math.max(4, orig.h + dy);
      if (handle.includes("w")) { x = orig.x + dx; w = Math.max(4, orig.w - dx); }
      if (handle.includes("n")) { y = orig.y + dy; h = Math.max(4, orig.h - dy); }
    } else {
      x = orig.x + dx; y = orig.y + dy;
    }

    const page = state.chapter.pages[state.pageIndex];
    x = Math.max(0, Math.min(x, page.width - 4));
    y = Math.max(0, Math.min(y, page.height - 4));
    w = Math.min(w, page.width - x);
    h = Math.min(h, page.height - y);

    m.x = x; m.y = y; m.w = w; m.h = h;
    if (m.src === "ai") m.src = "manual"; // any manual adjustment promotes it

    const activeDisplay = { x: m.x * state.scale, y: m.y * state.scale, w: m.w * state.scale, h: m.h * state.scale };
    const othersDisplay = state.marks.filter(o => o.id !== m.id).map(o => ({
      x: o.x * state.scale, y: o.y * state.scale, w: o.w * state.scale, h: o.h * state.scale,
    }));
    showGuides(activeDisplay, othersDisplay);
    render();
  }
  function onUp() {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    clearGuides();
    markDirty();
  }
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
}
