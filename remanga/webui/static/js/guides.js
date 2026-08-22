// Canva-style alignment guides: while dragging/resizing a mark, draw a
// snap-line whenever one of its edges/midlines is within THRESH px of
// another mark's on this page.

import { stage } from "./dom.js";

const THRESH = 5;

export function showGuides(activeDisplay, othersDisplay) {
  stage.querySelectorAll(".guide-line").forEach(el => el.remove());
  const edgesX = [activeDisplay.x, activeDisplay.x + activeDisplay.w / 2, activeDisplay.x + activeDisplay.w];
  const edgesY = [activeDisplay.y, activeDisplay.y + activeDisplay.h / 2, activeDisplay.y + activeDisplay.h];
  othersDisplay.forEach(o => {
    const oEdgesX = [o.x, o.x + o.w / 2, o.x + o.w];
    const oEdgesY = [o.y, o.y + o.h / 2, o.y + o.h];
    edgesX.forEach(ax => oEdgesX.forEach(ox => { if (Math.abs(ax - ox) < THRESH) drawGuide("v", ox); }));
    edgesY.forEach(ay => oEdgesY.forEach(oy => { if (Math.abs(ay - oy) < THRESH) drawGuide("h", oy); }));
  });
}

function drawGuide(axis, pos) {
  const line = document.createElement("div");
  line.className = "guide-line " + axis;
  if (axis === "v") line.style.left = pos + "px"; else line.style.top = pos + "px";
  stage.appendChild(line);
}

export function clearGuides() {
  stage.querySelectorAll(".guide-line").forEach(el => el.remove());
}
