// Canva/Illustrator-style zoom and free panning: fit-to-window on page load,
// the zoom-in/out buttons, Ctrl/Cmd+scroll (and trackpad pinch) to zoom
// anchored under the cursor, Alt+scroll to pan horizontally, plain
// scroll/trackpad to pan freely, and spacebar+drag / middle-mouse-drag to pan.
//
// Panning is NOT native element scrolling. canvasWrap is overflow:hidden and
// .page-stage is positioned with a CSS transform driven by state.panX/panY
// (see canvas.css). Native overflow:auto scrolling only has range to move
// when content overflows its box, so at "fit" zoom - where the page is
// deliberately sized to fit inside the viewport - there'd be nothing to
// scroll and every pan gesture would silently do nothing. Driving position
// with our own transform means panning always works, at any zoom level,
// the same way Canva/Illustrator's boundless canvas does.

import { stage, pageImg, canvasWrap, zoomLabel, zoomInBtn, zoomOutBtn } from "./dom.js";
import { state, currentPage } from "./state.js";
import { render } from "./render.js";

const MIN_SCALE = 0.05, MAX_SCALE = 8;

export function fitZoomToWrap(naturalW, naturalH) {
  // Extra margin (56px sides/top, 100px bottom for the floating hint-toast)
  // so the default fit-to-window view leaves the page clearly inset instead
  // of touching the viewport edge and floating UI.
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

export function applyPan() {
  stage.style.transform = `translate(${Math.round(state.panX)}px, ${Math.round(state.panY)}px)`;
}

// Re-centers the page horizontally with a fixed top inset, matching the
// margin fitZoomToWrap sized the default zoom around. Call after
// fitZoomToWrap()+applyZoom() on page load/resize; zoomTo() repositions
// independently (anchored under the cursor) once the user is panning/zooming
// by hand, so it does not re-center.
export function centerStage() {
  const page = currentPage();
  const stageW = Math.round(page.width * state.scale);
  state.panX = Math.round((canvasWrap.clientWidth - stageW) / 2);
  state.panY = 56;
  applyPan();
}

// The full "back to default" sequence - re-fit the zoom to the window and
// re-center - used on page load/resize and by the reset-view shortcut
// (Ctrl/Cmd+Tab by default; see ShortcutsConfig.reset_view) so a user who's
// zoomed/panned off into nowhere has one keypress back to a sane view.
export function resetView() {
  const page = currentPage();
  fitZoomToWrap(page.width, page.height);
  applyZoom();
  centerStage();
  render();
}

// Zoom while keeping a given point on the page (in canvasWrap viewport
// coordinates) visually fixed - the same anchor-under-cursor behavior as
// Canva/Illustrator's ctrl+scroll and +/- zoom, instead of always re-centering.
export function zoomTo(newScale, anchorClientX, anchorClientY) {
  newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, newScale));
  const wrapRect = canvasWrap.getBoundingClientRect();
  if (anchorClientX === undefined) {
    anchorClientX = wrapRect.left + wrapRect.width / 2;
    anchorClientY = wrapRect.top + wrapRect.height / 2;
  }
  // Point under the cursor, in unscaled stage coordinates (stable across a
  // scale change since it's the page content itself, not screen pixels).
  const stageX = (anchorClientX - wrapRect.left - state.panX) / state.scale;
  const stageY = (anchorClientY - wrapRect.top - state.panY) / state.scale;

  state.scale = newScale;
  applyZoom();

  state.panX = anchorClientX - wrapRect.left - stageX * newScale;
  state.panY = anchorClientY - wrapRect.top - stageY * newScale;
  applyPan();
  render();
}

zoomInBtn.addEventListener("click", () => zoomTo(state.scale + 0.1));
zoomOutBtn.addEventListener("click", () => zoomTo(state.scale - 0.1));

// Firefox reports a plain mouse wheel's notch as a handful of "lines"
// (e.deltaMode === 1, deltaY often as small as 1-3) while Chrome/Safari
// normalize wheel input to pixels (deltaMode === 0, deltaY ~= +-100 per
// notch). Used raw, that made every wheel gesture here - zoom, alt+pan,
// plain pan - land as an imperceptible few-pixel nudge in Firefox even
// though the identical gesture worked fine in Chrome. Normalize to an
// approximate pixel delta before using it anywhere below.
function wheelPixels(e) {
  const mult = e.deltaMode === 1 ? 16 /* DOM_DELTA_LINE */
    : e.deltaMode === 2 ? canvasWrap.clientHeight /* DOM_DELTA_PAGE */
    : 1 /* DOM_DELTA_PIXEL */;
  return { dx: e.deltaX * mult, dy: e.deltaY * mult };
}

canvasWrap.addEventListener("wheel", (e) => {
  const { dx, dy } = wheelPixels(e);

  if (e.ctrlKey || e.metaKey) {
    // Zoom, anchored under the cursor. Also fires for trackpad pinch, which
    // browsers report as a synthetic ctrl+wheel with small deltas.
    e.preventDefault();
    // A physical mouse wheel reports one notch as a single large delta,
    // which used unclamped blew straight past MAX/MIN_SCALE territory in
    // one tick. Clamp the per-event delta first so a mouse notch and a
    // trackpad-pinch step both land as one smooth, similarly sized zoom
    // increment - the calibrated feel Canva/Illustrator have.
    const delta = Math.max(-50, Math.min(50, dy));
    const factor = Math.exp(-delta * 0.003);
    zoomTo(state.scale * factor, e.clientX, e.clientY);
    return;
  }
  if (e.altKey) {
    // Alt+scroll pans horizontally (Illustrator/Canva-style), turning
    // vertical wheel motion sideways so a plain mouse wheel can scrub
    // through a wide page without a horizontal scroll input.
    e.preventDefault();
    state.panX -= (dy !== 0 ? dy : dx);
    applyPan();
    return;
  }
  // Plain wheel/trackpad: pan freely in both directions. canvasWrap has no
  // native scroll of its own (see file header) so this is the only thing
  // that moves the page for an unmodified scroll gesture.
  e.preventDefault();
  state.panX -= dx;
  state.panY -= dy;
  applyPan();
}, { passive: false });

// Spacebar-held + drag pans the canvas (hand tool), same as Illustrator/
// Photoshop/Canva. Also supports middle-mouse-button drag directly, no key
// needed.
function beginPan(e) {
  state.panning = {
    startX: e.clientX, startY: e.clientY,
    startPanX: state.panX, startPanY: state.panY,
  };
  canvasWrap.classList.add("panning");
  const onMove = (ev) => {
    if (!state.panning) return;
    state.panX = state.panning.startPanX + (ev.clientX - state.panning.startX);
    state.panY = state.panning.startPanY + (ev.clientY - state.panning.startY);
    applyPan();
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
  // Firefox binds a lone Alt press/release (with no other key involved) to
  // toggling its hidden menu bar - a browser-chrome accelerator, unrelated
  // to our altKey-modifier checks in the wheel handler above, which never
  // sees this because it only fires during an actual wheel event.
  // preventDefault on the Alt key itself is the standard way pages (image
  // editors, canvas tools) suppress it; this page has no text inputs, so
  // there's no AltGr/dead-key composition to preserve.
  if (e.key === "Alt") e.preventDefault();
});
document.addEventListener("keyup", (e) => {
  if (e.key === "Alt") e.preventDefault();
  if (e.code === "Space") {
    state.spaceHeld = false;
    canvasWrap.classList.remove("space-pan");
  }
});
