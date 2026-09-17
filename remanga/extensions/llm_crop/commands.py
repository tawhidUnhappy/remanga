"""The LLM crop commands - cropping with Gemini instead of the Panel Marker.
Placed next to the marker's commands by the manifest (extension.py)."""

from __future__ import annotations

from remanga.commands.setup_rows import section_setup
from remanga.commands.spec import Command, Param, chapter_param, chapters_param, project_param
from remanga.extensions.llm_crop import handlers

# Both the workflow's own settings and the cleanup passes the cut runs belong
# next to the commands that build what Gemini sees and cut what it sends back.
LLM_CROP_SETUP = (
    section_setup("llm_crop", "what the grid uploads are, how readily Gemini groups panels, and paint-out"),
    section_setup("detection", "which cleanup passes run when Gemini's crops are cut"),
)


def _replace_marks_param() -> Param:
    # cli_only: the handler asks this itself, naming the chapters that really
    # hold Panel Marker marks - asked up front it would be a question about
    # marks nobody knows exist yet.
    return Param("force", ["--force", "-f"], type="bool", default=False, cli_only=True,
                 help="Replace crops.json even where it holds marks from the Panel Marker, without asking",
                 prompt="Replace Panel Marker marks without asking?")


def _reply_pasted(session, values) -> bool:
    # llm-crop only builds the grid when the reply isn't pasted yet; with a
    # reply waiting to import, which uploads to build is no question.
    from remanga.extensions.llm_crop.paths import get_llm_crops_path
    from remanga.json_io import has_real_json_content

    return values.get("chapter") is not None and has_real_json_content(
        get_llm_crops_path(session.project, values["chapter"]))


def _formats_param(prompt: str, *, skip_when_replied: bool = False) -> Param:
    """Which grid uploads to build - a checklist in the wizard, a
    comma-separated list on the CLI, saved to the project either way."""
    from remanga.extensions.llm_crop.settings import GRID_FORMATS

    return GRID_FORMATS.param(prompt, skip=_reply_pasted if skip_when_replied else None, step="llm-crop")


CROP_GRID = Command(
    "crop-grid",
    "Build this chapter's upload for cropping with Gemini - every page on a square black canvas "
    "under a green 0-1000 ruler grid, as whichever of a folder, a zip, a split zip or a PDF you pick, "
    "carrying the chapter_info.json the prompt reads - and create the empty llm_crops.json its reply is "
    "pasted into",
    handlers.crop_grid,
    [project_param(), chapter_param(), _formats_param("What to build for Gemini")],
    category="Crop panels",
    short="Build one chapter's grid upload for Gemini to crop",
    detail="upload it with prompts/llm_crop.md, paste the reply into llm_crops.json, then run llm-crop",
    setup=LLM_CROP_SETUP,
)

LLM_CROP = Command(
    "llm-crop",
    "Crop with Gemini instead of the Panel Marker - builds the grid upload if needed, waits for the "
    "reply pasted into llm_crops.json, checks it (writing a fix request to send back when something "
    "is wrong) and turns it into crops.json, with preview images to check by eye",
    handlers.llm_crop,
    [project_param(), chapter_param(),
     _formats_param("What to build for Gemini, if the grid isn't built yet", skip_when_replied=True),
     _replace_marks_param()],
    category="Crop panels",
    short="Import Gemini's crops for one chapter (builds the grid if needed)",
    detail="bubbles kept whole with their panel, groups of panels, neighbours painted out",
    setup=LLM_CROP_SETUP,
)

CROP_GRID_ALL = Command(
    "crop-grid-all",
    "Build the Gemini crop upload for every downloaded chapter at once - the same grid formats as "
    "`crop-grid`, run over the whole manga. Chapters with no pages yet are skipped and named",
    handlers.crop_grid_all,
    [
        project_param(),
        chapters_param("build crop grids for", "Chapters with no downloaded pages are skipped."),
        _formats_param("What to build for Gemini, for every chapter"),
    ],
    category="Crop panels",
    short="Build the Gemini grid upload for every chapter",
    detail="every chapter's upload ready to send to Gemini in one go",
    setup=LLM_CROP_SETUP,
)

LLM_CROP_ALL = Command(
    "llm-crop-all",
    "Import Gemini's crops for every chapter whose llm_crops.json has a reply pasted in - checked "
    "the same way as `llm-crop`, with a fix request written for any reply that doesn't pass. "
    "Chapters still waiting for a reply are named and left alone",
    handlers.llm_crop_all,
    [
        project_param(),
        chapters_param("import Gemini's crops for", "Chapters whose llm_crops.json is still empty are skipped."),
        _replace_marks_param(),
    ],
    category="Crop panels",
    short="Import Gemini's crops for every chapter with a reply pasted in",
    detail="the whole-project form of llm-crop - no waiting, just whatever has been pasted",
    setup=LLM_CROP_SETUP,
)


def _ask_chapter_range(param, session, values):
    from remanga.tui import CANCEL, ask_text

    answer = ask_text("Chapters to take to video", default="", allow_empty=True,
                      note="a range like 1-5, commas for more (1-5,8) - chapters not downloaded yet are "
                           "downloaded · leave empty for every chapter this project has")
    return CANCEL if answer is None else (answer.strip() or None)


AUTO = Command(
    "auto",
    "Hands-off: take chapters from download to rendered video, stopping for nothing but the Gemini "
    "hand-offs - it downloads, builds each grid upload with MAGI's panel labels, watches llm_crops.json and "
    "imports and cuts each reply as it is saved (writing a fix request when one doesn't check out), packages, "
    "lists each narration upload in chapter order, watches narration.json, and voices, mixes and renders. "
    "No Enter presses: save a reply and it carries on. Stop with Ctrl+C and run it again to resume",
    handlers.auto,
    [
        project_param(),
        Param("chapters", ["--chapters", "-c"], required=False, default=None, prompter=_ask_chapter_range,
              help="Chapters to take to video: numbers and ranges, e.g. '1-5,8' (default: every chapter the "
                   "project has). Chapters MangaDex lists that aren't downloaded yet are downloaded.",
              prompt="Chapters to take to video"),
    ],
    category="Run & check",
    short="Hands-off: chapters to video - you only do the Gemini hand-offs",
    detail="save each Gemini reply into its file and it carries on by itself",
    setup=LLM_CROP_SETUP,
)
