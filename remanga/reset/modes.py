"""What each restart mode keeps - the fixed presets, as data.

`restart` offers four named modes and `wipe` offers "keep any combination
you like" (see remanga.reset.entries.wipeable_entries). The four presets
live here as specs rather than as an if/elif chain plus two parallel
dictionaries of display strings in the command handler: the label and the
"kept:" line shown before a destructive confirmation are part of what a
mode *is*, and having them anywhere else is how a mode's description ends
up describing what it used to delete.

PROJECT_KEEP, at the bottom, is the same idea one level up: what a
whole-project wipe keeps, as data."""

from __future__ import annotations

from dataclasses import dataclass

# Chapter-source entries kept by each deletion mode. "pages" (the downloaded
# scans) is always kept - a restart never re-downloads unless
# reverify_downloads finds something missing.
KEEP_ON_RESTART = {"pages"}
KEEP_ON_MARKS_ONLY_RESTART = KEEP_ON_RESTART | {"crops.json"}
KEEP_ON_SOFT_RESTART = KEEP_ON_RESTART | {
    "crops.json", "panels", "narration.json", "narration_review.json", "narration_reviews",
}

_KEEP_SETS: dict[str, set] = {
    "hard": KEEP_ON_RESTART,
    "marks_only": KEEP_ON_MARKS_ONLY_RESTART,
    "soft": KEEP_ON_SOFT_RESTART,
}

# What a whole-PROJECT wipe keeps, and the only things that do - see
# remanga.reset.actions.wipe_project. Two groups, and nothing else at the
# project root belongs to either:
#   - chapters/  the source tree. paths.get_chapter_dir holds only material
#                that was fetched from outside the pipeline or hand-authored
#                (pages/, crops.json, narration.json), so nothing in there is
#                ever something a regenerate could rebuild.
#   - the project's own metadata/settings files. project.json (manga source
#     + this project's remembered choices), memory.json (the LLM's story
#     continuity), manifest.json (production bookkeeping AND the cached
#     MangaDex chapter feed - throwing it away would turn a re-verify into a
#     re-download of every page), and pipeline.json, the legacy home of the
#     saved step order still read for projects written by an older version
#     (paths.get_pipeline_path): a settings file exactly like project.json,
#     and deleting a setting is not what "delete the generated files" means.
#
# Everything else directly under projects/{manga}/ is a generated-artifact
# directory (paths.GENERATED_KINDS - audio/, video/, panels_zip/, sheets/,
# ...) and goes. Expressed as "keep these, delete the rest" rather than as a
# loop over GENERATED_KINDS on purpose: a stray folder from an older layout,
# a kind that is no longer produced, or a half-written temp directory is
# exactly the stale state a full regenerate exists to clear, and a
# delete-list built from the current GENERATED_KINDS would walk straight
# past every one of them.
PROJECT_KEEP: tuple[str, ...] = (
    "chapters", "manifest.json", "memory.json", "pipeline.json", "project.json",
)


@dataclass(frozen=True)
class RestartMode:
    """One selectable restart preset.

    `deletion_mode` is the mode that actually decides what gets deleted, and
    is usually the mode's own name. "remark" is the exception: it deletes
    exactly like marks_only and then reopens the Panel Marker, which is a
    UI behavior rather than a different deletion - expressing that here is
    what stops it from being a special case inside the delete path."""

    name: str
    label: str
    keeps: str
    summary: str
    deletion_mode: str = ""
    reopen_marker: bool = False

    @property
    def deletes_like(self) -> str:
        return self.deletion_mode or self.name


RESTART_MODES: tuple[RestartMode, ...] = (
    RestartMode(
        "hard", "Hard restart", "downloaded pages",
        "back to just the downloaded pages - re-mark, re-crop, re-narrate",
    ),
    RestartMode(
        "marks_only", "Marks-only restart",
        "downloaded pages and crops.json (narration.json gets emptied, not kept)",
        "keep the panel marks, redo everything after them",
    ),
    RestartMode(
        "remark", "Re-mark restart",
        "downloaded pages and crops.json (narration.json gets emptied, not kept)",
        "same as marks-only, then reopens the Panel Marker with those marks loaded",
        deletion_mode="marks_only", reopen_marker=True,
    ),
    RestartMode(
        "soft", "Soft restart", "downloaded pages, crops.json, panels/, and narration.json",
        "keep everything hand-made; wipe only generated audio/video/packaging",
    ),
)

RESTART_MODE_NAMES = tuple(mode.name for mode in RESTART_MODES)
RESTART_MODE_BY_NAME = {mode.name: mode for mode in RESTART_MODES}


def keep_set(mode: str) -> set:
    """The chapter-source entries a deletion mode preserves. Accepts only
    real deletion modes ("remark" resolves to marks_only before it gets
    here - see RestartMode.deletes_like)."""
    try:
        return set(_KEEP_SETS[mode])
    except KeyError:
        raise ValueError(
            f"Unknown restart mode {mode!r} - expected one of {tuple(_KEEP_SETS)}"
        ) from None


@dataclass(frozen=True)
class RebuildMode:
    """One selectable answer to "how much of this should be rebuilt?".

    Replaces three separate yes/no prompts (--force, --regenerate-effects,
    --regenerate-all) that a person had to combine correctly in their head
    to get what they wanted. They are not independent - each is strictly
    more destructive than the last - so a single ordered choice is both
    honest about that and impossible to answer incoherently.

    `deletes` and `keeps` are written as concrete file paths rather than as
    categories, because "regenerate everything" does not tell anyone whether
    an hour of synthesized speech is about to go."""

    name: str
    label: str
    deletes: str
    keeps: str
    cost: str
    # What the handler actually does with it.
    force: bool
    wipe: str = ""  # "" | "derived" | "project"


REBUILD_MODES: tuple[RebuildMode, ...] = (
    RebuildMode(
        "missing", "Only what's missing",
        deletes="nothing",
        keeps="everything already built",
        cost="fastest - picks up where the last run stopped",
        force=False,
    ),
    RebuildMode(
        "outputs", "Sound and video",
        deletes="audio_modified/ and video/",
        keeps="audio/ - the synthesized narration",
        cost="minutes - no re-narration",
        force=True, wipe="derived",
    ),
    RebuildMode(
        "everything", "Everything, from scratch",
        deletes="audio/, audio_modified/ and video/ - every generated file",
        keeps="chapters/ (pages, crops.json, narration.json) and the project's json files",
        cost="slowest - re-runs text-to-speech on every panel",
        force=True, wipe="project",
    ),
    RebuildMode(
        "sources", "Down to the source files",
        deletes="every generated file, AND the cropped panels/",
        keeps="only what remanga cannot rebuild: pages (re-verified), crops.json, "
              "narration.json, and the project's json files",
        cost="slowest - re-crops, re-narrates the audio, re-renders and re-joins",
        force=True, wipe="sources",
    ),
)

# What a "down to the source files" rebuild keeps INSIDE chapters/. Exactly
# the three things remanga cannot produce for itself:
#   pages/          fetched from MangaDex (re-verified, not re-downloaded
#                   wholesale - see reset.reverify_chapter_downloads)
#   crops.json      panel boxes, hand-placed or hand-corrected in the Marker
#   narration.json  written by an LLM against those panels, then reviewed
# Everything else in there - panels/ above all - is a derivative of these
# three and is rebuilt. panels/ is included in the delete precisely because
# it is NOT source: it is the crop output, and keeping a stale one is how a
# re-crop silently disagrees with narration.json's panel_ids.
KEEP_ON_SOURCES_REBUILD = {"pages", "crops.json", "narration.json"}

REBUILD_MODE_NAMES = tuple(mode.name for mode in REBUILD_MODES)
REBUILD_MODE_BY_NAME = {mode.name: mode for mode in REBUILD_MODES}
DEFAULT_REBUILD_MODE = REBUILD_MODES[0].name
