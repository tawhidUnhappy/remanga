// The side panel: the gutter colours that verified, and every panel - its rows,
// and flags for what deserves a look: a tall panel (no calm place to split
// it), an overlap, sides dragged in. A click selects the panel and scrolls to it.

import { state, select } from "./state.js";
import { colorOf } from "./overlay.js";

const runWidth = (row) => (state.runs.find(r => row < r.top + r.height) || state.runs[0]).width;
import { draw, scrollToRow } from "./viewport.js";

const list = document.getElementById("panelList"), colors = document.getElementById("gutterColors");

export function renderColors() {
  colors.replaceChildren(...state.chapter.colors.map(c => {
    const el = document.createElement("span");
    el.className = `swatch ${c.strength}`;
    el.title = `rgb(${c.color.join(", ")}) - ${c.count} ${c.strength} gutter(s)`;
    el.innerHTML = `<i style="background: rgb(${c.color.join(",")})"></i><b class="mono">${c.count}</b>`;
    return el;
  }));
}

function flags(m, i) {
  const out = [];
  if (m.bottom - m.top > 1.8 * runWidth(m.top)) out.push(["tall", "tall - no calm place to split it; check it"]);
  const prev = state.marks[i - 1], next = state.marks[i + 1];
  if ((prev && prev.bottom > m.top) || (next && next.top < m.bottom)) out.push(["overlap", "overlaps a neighbour"]);
  if (m.left > 0 || m.right < 1) out.push(["sides", "narrower than the strip"]);
  return out;
}

export function renderList() {
  document.getElementById("count").textContent = state.marks.length;
  list.replaceChildren(...state.marks.map((m, i) => {
    const row = document.createElement("button");
    row.className = "panel-row" + (m.id === state.selected ? " selected" : "");
    row.style.setProperty("--c", colorOf(i));
    row.innerHTML = `<span class="num mono">${i + 1}</span><span class="rows mono">${m.top}–${m.bottom}</span>`
      + `<span class="height mono">${m.bottom - m.top}</span>`
      + flags(m, i).map(([cls, title]) => `<span class="flag ${cls}" title="${title}"></span>`).join("");
    row.addEventListener("click", () => {
      select(m.id);
      scrollToRow(m.top);
    });
    return row;
  }));
  list.querySelector(".selected")?.scrollIntoView({ block: "nearest" });
}
