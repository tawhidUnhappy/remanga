// The sliding window of mounted cards.
//
// Only a bounded range of panel CARDS is ever in the DOM at once, centered on
// wherever you are scrolled to. Scrolling toward either edge grows the range
// that way and, once it has grown past MAX_RENDERED, trims the opposite
// (off-screen) end back off - so memory, DOM size and decoded-image cost stay
// roughly constant however many panels the chapter has, instead of a whole
// chapter of full-resolution images sitting in the document at once.

import { buildCard } from "./card.js";
import { panels } from "./state.js";

const CHUNK = 8; // panels added per scroll-triggered extension
const MAX_RENDERED = 24; // cards kept mounted before the far end gets trimmed

let renderStart = 0; // inclusive index into panels
let renderEnd = 0; // exclusive index into panels
let listEl, topSentinel, bottomSentinel;
let topObserver, bottomObserver, centerObserver;

export function initVirtualList({ onActive }) {
  listEl = document.getElementById("panel-list");
  listEl.innerHTML = "";

  topSentinel = document.createElement("div");
  topSentinel.className = "scroll-sentinel";
  bottomSentinel = document.createElement("div");
  bottomSentinel.className = "scroll-sentinel";
  listEl.appendChild(topSentinel);
  listEl.appendChild(bottomSentinel);

  // A big rootMargin on both edges means "start loading/unloading well before
  // the sentinel is actually on screen" - keeps scrolling smooth instead of
  // popping in a chunk right at the visible edge.
  topObserver = new IntersectionObserver(onTopVisible, { rootMargin: "1000px 0px 1000px 0px" });
  bottomObserver = new IntersectionObserver(onBottomVisible, { rootMargin: "1000px 0px 1000px 0px" });
  topObserver.observe(topSentinel);
  bottomObserver.observe(bottomSentinel);

  centerObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        onActive(entry.target.dataset.panelId);
        break;
      }
    }
  }, { rootMargin: "-40% 0px -55% 0px", threshold: 0 });

  renderStart = 0;
  renderEnd = 0;
  mountRange(0, Math.min(panels.length, CHUNK * 2));
}

// Jumps to any panel by id, re-windowing around it first if it isn't mounted
// - the navigator can point at a panel far outside the current range.
export function jumpToPanel(panelId) {
  const idx = panels.findIndex((panel) => panel.panel_id === panelId);
  if (idx === -1) return;

  if (idx < renderStart || idx >= renderEnd) {
    const half = Math.floor(MAX_RENDERED / 2);
    const newStart = Math.max(0, Math.min(idx - half, panels.length - MAX_RENDERED));
    const newEnd = Math.min(panels.length, Math.max(newStart, 0) + MAX_RENDERED);
    remountRange(Math.max(0, newStart), newEnd);
  }

  const card = listEl.querySelector(`.panel-card[data-panel-id="${CSS.escape(panelId)}"]`);
  if (card) card.scrollIntoView({ block: "start", behavior: "auto" });
}

function mount(index, before) {
  const card = buildCard(panels[index]);
  listEl.insertBefore(card, before);
  centerObserver.observe(card);
  return card;
}

// Appends cards for [start, end) right before the bottom sentinel.
function mountRange(start, end) {
  for (let i = start; i < end; i++) mount(i, bottomSentinel);
  renderStart = start;
  renderEnd = end;
}

// Wipes every mounted card and mounts a fresh [start, end) range - used by
// jumpToPanel when the target isn't anywhere near what's currently mounted,
// where incremental extend/trim wouldn't make sense.
function remountRange(start, end) {
  while (listEl.children.length > 2) {
    const node = listEl.children[1];
    centerObserver.unobserve(node);
    node.remove();
  }
  mountRange(start, end);
}

function onBottomVisible(entries) {
  if (!entries[0].isIntersecting || renderEnd >= panels.length) return;
  const newEnd = Math.min(panels.length, renderEnd + CHUNK);
  for (let i = renderEnd; i < newEnd; i++) mount(i, bottomSentinel);
  renderEnd = newEnd;
  trimTopIfNeeded();
}

function onTopVisible(entries) {
  if (!entries[0].isIntersecting || renderStart <= 0) return;
  const newStart = Math.max(0, renderStart - CHUNK);
  const inserted = [];
  for (let i = renderStart - 1; i >= newStart; i--) inserted.push(mount(i, topSentinel.nextSibling));
  renderStart = newStart;

  // Compensate scroll position: content just appeared ABOVE the viewport,
  // which would otherwise shove everything you are looking at downward by the
  // same amount - so scroll down by exactly what was inserted to keep the
  // same content under the viewport.
  let insertedHeight = 0;
  for (const node of inserted) insertedHeight += node.getBoundingClientRect().height;
  if (insertedHeight > 0) window.scrollBy(0, insertedHeight);

  trimBottomIfNeeded();
}

// Removes the oldest (topmost) mounted cards once the window has grown past
// MAX_RENDERED via bottom-extension - those cards are above the viewport (you
// just scrolled down to trigger this), so removing them shifts everything
// below UP; compensate by scrolling up the same amount.
function trimTopIfNeeded() {
  const overflow = (renderEnd - renderStart) - MAX_RENDERED;
  if (overflow <= 0) return;
  let removedHeight = 0;
  for (let i = 0; i < overflow; i++) {
    const node = listEl.children[1]; // first card after topSentinel
    removedHeight += node.getBoundingClientRect().height;
    centerObserver.unobserve(node);
    node.remove();
  }
  renderStart += overflow;
  if (removedHeight > 0) window.scrollBy(0, -removedHeight);
}

// Removes the newest (bottommost) mounted cards once the window has grown
// past MAX_RENDERED via top-extension - those cards are below the viewport, so
// removing them doesn't move anything visible; no compensation needed.
function trimBottomIfNeeded() {
  const overflow = (renderEnd - renderStart) - MAX_RENDERED;
  if (overflow <= 0) return;
  for (let i = 0; i < overflow; i++) {
    const node = listEl.children[listEl.children.length - 2]; // last card before bottomSentinel
    centerObserver.unobserve(node);
    node.remove();
  }
  renderEnd -= overflow;
}
