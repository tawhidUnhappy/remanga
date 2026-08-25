// Moving or resizing an *existing* mark by dragging its body or one of its
// eight resize handles (drawing a brand-new mark lives in draw.js).

import { stage } from "./dom.js";
import { state } from "./state.js";
import { render } from "./render.js";
import { markDirty } from "./marks.js";
import { showGuides, clearGuides } from "./guides.js";

export function onMarkMouseDown(e, m) {
  if (e.button === 2) return;
  e.stopPropagation();

  const handle = e.target.classList.contains("handle") ? [...e.target.classList].find(c => c !== "handle") : null;
  const wasSelected = state.selectedId === m.id;
  state.selectedId = m.id;

  // Clicking a mark that wasn't already selected only selects it - it
  // doesn't also start moving it in the same gesture. Without this, a
  // single click-drag both selected AND moved whatever mark happened to be
  // under the cursor, so on a page with tightly packed/overlapping panels
  // it was easy to nudge the wrong neighboring mark by accident while
  // aiming for another one. A second, deliberate drag on the now-selected
  // mark is what actually adjusts it - one mark at a time. Resize handles
  // only ever render on the already-selected mark (see render.js), so a
  // handle-drag is unaffected by this and still works on the first click.
  if (!handle && !wasSelected) {
    render();
    return;
  }

  const startX = e.clientX, startY = e.clientY;
  const orig = { ...m };
  render();

  // render() above just tore down and rebuilt every mark div (needed so a
  // freshly-selected mark grows its handles before the drag starts), which
  // means the element the mousedown actually landed on (e.currentTarget) no
  // longer exists in the DOM - it's been replaced by an equivalent new node.
  // Re-find that node once, up front, and mutate *only it* for the rest of
  // the gesture instead of calling render() again on every mousemove. A full
  // render() rebuilds every mark AND the entire sidebar list from scratch;
  // doing that 60+ times a second during a drag is enough DOM churn that
  // fast or sustained drags visibly stutter and can drop/desync from the
  // mouse mid-gesture. Updating this one element's inline style per move is
  // the event-driven equivalent: react to what actually changed (this
  // mark's box) instead of re-scanning and repainting the whole page on
  // every tick.
  const el = stage.querySelector(`.mark[data-mark-id="${CSS.escape(String(m.id))}"]`);
  const dimEl = el?.querySelector(".dim-readout");

  function onMove(ev) {
    const dxDisplay = ev.clientX - startX, dyDisplay = ev.clientY - startY;
    const dx = dxDisplay / state.scale, dy = dyDisplay / state.scale;
    const page = state.chapter.pages[state.pageIndex];
    let { x, y, w, h } = orig;

    if (handle) {
      // Each side resizes from its FIXED opposite edge (e.g. dragging the
      // west handle keeps the east edge, orig.x + orig.w, anchored) and
      // clamps the moving edge between that anchor (minus a 4px floor) and
      // the page bound. Previously the moving edge and the size were
      // computed independently - once dragging ran past the opposite edge
      // (or off the page), the size floored at 4px but the position kept
      // following the cursor unbounded, so the box appeared to detach and
      // "expand" off the opposite side instead of just stopping in place.
      if (handle.includes("e")) {
        const right = Math.min(page.width, Math.max(orig.x + 4, orig.x + orig.w + dx));
        w = right - orig.x;
      }
      if (handle.includes("w")) {
        const right = orig.x + orig.w; // fixed
        x = Math.max(0, Math.min(right - 4, orig.x + dx));
        w = right - x;
      }
      if (handle.includes("s")) {
        const bottom = Math.min(page.height, Math.max(orig.y + 4, orig.y + orig.h + dy));
        h = bottom - orig.y;
      }
      if (handle.includes("n")) {
        const bottom = orig.y + orig.h; // fixed
        y = Math.max(0, Math.min(bottom - 4, orig.y + dy));
        h = bottom - y;
      }
    } else {
      // Moving the whole mark keeps its size fixed - just stop translating
      // at the page edge instead of shrinking it.
      x = Math.max(0, Math.min(orig.x + dx, page.width - orig.w));
      y = Math.max(0, Math.min(orig.y + dy, page.height - orig.h));
    }

    m.x = x; m.y = y; m.w = w; m.h = h;
    if (m.src === "ai") m.src = "manual"; // any manual adjustment promotes it

    const activeDisplay = { x: m.x * state.scale, y: m.y * state.scale, w: m.w * state.scale, h: m.h * state.scale };
    const othersDisplay = state.marks.filter(o => o.id !== m.id).map(o => ({
      x: o.x * state.scale, y: o.y * state.scale, w: o.w * state.scale, h: o.h * state.scale,
    }));
    showGuides(activeDisplay, othersDisplay);

    if (el) {
      el.style.left = activeDisplay.x + "px";
      el.style.top = activeDisplay.y + "px";
      el.style.width = activeDisplay.w + "px";
      el.style.height = activeDisplay.h + "px";
    }
    if (dimEl) dimEl.textContent = Math.round(m.w) + " × " + Math.round(m.h) + " px";
  }
  function onUp() {
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
    clearGuides();
    markDirty();
    // The one full re-render for this gesture: syncs the sidebar list (its
    // dimensions text, panel order) and re-derives everything from state
    // now that the drag is over, rather than on every intermediate move.
    render();
  }
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
}
