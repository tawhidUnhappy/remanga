// Canva/Illustrator-style zoom and free panning: fit-to-window on page load,
// the zoom-in/out buttons, Ctrl/Cmd+scroll (and trackpad pinch) to zoom
// anchored under the cursor, Alt+scroll to pan horizontally, and
// spacebar+drag / middle-mouse-drag to pan.
// Plain wheel/trackpad scroll already pans freely for free since canvasWrap
// is a native overflow:auto viewport - no code needed for that case.

import { stage, pageImg, canvasWrap, zoomLabel, zoomInBtn, zoomOutBtn } from "./dom.js";
import { state, currentPage } from "./state.js";
import { render } from "./render.js";

const MIN_SCALE = 0.05, MAX_SCALE = 8;

export function fitZoomToWrap(naturalW, naturalH) {
  // Mirrors canvas-wrap's CSS padding (56px sides/top, 100px bottom for the
  // floating hint-toast) so the default fit-to-window view leaves the page
  // clearly inset instead of touching the viewport edge and floating UI.
  const availW = canvasWrap.clientWidth - 112;
  const availH = canvasWrap.clientHeight - 156;
  state.scale = Math.min(1, availW / naturalW, availH / naturalH);
  state.scale = Math.max(0.15, state.scale);
}

export function applyZoom() {
  const page = currentPage();
  stage.style.width = Math.round(page.width * state.scale) + "px";
  stage.style.height = Math.round(page.height * state.scale) + "px";
  pageImg.style.width = "100%";
  pageImg.style.height = "100%";
  zoomLabel.textContent = Math.round(state.scale * 100) + "%";
}

// Zoom while keeping a given point on the page (in canvasWrap viewport
// coordinates) visually fixed - the same anchor-under-cursor behavior as
// Canva/Illustrator's ctrl+scroll and +/- zoom, instead of always re-centering.
export function zoomTo(newScale, anchorClientX, anchorClientY) {
  newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, newScale));
  if (anchorClientX === undefined) {
    const rect = canvasWrap.getBoundingClientRect();
    anchorClientX = rect.left + rect.width / 2;
    anchorClientY = rect.top + rect.height / 2;
  }
  const wrapRect = canvasWrap.getBoundingClientRect();
  // Point under the cursor, in unscaled stage coordinates (stable across a
  // scale change since it's the page content itself, not screen pixels).
  const stageX = (canvasWrap.scrollLeft + anchorClientX - wrapRect.left) / state.scale;
  const stageY = (canvasWrap.scrollTop + anchorClientY - wrapRect.top) / state.scale;

  state.scale = newScale;
  applyZoom();
  render();

  canvasWrap.scrollLeft = stageX * state.scale - (anchorClientX - wrapRect.left);
  canvasWrap.scrollTop = stageY * state.scale - (anchorClientY - wrapRect.top);
}

zoomInBtn.addEventListener("click", () => zoomTo(state.scale + 0.1));
zoomOutBtn.addEventListener("click", () => zoomTo(state.scale - 0.1));

canvasWrap.addEventListener("wheel", (e) => {
  if (e.ctrlKey || e.metaKey) {
    // Zoom, anchored under the cursor. Also fires for trackpad pinch, which
    // browsers report as a synthetic ctrl+wheel with small deltas.
    e.preventDefault();
    // A physical mouse wheel reports one notch as a single large deltaY
    // (often +-100), which used unclamped blew straight past MAX/MIN_SCALE
    // territory in one tick. Clamp the per-event delta first so a mouse
    // notch and a trackpad-pinch step both land as one smooth, similarly
    // sized zoom increment - the calibrated feel Canva/Illustrator have.
    const delta = Math.max(-50, Math.min(50, e.deltaY));
    const factor = Math.exp(-delta * 0.003);
    zoomTo(state.scale * factor, e.clientX, e.clientY);
    return;
  }
  if (e.altKey) {
    // Alt+scroll pans horizontally (Illustrator/Canva-style), turning
    // vertical wheel motion sideways so a plain mouse wheel can scrub
    // through a wide page without a horizontal scroll input.
    e.preventDefault();
    canvasWrap.scrollLeft += (e.deltaY !== 0 ? e.deltaY : e.deltaX);
    return;
  }
  // plain scroll: let native panning happen
}, { passive: false });

// Spacebar-held + drag pans the canvas (hand tool), same as Illustrator/
// Photoshop/Canva. Also supports middle-mouse-button drag directly, no key
// needed.
function beginPan(e) {
  state.panning = {
    startX: e.clientX, startY: e.clientY,
    startScrollLeft: canvasWrap.scrollLeft, startScrollTop: canvasWrap.scrollTop,
  };
  canvasWrap.classList.add("panning");
  const onMove = (ev) => {
    if (!state.panning) return;
    canvasWrap.scrollLeft = state.panning.startScrollLeft - (ev.clientX - state.panning.startX);
    canvasWrap.scrollTop = state.panning.startScrollTop - (ev.clientY - state.panning.startY);
  };
  const onUp = () => {
    state.panning = null;
    canvasWrap.classList.remove("panning");
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
  };
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
}

canvasWrap.addEventListener("mousedown", (e) => {
  if (e.button === 1 || (e.button === 0 && state.spaceHeld)) {
    e.preventDefault();
    beginPan(e);
  }
}, { capture: true });

function isTypingTarget(el) {
  return el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
}

document.addEventListener("keydown", (e) => {
  if (e.code === "Space" && !e.repeat && !isTypingTarget(e.target)) {
    state.spaceHeld = true;
    canvasWrap.classList.add("space-pan");
    e.preventDefault();
  }
});
document.addEventListener("keyup", (e) => {
  if (e.code === "Space") {
    state.spaceHeld = false;
    canvasWrap.classList.remove("space-pan");
  }
});
