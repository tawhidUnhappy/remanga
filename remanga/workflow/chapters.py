"""Which chapters a project has, which MangaDex lists, and where each one is
in the workflow."""

from __future__ import annotations

from remanga.chapters import chapter_sort_key, discover_chapters, expand_chapter_selection
from remanga.config import RemangaConfig
from remanga.json_io import has_real_json_content
from remanga.narration import page_files, panel_files
from remanga.paths import (
    get_audio_timing_path,
    get_crops_path,
    get_final_video_path,
    get_narration_path,
    get_pdf_dir,
)


def local_chapters(project: str) -> list[str]:
    return discover_chapters(project)


def mangadex_chapters(project: str, config: RemangaConfig, url: str | None = None,
                      refresh: bool | None = None) -> list[dict]:
    """Every chapter the project's sources list (MangaDex, comix.to, ...),
    each with its local status (downloaded / partial / missing) and the
    source it comes from. `refresh` None = as each source does on opening a
    list (MangaDex asked again, a site read through Firefox shown as saved),
    True = ask every source now - see remanga.sources.chapter_listing."""
    from remanga.sources import chapter_listing

    return chapter_listing(project, config, refresh=refresh, url=url)


def source_names(project: str) -> list[str]:
    """The display names of the project's sources, in order of preference."""
    from remanga.sources import project_sources

    return [source.display_name for source, _ in project_sources(project)]


def select_chapters(raw: str, available: list[str]) -> list[str]:
    """'1', '1-5', '1-5,8', or 'all', against the chapters available."""
    text = (raw or "").strip()
    if not text or text.lower() == "all":
        return sorted(available, key=chapter_sort_key)
    return expand_chapter_selection(text, available)


def chapter_state(project: str, chapter: str) -> str:
    """Where a chapter is, in words: the next thing it needs."""
    if not page_files(project, chapter):
        return "not downloaded"
    if get_final_video_path(project, chapter, create=False).exists():
        return "video done"
    if has_real_json_content(get_narration_path(project, chapter)):
        return "narration pasted - make the video"
    if any(get_pdf_dir(project, chapter, create=False).glob("panels_*.pdf")):
        return "PDF ready - waiting for the narration"
    if panel_files(project, chapter):
        return "panels cut - make the PDF"
    if has_marks(project, chapter):
        return "panels marked - create the panels"
    return "downloaded - mark the panels"


def has_audio(project: str, chapter: str) -> bool:
    """Whether this chapter has been narrated before - what makes remaking the
    video a thing to offer at all."""
    return get_audio_timing_path(project, chapter, create=False).exists()


def has_marks(project: str, chapter: str) -> bool:
    """Whether this chapter's panels have been marked: crops.json saved, or a
    long strip's strip_marks.json (crops.json follows it at Create panels)."""
    return (has_real_json_content(get_crops_path(project, chapter))
            or has_real_json_content(get_crops_path(project, chapter).with_name("strip_marks.json")))


def has_panels(project: str, chapter: str) -> bool:
    return bool(panel_files(project, chapter))


def page_check(project: str, chapter: str) -> dict:
    """How a downloaded chapter's pages were checked, from its download record:
    {"mark": "✓" (all checked) / "?" (the pages on disk aren't the checked
    download) / "" (nothing downloaded), "count": pages on disk, "lines": what
    was checked, in words}."""
    from remanga.paths import read_manifest

    files = page_files(project, chapter)
    if not files:
        return {"mark": "", "count": 0, "lines": []}
    record = read_manifest(project).get("chapters", {}).get(str(chapter), {}).get("pages") or {}
    if not record.get("verified") or record.get("total_pages") != len(files):
        return {"mark": "?", "count": len(files), "lines": [
            f"{len(files)} pages on disk, but not as one checked download - Check pages fetches whatever is "
            "missing or broken and checks them all."]}
    if record.get("checks"):
        lines = [("✓ " if c["ok"] else "· ") + c["says"] for c in record["checks"]]
    elif record.get("source") in (None, "", "mangadex"):
        lines = [f"✓ {len(files)} pages, every one byte for byte the file MangaDex names after its SHA-256 checksum"]
    else:
        lines = [f"✓ {len(files)} pages, numbered 1-{len(files)}, every one a whole image, as many as the "
                 "reader numbered", "· downloaded before the fuller check (the site's own list, the page bar, "
                 "page sizes) - Re-download gives it one"]
    return {"mark": "✓", "count": len(files), "lines": lines}
