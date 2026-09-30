// Loads the chapter and wires the Strip Marker together.

import { state } from "./state.js";
import { getJson } from "./api.js";
import { canRedo, canUndo, commit, onChange, redo, undo } from "./history.js";
import { draw, relayout } from "./viewport.js";
import { renderColors, renderList } from "./sidebar.js";
import { status } from "./status.js";
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
  status("Finding the panels...");
  const data = await getJson("/api/strip");
  state.chapter = data;
  state.runs = data.runs.map(r => ({ ...r }));
  state.totalHeight = data.total_height;
  state.marks = fromRows(data.panels);
  $("where").textContent = `${data.title} · chapter ${data.chapter}`;
  document.title = `remanga - Strip Marker - chapter ${data.chapter}`;
  renderColors();
  relayout();
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

load().catch(e => status("Couldn't load the chapter: " + e.message));
