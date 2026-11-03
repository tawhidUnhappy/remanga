// Loads the chapter and wires the Strip Marker together.

import { state } from "./state.js";
import { getJson } from "./api.js";
import { canRedo, canUndo, commit, onChange, redo, undo } from "./history.js";
import { draw, relayout } from "./viewport.js";
import { renderColors, renderList } from "./sidebar.js";
import { status } from "./status.js";
import { hideLoading, showLoading } from "/shared/js/screens.js";
import { autoMarks, finish, fromRows } from "./actions.js";
import "./gestures.js";
import "./keys.js";
import { renderSelbar } from "./selbar.js";
import { setMode } from "./gestures.js";

const $ = (id) => document.getElementById(id);

function refresh() {
  renderSelbar();
  $("undoBtn").disabled = !canUndo();
  $("redoBtn").disabled = !canRedo();
  renderList();
  draw();
}

async function load() {
  showLoading("Opening the chapter", "reading the downloaded images");
  const layout = await getJson("/api/layout");
  state.runs = layout.runs.map(r => ({ ...r }));
  state.totalHeight = layout.total_height;
  $("where").textContent = `${layout.title} · chapter ${layout.chapter}`;
  document.title = `remanga - Strip Marker - chapter ${layout.chapter}`;
  relayout();   // the strip is on screen behind the loading card from here on
  showLoading("Finding the panels", "gutters, borders and calm stretches - a few seconds for a long chapter");
  const data = await getJson("/api/strip");
  hideLoading();
  state.chapter = data;
  state.marks = fromRows(data.panels);
  renderColors();
  refresh();
  const weak = data.gutters.filter(g => g.strength === "local").length;
  status((data.proposed ? "Proposed from the gutters - scroll through and fix what is wrong." : "Your saved marks.")
    + (data.tall.length ? ` ${data.tall.length} tall panel(s) had no calm place to split - flagged in the list.` : "")
    + (weak ? ` ${weak} gutter(s) verified only locally (amber).` : ""));
}

onChange(refresh);
document.addEventListener("strip:select", () => { renderSelbar(); renderList(); draw(); });
$("undoBtn").addEventListener("click", () => undo());
$("redoBtn").addEventListener("click", () => redo());
$("autoBtn").addEventListener("click", autoMarks);
$("clearBtn").addEventListener("click", () => { commit([]); status("Cleared - Ctrl+Z brings them back."); });
$("finishBtn").addEventListener("click", finish);
$("newBtn").addEventListener("click", () => setMode(state.mode === "new" ? "select" : "new"));
$("gutterToggle").addEventListener("change", (e) => { state.showGutters = e.target.checked; draw(); });
document.addEventListener("dragstart", (e) => e.preventDefault());

load().catch(e => { hideLoading(); status("Couldn't load the chapter: " + e.message); });
