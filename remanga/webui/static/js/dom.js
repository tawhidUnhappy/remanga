// Central place for every DOM element reference the app touches, plus the
// one-time platform-label setup (Ctrl vs ⌘ in the save-shortcut hints).
// Every other module imports its elements from here instead of re-querying
// the document, so there's exactly one source of truth for ids.

export const isMac = navigator.platform.toUpperCase().includes("MAC");
// Instant default before shortcuts.js's async fetch resolves and (in
// updateHints()) overwrites these with whatever's actually bound, in case
// the user has rebound Save away from the default.
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
export const scopeSelect = document.getElementById("scopeSelect");
export const assistRange = document.getElementById("assistRange");
export const rangeFrom = document.getElementById("rangeFrom");
export const rangeTo = document.getElementById("rangeTo");
export const autoAllToggle = document.getElementById("autoAllToggle");
export const autoSaveToggle = document.getElementById("autoSaveToggle");
export const autoOrderToggle = document.getElementById("autoOrderToggle");
export const reorderBtn = document.getElementById("reorderBtn");
export const relabelBtn = document.getElementById("relabelBtn");
export const saveOverlay = document.getElementById("saveOverlay");
export const saveOverlayTitle = document.getElementById("saveOverlayTitle");
export const saveOverlayText = document.getElementById("saveOverlayText");
export const saveBtn = document.getElementById("saveBtn");
export const saveLabel = document.getElementById("saveLabel");
export const finishBtn = document.getElementById("finishBtn");
export const saveKbd = document.getElementById("saveKbd");
export const hintSaveKbd = document.getElementById("hintSaveKbd");
export const toolDrawBtn = document.getElementById("toolDraw");
export const toolAdjustBtn = document.getElementById("toolAdjust");
export const zoomInBtn = document.getElementById("zoomIn");
export const zoomOutBtn = document.getElementById("zoomOut");
export const prevPageBtn = document.getElementById("prevPage");
export const nextPageBtn = document.getElementById("nextPage");
export const chapterNav = document.getElementById("chapterNav");
export const chapterName = document.getElementById("chapterName");
export const chapterPos = document.getElementById("chapterPos");
export const prevChapterBtn = document.getElementById("prevChapter");
export const nextChapterBtn = document.getElementById("nextChapter");

export const toolbar = document.getElementById("toolbar");
export const viewBadge = document.getElementById("viewBadge");
export const hintToast = document.getElementById("hintToast");
export const sidebarFooter = document.getElementById("sidebarFooter");
export const tabPageBtn = document.getElementById("tabPage");
export const tabSessionBtn = document.getElementById("tabSession");
export const panePage = document.getElementById("panePage");
export const paneSession = document.getElementById("paneSession");
export const outlineTree = document.getElementById("outlineTree");
export const outlineSummary = document.getElementById("outlineSummary");

export const shortcutsBtn = document.getElementById("shortcutsBtn");
export const shortcutsOverlay = document.getElementById("shortcutsOverlay");
export const shortcutsList = document.getElementById("shortcutsList");
export const shortcutsCloseBtn = document.getElementById("shortcutsCloseBtn");
export const shortcutsCancelBtn = document.getElementById("shortcutsCancelBtn");
export const shortcutsResetBtn = document.getElementById("shortcutsResetBtn");
export const shortcutsSaveBtn = document.getElementById("shortcutsSaveBtn");
