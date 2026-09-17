"""The wizard's top-level menu groups.

Their own module rather than a block inside the command catalog: every
catalog file names these categories, and the catalog files are what change
when a command is added. Keeping the groups here means adding a command
never touches the file that defines what the groups *are*."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    """A wizard menu group. Ordered as listed - the order a chapter moves
    through them - and described, so the top-level menu says what
    each group is for instead of listing three bare nouns."""

    name: str
    description: str


CATEGORIES: tuple[Category, ...] = (
    # The first five are a chapter's way from pages to video, in order, and
    # say which step they are; the rest are for any time. The step is in the
    # description rather than the name, so typing a group's name to filter
    # the menu still works, and a numbered menu doesn't read "2. 1 · ...".
    Category("Get pages", "step 1 · download chapters from MangaDex"),
    Category("Crop panels", "step 2 · mark panels by hand or with Gemini, then cut them out"),
    Category("Package for the LLM", "step 3 · sheets, zips and PDFs of the cut panels, to upload"),
    Category("Narration", "step 4 · create the script, write it yourself, review it"),
    Category("Audio & video", "step 5 · voice, mix and render, for one chapter or the whole manga"),
    Category("Run & check", "run the pipeline, see how far chapters have got, verify outputs"),
    Category("Clean up", "delete a chapter's files, or reset it to its pages"),
    Category("Setup", "settings, shared files, model weights and tools"),
)
