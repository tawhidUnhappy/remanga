// The session outline: every chapter, every page, every panel, as one
// collapsible tree in the sidebar - and the fastest way to get to any of
// them.
//
// The chapter arrows in the top bar walk the session one step at a time,
// which is the wrong tool for "show me panel 3 of page 12 of chapter 7" and
// hopeless for "did chapter 4 actually get marked?". This is the other view:
// the whole session at once, collapsed to the depth you're actually looking
// at.
//
// Everything below the open chapter is built lazily. A hundred-chapter
// project has thousands of pages and tens of thousands of panels; rendering
// that eagerly would be a DOM the browser has to fight, for rows nobody is
// looking at. Collapsed chapters are one row each, and a page's panels only
// exist while that page is expanded.

import { outlineTree, outlineSummary } from "./dom.js";
import { state } from "./state.js";
import { api } from "./api.js";

// Which groups are open, by key ("ch:3", "pg:3:001_004.jpg"). Kept across
// re-renders so marking a panel doesn't collapse the tree you're working in.
const open = new Set();

// The last outline fetched from the server. The chapter on screen is drawn
// from live client state instead (see chapterPages) - it changes with every
// mark, and refetching for each one would be a request per keystroke.
let outline = [];

export async function refreshOutline() {
  try {
    const res = await api("/api/outline");
    outline = res.chapters || [];
  } catch {
    outline = [];
  }
  if (state.chapter) open.add(`ch:${state.chapter.chapter_index}`);
  renderOutline();
}

// Panel counts for one chapter. For the chapter on screen these come from
// the client's own cache, so the tree updates as marks are drawn or deleted;
// for every other chapter they're whatever the server last reported.
function chapterPages(entry) {
  if (state.chapter && entry.index === state.chapter.chapter_index) {
    return state.chapter.pages.map(page => ({
      index: page.index,
      filename: page.filename,
      panels: (state.pageMarksCache[page.filename] || []).length,
      decided: state.touchedPages.has(page.filename),
    }));
  }
  return entry.pages;
}

function chevron(isOpen) {
  const el = document.createElement("span");
  el.className = "ol-chev" + (isOpen ? " open" : "");
  el.textContent = "›";
  return el;
}

// An empty page is two different things, and the difference is the whole
// point of looking at this list on a half-finished chapter:
//   0  (dashed)  nobody has been here - MAGI will still detect it
//   —  (solid)   somebody looked and said there are no panels
// A page with panels just shows how many.
function pagePill(page) {
  const el = document.createElement("span");
  if (page.panels) {
    el.className = "ol-pill mono";
    el.textContent = String(page.panels);
  } else if (page.decided) {
    el.className = "ol-pill mono none";
    el.textContent = "—";
    el.title = "No panels on this page - decided";
  } else {
    el.className = "ol-pill mono muted";
    el.textContent = "0";
    el.title = "Not marked yet";
  }
  return el;
}

function toggle(key) {
  if (open.has(key)) open.delete(key); else open.add(key);
  renderOutline();
}

function renderPanels(page, chapterIndex) {
  const wrap = document.createElement("div");
  wrap.className = "ol-panels";
  if (!page.panels) {
    const none = document.createElement("div");
    none.className = "ol-none";
    none.textContent = page.decided ? "no panels here — decided" : "not marked yet";
    wrap.appendChild(none);
    return wrap;
  }
  // Panel numbers are positions in reading order - the same thing the page's
  // own panel list shows, and the same thing that becomes panel_id in
  // crops.json - so a row here names exactly what a row there does.
  for (let i = 0; i < page.panels; i++) {
    const btn = document.createElement("button");
    btn.className = "ol-panel";
    btn.textContent = `Panel ${i + 1}`;
    btn.addEventListener("click", () => goTo(chapterIndex, page.index - 1, i));
    wrap.appendChild(btn);
  }
  return wrap;
}

function renderPage(page, chapterIndex, isCurrentChapter) {
  const key = `pg:${chapterIndex}:${page.filename}`;
  const isOpen = open.has(key);
  const isCurrent = isCurrentChapter && state.chapter
    && state.chapter.pages[state.pageIndex]
    && state.chapter.pages[state.pageIndex].filename === page.filename;

  const row = document.createElement("div");
  row.className = "ol-page" + (isCurrent ? " current" : "");

  const head = document.createElement("button");
  head.className = "ol-page-head";
  head.appendChild(chevron(isOpen));
  const name = document.createElement("span");
  name.className = "ol-page-name mono";
  name.textContent = String(page.index).padStart(2, "0");
  head.appendChild(name);
  const label = document.createElement("span");
  label.className = "ol-page-label";
  label.textContent = page.filename;
  head.appendChild(label);
  head.appendChild(pagePill(page));
  // The chevron expands in place; the row itself navigates. Two jobs, two
  // targets, no modifier keys.
  head.addEventListener("click", (e) => {
    if (e.target.closest(".ol-chev")) { toggle(key); return; }
    open.add(key);
    goTo(chapterIndex, page.index - 1, null);
  });
  row.appendChild(head);

  if (isOpen) row.appendChild(renderPanels(page, chapterIndex));
  return row;
}

function renderChapter(entry) {
  const key = `ch:${entry.index}`;
  const isOpen = open.has(key);
  const isCurrent = state.chapter && entry.index === state.chapter.chapter_index;
  const pages = chapterPages(entry);
  const panels = pages.reduce((n, p) => n + p.panels, 0);
  const marked = pages.filter(p => p.panels).length;

  const box = document.createElement("div");
  box.className = "ol-chapter" + (isCurrent ? " current" : "");

  const head = document.createElement("button");
  head.className = "ol-chapter-head";
  head.appendChild(chevron(isOpen));
  const name = document.createElement("span");
  name.className = "ol-chapter-name";
  name.textContent = `Chapter ${entry.chapter}`;
  head.appendChild(name);

  const waiting = pages.filter(p => !p.decided && !p.panels).length;
  const meta = document.createElement("span");
  meta.className = "ol-meta mono" + (waiting ? " waiting" : "");
  meta.textContent = waiting ? `${marked}/${pages.length} · ${panels} · ${waiting}?`
                             : `${marked}/${pages.length} · ${panels}`;
  meta.title = `${marked} of ${pages.length} page(s) marked · ${panels} panel(s)`
             + (waiting ? ` · ${waiting} page(s) nobody has looked at yet` : " · every page accounted for");
  head.appendChild(meta);

  head.addEventListener("click", (e) => {
    if (e.target.closest(".ol-chev") || isCurrent) { toggle(key); return; }
    // Clicking another chapter's header is the common case for "take me
    // there", so it navigates AND opens - one click, not two.
    open.add(key);
    goTo(entry.index, 0, null);
  });
  box.appendChild(head);

  if (isOpen) {
    const list = document.createElement("div");
    list.className = "ol-pages";
    for (const page of pages) list.appendChild(renderPage(page, entry.index, isCurrent));
    box.appendChild(list);
  }
  return box;
}

export function renderOutline() {
  outlineTree.replaceChildren();
  if (!outline.length) return;

  const totalPanels = outline.reduce(
    (n, entry) => n + chapterPages(entry).reduce((m, p) => m + p.panels, 0), 0);
  const totalPages = outline.reduce((n, entry) => n + chapterPages(entry).length, 0);
  outlineSummary.textContent =
    `${outline.length} chapter(s) · ${totalPages} page(s) · ${totalPanels} panel(s)`;

  for (const entry of outline) outlineTree.appendChild(renderChapter(entry));
}

// Jump anywhere in the session: chapter, then page, then (optionally) select
// a panel. Imported lazily to keep the module graph one-way - chapter-nav.js
// imports this one, for the refresh after a chapter change.
async function goTo(chapterIndex, pageIndex, panelIndex) {
  const { gotoChapter } = await import("./chapter-nav.js");
  const { loadPage } = await import("./page-nav.js");
  const { render } = await import("./render.js");

  if (!state.chapter || chapterIndex !== state.chapter.chapter_index) {
    await gotoChapter(chapterIndex, pageIndex);
  } else if (pageIndex !== state.pageIndex) {
    await loadPage(pageIndex);
  }
  if (panelIndex !== null && state.marks[panelIndex]) {
    state.selectedId = state.marks[panelIndex].id;
    render();
    document.querySelector(`.mark[data-mark-id="${CSS.escape(String(state.selectedId))}"]`)
      ?.scrollIntoView({ block: "center", inline: "center", behavior: "smooth" });
  }
  renderOutline();
}
