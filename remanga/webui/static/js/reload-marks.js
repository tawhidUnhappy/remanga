// Re-reads the chapter's marks from the server, for the places that change
// them behind the tab's back (a reorder, auto-order being switched on).
//
// The import is dynamic on purpose: chapter-nav.js imports the action bar for
// its poll and its sync, so importing chapter-nav back at module level would
// be a cycle. Nothing here runs at load time, so deferring it costs nothing.

export async function reloadMarks() {
  const { reloadChapterMarks } = await import("./chapter-nav.js");
  await reloadChapterMarks();
}
