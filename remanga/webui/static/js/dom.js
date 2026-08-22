// Central place for every DOM element reference the app touches, plus the
// one-time platform-label setup (Ctrl vs ⌘ in the save-shortcut hints).
// Every other module imports its elements from here instead of re-querying
// the document, so there's exactly one source of truth for ids.

export const isMac = navigator.platform.toUpperCase().includes("MAC");
document.querySelectorAll("#saveKbd, #hintSaveKbd").forEach(el => el.textContent = isMac ? "⌘S" : "Ctrl+S");

export const stage = document.getElementById("stage");
export const canvasWrap = document.getElementById("canvasWrap");
export const pageImg = document.getElementById("pageImg");
export const panelList = document.getElementById("panelList");
export const panelCount = document.getElementById("panelCount");
export const pageNumEl = document.getElementById("pageNum");
export const pageTotalEl = document.getElementById("pageTotal");
export const storyBadge = document.getElementById("storyBadge");
export const zoomLabel = document.getElementById("zoomLabel");
export const assistCard = document.getElementById("assistCard");
export const assistBtn = document.getElementById("assistBtn");
export const assistProgressBar = document.getElementById("assistProgressBar");
export const assistStatus = document.getElementById("assistStatus");
export const saveOverlay = document.getElementById("saveOverlay");
export const saveBtn = document.getElementById("saveBtn");
export const toolDrawBtn = document.getElementById("toolDraw");
export const toolSelectBtn = document.getElementById("toolSelect");
export const zoomInBtn = document.getElementById("zoomIn");
export const zoomOutBtn = document.getElementById("zoomOut");
export const prevPageBtn = document.getElementById("prevPage");
export const nextPageBtn = document.getElementById("nextPage");
