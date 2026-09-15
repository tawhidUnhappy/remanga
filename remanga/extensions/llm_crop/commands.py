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


CROP_GRID = Command(
    "crop-grid",
    "Build this chapter's upload for cropping with Gemini - every page on a square black canvas "
    "under a green 0-1000 ruler grid, as a folder, a zip and/or a PDF carrying the "
    "chapter_info.json the prompt reads - and create the empty llm_crops.json its reply is pasted into",
    handlers.crop_grid,
    [project_param(), chapter_param()],
    category="Chapter Production",
    detail="upload it with prompts/llm_crop.md, paste the reply into llm_crops.json, then run llm-crop",
    setup=LLM_CROP_SETUP,
)

LLM_CROP = Command(
    "llm-crop",
    "Crop with Gemini instead of the Panel Marker - builds the grid upload if needed, waits for the "
    "reply pasted into llm_crops.json, checks it (writing a fix request to send back when something "
    "is wrong) and turns it into crops.json, with preview images to check by eye",
    handlers.llm_crop,
    [project_param(), chapter_param(), _replace_marks_param()],
    category="Chapter Production",
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
    ],
    category="Project-wide",
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
    category="Project-wide",
    detail="the whole-project form of llm-crop - no waiting, just whatever has been pasted",
    setup=LLM_CROP_SETUP,
)
