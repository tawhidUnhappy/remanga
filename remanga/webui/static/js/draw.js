// Drawing a brand-new mark by dragging on empty canvas (Canva-style: the
// drag can start outside the page bounds and still produce a clamped box).

import { stage, canvasWrap } from "./dom.js";
import { state } from "./state.js";
import { render } from "./render.js";
import { markDirty, clampBoxToPage } from "./marks.js";

let drawing = null, ghostEl = null;

canvasWrap.addEventListener("mousedown", (e) => {
  if (e.target.closest(".mark")) return; // let mark-level handler deal with it
  if (e.button !== 0 || state.spaceHeld) return;

  // Clicking the canvas background - not a mark, whether that's empty
  // space on the page or outside it entirely - deselects whatever mark
  // was selected and clears its highlight/handles. This applies in both
  // Draw and Select mode (in Select mode nothing else would ever clear a
  // selection), and runs before the draw-mode-only new-box gesture below
  // so it always takes effect even when the click goes on to draw a new
  // box (which then selects itself once finished, in onUp).
  if (state.selectedId !== null) {
    state.selectedId = null;
    render();
  }

  if (state.mode !== "draw") return;
  e.preventDefault();

  const rect = stage.getBoundingClientRect();
  const anchorX = e.clientX - rect.left;   // may be negative or beyond stage size - that's fine
  const anchorY = e.clientY - rect.top;
  drawing = { anchorX, anchorY, x: anchorX, y: anchorY, w: 0, h: 0 };
  ghostEl = document.createElement("div");
  ghostEl.className = "draw-ghost";
  stage.appendChild(ghostEl);

  function onMove(ev) {
    const cx = ev.clientX - rect.left, cy = ev.clientY - rect.top;
    const x = Math.min(cx, drawing.anchorX), y = Math.min(cy, drawing.anchorY);
    const w = Math.abs(cx - drawing.anchorX), h = Math.abs(cy - drawing.anchorY);
    Object.assign(ghostEl.style, { left: x + "px", top: y + "px", width: w + "px", height: h + "px" });
    drawing.x = x; drawing.y = y; drawing.w = w; drawing.h = h;
  }
  function onUp() {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    ghostEl?.remove();
    if (drawing.w > 8 && drawing.h > 8) {
      const natural = clampBoxToPage(drawing.x / state.scale, drawing.y / state.scale, drawing.w / state.scale, drawing.h / state.scale);
      const m = { id: "local-" + (state.nextLocalId++), ...natural, src: "manual" };
      state.marks.push(m);
      state.selectedId = m.id;
      markDirty();
      render();
    }
    drawing = null;
  }
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
});

// Covers the whole canvas, not just the page - including the padding/
// background around it - so right-click never falls through to the
// browser's native context menu anywhere over the canvas. (Marks have
// their own contextmenu handler, in render.js, that also deletes them;
// this one is a catch-all and doesn't interfere with that.)
canvasWrap.addEventListener("contextmenu", (e) => e.preventDefault());
