// The right-side navigator: one dot per panel, colored by written/empty,
// click to jump straight to it.
//
// Always fully rendered, unlike the cards: a few hundred small image-free
// divs cost nothing, and a navigator that only covered the mounted window
// would not be a navigator.

import { panels, textOf } from "./state.js";

const dots = new Map(); // panel_id -> nav dot element
let activePanelId = null;

export function buildNav(onJump) {
  const nav = document.getElementById("panel-nav");
  nav.innerHTML = "";
  dots.clear();
  for (const panel of panels) {
    const written = textOf(panel.panel_id).trim().length > 0;
    const dot = document.createElement("div");
    dot.className = "nav-dot" + (written ? " is-written" : "");
    dot.title = `${panel.panel_id}${written ? " — written" : " — empty"}`;
    dot.addEventListener("click", () => onJump(panel.panel_id));
    dots.set(panel.panel_id, dot);
    nav.appendChild(dot);
  }
}

export function setNavWritten(panelId, written) {
  const dot = dots.get(panelId);
  if (!dot) return;
  dot.classList.toggle("is-written", written);
  dot.title = `${panelId}${written ? " — written" : " — empty"}`;
}

export function setActiveNav(panelId) {
  if (panelId === activePanelId) return;
  const previous = dots.get(activePanelId);
  if (previous) previous.classList.remove("active");
  const next = dots.get(panelId);
  if (next) next.classList.add("active");
  activePanelId = panelId;
}
