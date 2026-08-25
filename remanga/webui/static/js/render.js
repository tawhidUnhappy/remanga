// Everything that paints the current page's marks: the boxes on the canvas
// stage and their mirror list in the sidebar.

import { stage, panelList, panelCount, storyBadge } from "./dom.js";
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

    if (m.id === state.selectedId) {
      ["nw", "n", "ne", "w", "e", "sw", "s", "se"].forEach(pos => {
        const h = document.createElement("div");
        h.className = "handle " + pos;
        el.appendChild(h);
      });
      const dim = document.createElement("div");
      dim.className = "dim-readout";
      dim.textContent = Math.round(m.w) + " × " + Math.round(m.h) + " px";
      el.appendChild(dim);
    }

    el.addEventListener("mousedown", (e) => onMarkMouseDown(e, m));
    el.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      deleteMark(m.id);
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
  if (!state.marks.length) {
    panelList.innerHTML = `<div class="empty-list">No panels marked on this page yet.<br>Drag on the canvas to add one, or wait for MAGI v3.</div>`;
    return;
  }
  panelList.innerHTML = "";
  state.marks.forEach((m, i) => {
    const row = document.createElement("div");
    row.className = "panel-row" + (m.id === state.selectedId ? " selected" : "") + (m.src === "ai" ? " is-ai" : "");
    row.draggable = true;
    row.dataset.index = i;
    row.innerHTML = `
      <span class="grip">⠿</span>
      <span class="order-badge">${i + 1}</span>
      <span class="panel-row-main">
        <span class="panel-row-title">Panel ${i + 1}
          <span class="src-chip ${m.src === "ai" ? "ai" : ""}">${m.src === "ai" ? "AI" : "MANUAL"}</span>
        </span>
        <span class="panel-row-sub">${Math.round(m.w)}×${Math.round(m.h)} px</span>
      </span>
      <button class="row-del" title="Delete">✕</button>
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
