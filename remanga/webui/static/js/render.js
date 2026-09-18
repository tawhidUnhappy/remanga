// Everything that paints the current page's marks: the boxes on the canvas
// stage and their mirror list in the sidebar.

import { stage, panelList, panelCount, storyBadge, orderHint } from "./dom.js";
import { state } from "./state.js";
import { deleteMark, markDirty } from "./marks.js";
import { onMarkMouseDown } from "./drag-resize.js";

export function render() {
  stage.querySelectorAll(".mark, .guide-line").forEach(el => el.remove());

  state.marks.forEach((m, i) => {
    const el = document.createElement("div");
    el.className = "mark" + (m.src === "ai" ? " ai" : "") + (m.id === state.selectedId ? " selected" : "");
    el.dataset.markId = m.id;
    Object.assign(el.style, {
      left: (m.x * state.scale) + "px", top: (m.y * state.scale) + "px",
      width: (m.w * state.scale) + "px", height: (m.h * state.scale) + "px",
    });

    const tag = document.createElement("div");
    tag.className = "tag";
    tag.textContent = "Panel " + (i + 1);
    el.appendChild(tag);

    if (m.id === state.selectedId && !state.readOnly) {
      ["nw", "n", "ne", "w", "e", "sw", "s", "se"].forEach(pos => {
        const h = document.createElement("div");
        h.className = "handle " + pos;
        el.appendChild(h);
      });
    }
    if (m.id === state.selectedId) {
      const dim = document.createElement("div");
      dim.className = "dim-readout";
      dim.textContent = Math.round(m.w) + " × " + Math.round(m.h) + " px";
      el.appendChild(dim);
    }

    el.addEventListener("mousedown", (e) => onMarkMouseDown(e, m));
    el.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      deleteMark(m.id);   // itself a no-op in a read-only session
    });

    stage.appendChild(el);
  });

  renderList();
  updateStoryBadge();
}

function updateStoryBadge() {
  const n = state.marks.length;
  storyBadge.textContent = n ? `${n} panel${n === 1 ? "" : "s"}` : "no panels";
  storyBadge.classList.toggle("story", n > 0);
}

function renderList() {
  panelCount.textContent = state.marks.length;
  orderHint.innerHTML = state.autoOrder
    ? "Auto-order is on — panels stay in reading order. Turn it off to order them yourself."
    : "Drag <b>⠿</b> to reorder — this sets narration order.";
  if (!state.marks.length) {
    panelList.innerHTML = state.readOnly
      ? `<div class="empty-list">No panels marked on this page.</div>`
      : `<div class="empty-list">No panels marked on this page yet.<br>Drag on the canvas to add one, or press <b>Detect</b>.</div>`;
    return;
  }
  panelList.innerHTML = "";
  state.marks.forEach((m, i) => {
    const row = document.createElement("div");
    row.className = "panel-row" + (m.id === state.selectedId ? " selected" : "") + (m.src === "ai" ? " is-ai" : "");
    // Reordering IS an edit - it's what sets narration order - so a viewer
    // neither drags nor shows a grip to drag by.
    // With auto-order on, a dragged order would be re-sorted on the very next
    // save, so the handle isn't offered: the switch decides the order, and
    // turning it off is how you get the handle back.
    row.draggable = !state.readOnly && !state.autoOrder;
    row.dataset.index = i;
    row.innerHTML = `
      ${state.readOnly || state.autoOrder ? "" : `<span class="grip">⠿</span>`}
      <span class="order-badge">${i + 1}</span>
      <span class="panel-row-main">
        <span class="panel-row-title">Panel ${i + 1}
          <span class="src-chip ${m.src === "ai" ? "ai" : ""}">${m.src === "ai" ? "AI" : "MANUAL"}</span>
        </span>
        <span class="panel-row-sub">${Math.round(m.w)}×${Math.round(m.h)} px</span>
      </span>
      ${state.readOnly ? "" : `<button class="row-del" title="Delete">✕</button>`}
    `;
    row.addEventListener("click", (e) => {
      if (e.target.closest(".row-del")) { deleteMark(m.id); return; }
      state.selectedId = m.id;
      render();
    });
    row.addEventListener("dragstart", (e) => {
      row.classList.add("dragging");
      e.dataTransfer.setData("text/plain", String(i));
    });
    row.addEventListener("dragend", () => row.classList.remove("dragging"));
    row.addEventListener("dragover", (e) => e.preventDefault());
    row.addEventListener("drop", (e) => {
      e.preventDefault();
      const from = parseInt(e.dataTransfer.getData("text/plain"), 10);
      const to = i;
      if (from === to) return;
      const [moved] = state.marks.splice(from, 1);
      state.marks.splice(to, 0, moved);
      markDirty();
      render();
    });
    panelList.appendChild(row);
  });
}
