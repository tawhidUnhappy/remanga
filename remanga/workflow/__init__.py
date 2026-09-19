"""The whole workflow, one module per step and one function per thing it does:

    projects   making a project from a MangaDex link; the manga's own facts
    chapters   what a project has, what MangaDex lists, where each chapter is
    download   fetching a chapter's pages
    narration  the two browser passes: writing it by hand, reviewing an LLM's
    panels     marking the panels (the web UI) and cutting them out
    pdf        the panels as PDF parts for the LLM, and the hand-off
    video      the pasted narration -> clips -> mix -> render
    voices     one line in every voice the engine has, to listen to
    cleanup    resetting or deleting a chapter

Everything is re-exported here, so `workflow.make_pdf(...)` reads the same
from the command line (cli.py) and the menus (remanga/ui/) - which is the
point: the two front-ends cannot do a step differently."""

from remanga.narration import page_files, panel_files
from remanga.workflow.chapters import (
    chapter_state,
    has_audio,
    has_marks,
    has_panels,
    local_chapters,
    mangadex_chapters,
    select_chapters,
)
from remanga.workflow.cleanup import drop_mix_and_video, reset_chapter
from remanga.workflow.download import download, print_chapter_list
from remanga.workflow.narration import review_narration, write_narration
from remanga.workflow.panels import cut_panels, mark
from remanga.workflow.pdf import PdfResult, make_pdf, print_handoff
from remanga.workflow.projects import (
    READING_DIRECTION_BY_LANGUAGE,
    create_project,
    project_name_from_title,
    settle_reading_direction,
)
from remanga.workflow.video import (
    check_narration,
    make_video,
    mix,
    narrate,
    quality_warnings,
    render,
)
from remanga.workflow.voices import SAMPLE_TEXT, sample_voices, samples_dir

# page_files/panel_files are re-exported with the steps on purpose: a screen
# asking "does this chapter have pages" should not have to know which module
# holds that.

__all__ = [
    "READING_DIRECTION_BY_LANGUAGE",
    "SAMPLE_TEXT",
    "PdfResult",
    "chapter_state",
    "check_narration",
    "create_project",
    "cut_panels",
    "download",
    "drop_mix_and_video",
    "has_audio",
    "has_marks",
    "has_panels",
    "local_chapters",
    "make_pdf",
    "make_video",
    "mangadex_chapters",
    "mark",
    "mix",
    "narrate",
    "page_files",
    "panel_files",
    "print_chapter_list",
    "print_handoff",
    "project_name_from_title",
    "quality_warnings",
    "render",
    "reset_chapter",
    "review_narration",
    "sample_voices",
    "samples_dir",
    "select_chapters",
    "settle_reading_direction",
    "write_narration",
]
