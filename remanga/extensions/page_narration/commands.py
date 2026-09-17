"""The page narration commands - narrating whole pages instead of cropped
panels."""

from __future__ import annotations

from remanga.commands.setup_rows import section_setup
from remanga.commands.spec import Command, Param, chapter_param, chapters_param, project_param
from remanga.extensions.page_narration import handlers

PAGE_SETUP = (section_setup("page_narration", "which pages uploads are built, and their size cap"),)


def _reply_pasted(session, values) -> bool:
    from remanga.extensions.page_narration.paths import get_reply_path
    from remanga.json_io import has_real_json_content

    return values.get("chapter") is not None and has_real_json_content(
        get_reply_path(session.project, values["chapter"]))


def _formats_param(prompt: str, *, skip_when_replied: bool = False) -> Param:
    from remanga.extensions.page_narration.settings import PAGE_FORMATS

    return PAGE_FORMATS.param(prompt, skip=_reply_pasted if skip_when_replied else None, step="page-narration")


PAGE_UPLOAD = Command(
    "page-upload",
    "Build this chapter's pages upload for page mode - the downloaded pages, unchanged, as whichever PDF "
    "formats you pick, each carrying the chapter's identity - and create the empty page_narration.json the "
    "LLM's reply is pasted into",
    handlers.page_upload,
    [project_param(), chapter_param(), _formats_param("What to build for the LLM")],
    category="Package for the LLM",
    short="Page mode: build one chapter's pages PDF, no cropping",
    detail="upload it with prompts/page_narration.md and prompts/narration.md, paste the reply into "
           "page_narration.json, then run page-narration",
    setup=PAGE_SETUP,
)

PAGE_NARRATION = Command(
    "page-narration",
    "Page mode: narrate whole pages instead of cropped panels - builds the pages upload if needed, waits for "
    "the LLM's reply pasted into page_narration.json, checks it (writing a fix request when something is "
    "wrong), and turns it into panels/ (one image per story page) and narration.json (one entry per page), "
    "ready for tts, mix and render",
    handlers.page_narration,
    [
        project_param(), chapter_param(),
        _formats_param("What to build for the LLM, if the upload isn't built yet", skip_when_replied=True),
        # cli_only: the import asks itself, naming what the chapter really has.
        Param("force", ["--force", "-f"], type="bool", default=False, cli_only=True,
              help="Replace existing panels and narration.json with the page narration, without asking",
              prompt="Replace existing panels and narration without asking?"),
    ],
    category="Narration",
    short="Page mode: import one chapter's page-by-page narration",
    detail="each page is shown whole in the video, narrated panel by panel in one entry",
    setup=PAGE_SETUP,
)

PAGE_UPLOAD_ALL = Command(
    "page-upload-all",
    "Build the page mode pages upload for every downloaded chapter at once. Chapters with no pages yet are "
    "skipped and named",
    handlers.page_upload_all,
    [
        project_param(),
        chapters_param("build pages uploads for", "Chapters with no downloaded pages are skipped."),
        _formats_param("What to build for the LLM, for every chapter"),
    ],
    category="Package for the LLM",
    short="Page mode: build the pages PDF for every chapter",
    family="page-upload",
    setup=PAGE_SETUP,
)
