// Which of the sidebar's two panes is showing: the current page's panels, or
// the whole session's outline.
//
// A switch rather than a scroll: both lists want the full height of the
// sidebar, and stacking them would mean each is always half-hidden by the
// other. Switching keeps each one whole, and keeps its own scroll position -
// coming back to "All chapters" lands where you left it, not at the top.

import { tabPageBtn, tabSessionBtn, panePage, paneSession } from "./dom.js";

export function showPane(which) {
  const session = which === "session";
  panePage.hidden = session;
  paneSession.hidden = !session;
  tabPageBtn.classList.toggle("active", !session);
  tabSessionBtn.classList.toggle("active", session);
}

tabPageBtn.addEventListener("click", () => showPane("page"));
tabSessionBtn.addEventListener("click", () => showPane("session"));
