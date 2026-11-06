"""The whole workflow, one module per step and one function per thing it does:

    brief      a few words -> an LLM -> a manga, its chapters and a new Drama 3 voice
    projects   making a project from a MangaDex link; the manga's own facts
    chapters   what a project has, what MangaDex lists, where each chapter is
    download   fetching a chapter's pages
    narration  the two browser passes: writing it by hand, reviewing an LLM's
    panels     marking the panels (the web UI) and cutting them out
    crop_pdf   the crop PDF for an LLM: the pages with the machine's boxes
    crop_reply its pasted reply made the panel marks, the panels cut
    pdf        the panels as PDF parts for the LLM, and the hand-off
    video      the pasted narration -> clips -> mix -> render; or a new mix
               and render from the clips already there
    long_video one video of several chapters, joined or made from source
    voices     one line in every voice the engine has, to listen to
    cleanup    resetting or deleting a chapter
    upload     the project's one title, description and thumbnail, stamped
               for each video
    upload_pdf the upload PDF for an LLM: the images it may make thumbnails of
    upload_reply its pasted reply made the titles, thumbnails and description

Everything is re-exported here, so `workflow.make_pdf(...)` reads the same
from the command line (cli.py) and the menus (remanga/ui/) - which is the
point: the two front-ends cannot do a step differently."""

from remanga.narration import page_files, panel_files
from remanga.workflow.brief import apply_brief, make_brief_prompt, print_brief_result, read_reply_text
from remanga.workflow.chapters import (
    chapter_state,
    crop_reply_state,
    has_audio,
    has_marks,
    has_panels,
    local_chapters,
    mangadex_chapters,
    page_check,
    select_chapters,
    source_names,
)
from remanga.workflow.cleanup import (
    delete_project,
    drop_audio_and_video,
    drop_derived,
    drop_mix_and_video,
    project_footprint,
    reset_chapter,
)
from remanga.workflow.crop_pdf import CropPdfResult, crop_reply_path, has_crop_reply, make_crop_pdf, print_crop_handoff
from remanga.workflow.crop_reply import CropReplyResult, marks_from_reply, print_reply_result
from remanga.workflow.deletables import deletable_items, delete_items
from remanga.workflow.download import download, print_chapter_list
from remanga.workflow.long_video import (
    delete_long_video,
    join_chapters,
    long_label,
    long_videos,
    make_long_video,
    prepare_chapter,
)
from remanga.workflow.narration import review_narration, write_narration
from remanga.workflow.panel_marks import marks_from_panels
from remanga.workflow.panels import cut_panels, mark, remark
from remanga.workflow.pdf import PdfResult, make_pdf, print_handoff
from remanga.workflow.projects import (
    READING_DIRECTION_BY_LANGUAGE,
    create_project,
    project_name_from_title,
    settle_reading_direction,
)
from remanga.workflow.upload import stamp_all
from remanga.workflow.upload_pdf import UploadPdfResult, has_upload_reply, make_upload_pdf, print_upload_handoff
from remanga.workflow.upload_reply import UploadReplyResult, print_upload_result, upload_from_reply
from remanga.workflow.video import (
    check_chapter,
    check_narration,
    make_video,
    mix,
    narrate,
    quality_warnings,
    remake_from_source,
    remix_video,
    render,
)
from remanga.workflow.voices import SAMPLE_TEXT, sample_voices, samples_dir

# page_files/panel_files are re-exported with the steps on purpose: a screen
# asking "does this chapter have pages" should not have to know which module
# holds that.

__all__ = [
    "READING_DIRECTION_BY_LANGUAGE",
    "SAMPLE_TEXT",
    "CropPdfResult",
    "CropReplyResult",
    "PdfResult",
    "UploadPdfResult",
    "UploadReplyResult",
    "chapter_state",
    "check_chapter",
    "check_narration",
    "create_project",
    "crop_reply_path",
    "crop_reply_state",
    "cut_panels",
    "deletable_items",
    "delete_items",
    "delete_long_video",
    "delete_project",
    "download",
    "drop_audio_and_video",
    "drop_derived",
    "drop_mix_and_video",
    "has_audio",
    "has_crop_reply",
    "has_marks",
    "has_panels",
    "has_upload_reply",
    "join_chapters",
    "local_chapters",
    "long_label",
    "long_videos",
    "make_crop_pdf",
    "make_long_video",
    "make_pdf",
    "make_upload_pdf",
    "make_video",
    "mangadex_chapters",
    "mark",
    "marks_from_panels",
    "marks_from_reply",
    "mix",
    "narrate",
    "page_check",
    "page_files",
    "panel_files",
    "prepare_chapter",
    "print_chapter_list",
    "print_crop_handoff",
    "print_handoff",
    "print_reply_result",
    "print_upload_handoff",
    "print_upload_result",
    "project_footprint",
    "project_name_from_title",
    "quality_warnings",
    "remake_from_source",
    "remark",
    "remix_video",
    "render",
    "reset_chapter",
    "review_narration",
    "sample_voices",
    "samples_dir",
    "select_chapters",
    "settle_reading_direction",
    "source_names",
    "stamp_all",
    "upload_from_reply",
    "write_narration",
]
