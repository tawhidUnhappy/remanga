"""The one list of every remanga subcommand.

Adding a command means adding one entry here: it appears in `remanga
--help`, gets its flags parsed, and shows up in the interactive wizard's
menu under its category, with its parameters prompted for according to
their own specs. Nothing else has to be edited anywhere.

`interactive` is deliberately NOT in this registry - it's the thing that
displays this menu, so listing it inside itself would be circular."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from remanga.commands.handlers import chapter as chapter_handlers
from remanga.commands.handlers import cleanup as cleanup_handlers
from remanga.commands.handlers import project as project_handlers
from remanga.commands.handlers import setup as setup_handlers
from remanga.commands.selection import DEFAULT_WIPE_KEEP
from remanga.commands.spec import Command, Param, chapter_param, force_param, project_param
from remanga.pipeline import STEP_REGISTRY
from remanga.reset import RESTART_MODES


@dataclass(frozen=True)
class Category:
    """A wizard menu group. Ordered as listed - roughly the order a project
    moves through them - and described, so the top-level menu says what
    each group is for instead of listing three bare nouns."""

    name: str
    description: str


CATEGORIES: Tuple[Category, ...] = (
    Category("Setup", "settings, shared assets, and model weights"),
    Category("Chapter Production", "one chapter, from download to rendered video"),
    Category("Project-wide", "whole-project compile, status, verify, and cleanup"),
)

_STEP_NAMES = ", ".join(step.name for step in STEP_REGISTRY)
_RESTART_MODE_HELP = ". ".join(f"{mode.name}: {mode.summary}" for mode in RESTART_MODES)
_DEFAULT_KEEP_TEXT = ", ".join(sorted(DEFAULT_WIPE_KEEP))


COMMAND_REGISTRY: List[Command] = [
    Command(
        "setup-config",
        "Walkthrough configuration setup (engine, voice, BGM, resolution, vision format, blur)",
        setup_handlers.setup_config,
        category="Setup",
        detail="every setting, each showing its current value - change one or walk through them all",
    ),
    Command(
        "paths",
        "View/edit the shared asset paths (reference voice WAV, BGM file, TTS transcript) in one "
        "place, without the full setup-config walkthrough",
        setup_handlers.paths,
        category="Setup",
        detail="picks from the audio files already in global/ instead of asking you to type a path",
    ),
    Command(
        "setup-models",
        "Verify and download model weights with SHA-256 verification",
        setup_handlers.setup_models,
        category="Setup",
        detail="fetches only what the current configuration actually uses",
    ),
    Command(
        "download",
        "Download manga chapter from MangaDex",
        chapter_handlers.download,
        [
            project_param(),
            chapter_param("Chapter number (e.g. 1 or 01)"),
            Param("url", ["--url", "-u"], required=False, default=None,
                  help="Manga title or MangaDex URL/UUID (optional if saved)",
                  prompt="Manga title or MangaDex URL"),
        ],
        category="Chapter Production",
        detail="reuses the manga source saved in project.json - only asks when there isn't one",
    ),
    Command(
        "mark",
        "Launch the Panel Marker web UI to mark panels (writes crops.json)",
        chapter_handlers.mark,
        [project_param(), chapter_param()],
        category="Chapter Production",
        detail="MAGI v3 pre-fills what it can find; you adjust and save",
    ),
    Command(
        "review",
        "Launch the Narration Reviewer web UI to flag narration issues (writes "
        "narration_review.json), looping for as many rounds as you want before continuing to "
        "voice synthesis",
        chapter_handlers.review,
        [project_param(), chapter_param()],
        category="Chapter Production",
    ),
    Command(
        "write",
        "Launch the Narration Writer web UI to hand-write narration.json yourself, instead of "
        "an LLM - same panel-by-panel layout as the Narration Reviewer, but each field is the "
        "narration text itself. Generates an empty narration.json, then fills it in from what "
        "you type as you save",
        chapter_handlers.write,
        [project_param(), chapter_param()],
        category="Chapter Production",
    ),
    Command(
        "crop",
        "Crop panels using coordinates in crops.json and package sheets.zip or panels.zip",
        chapter_handlers.crop,
        [
            project_param(), chapter_param(),
            force_param("Force re-cropping even if panels exist"),
        ],
        category="Chapter Production",
    ),
    Command(
        "package",
        "Build/rebuild sheets, sheets.zip, panels.zip, and/or panels.pdf from an already-cropped "
        "chapter's panels, per config.json's cropper.package switches - no re-crop needed",
        chapter_handlers.package,
        [project_param(), chapter_param()],
        category="Chapter Production",
        detail="what to run right after turning a packaging format on in the settings",
    ),
    Command(
        "tts",
        "Generate vocal audio from narration.json",
        chapter_handlers.tts,
        [
            project_param(), chapter_param(),
            Param("voice", ["--voice", "-v"], required=False, default=None,
                  help="Override reference speaker WAV path", prompt="Reference voice override"),
            force_param("Force re-synthesis of all panels"),
        ],
        category="Chapter Production",
    ),
    Command(
        "mix",
        "Mix narration, apply edge fades, BGM, and normalize",
        chapter_handlers.mix,
        [
            project_param(), chapter_param(),
            Param("bgm", ["--bgm", "-b"], required=False, default=None,
                  help="Override background music audio path", prompt="Background music override"),
        ],
        category="Chapter Production",
    ),
    Command(
        "render",
        "Render final recap MP4 video",
        chapter_handlers.render,
        [
            project_param(), chapter_param(),
            force_param("Force re-rendering video"),
        ],
        category="Chapter Production",
    ),
    Command(
        "run",
        "Run this project's pipeline.json (or the full default step order, if it has none) for "
        "one chapter, or an explicit --steps subset/order instead - 'just one tool', 'a lot of "
        f"them', or a full custom pipeline. Steps: {_STEP_NAMES}",
        chapter_handlers.run,
        [
            project_param(), chapter_param(),
            Param("steps", ["--steps", "-s"], required=False, default=None,
                  help="Comma-separated step names to run, in order (one-off override - doesn't "
                       "touch pipeline.json). Default: this project's saved pipeline.json, or the "
                       f"full default order if it has none ({_STEP_NAMES}).",
                  prompt="Steps to run, in order"),
        ],
        category="Chapter Production",
        detail="the whole pipeline, or any subset of it, in any order",
    ),
    Command(
        "wipe",
        "Wipe everything for a chapter (source files and generated sheets/zips/audio/video) except "
        "whatever you choose to keep - unlike restart's fixed modes, any combination can be kept. "
        "Downloaded pages are always re-verified/re-fetched afterward. See wipe-chapters "
        "(Project-wide) for multiple chapters at once.",
        cleanup_handlers.wipe,
        [
            project_param(), chapter_param(),
            Param(
                "keep", ["--keep", "-k"], required=False, default=None,
                prompt="Keep which of the chapter's existing files?",
                help="Comma-separated names of items to keep (e.g. pages,narration.json) - the "
                     "wizard lists what actually exists for the chapter as a checklist. Left unset "
                     f"(the default): keeps {_DEFAULT_KEEP_TEXT} - the downloaded pages, marks, and "
                     "narration script, wiping only what's cheaply regenerated from them. Pass "
                     "'none' to wipe absolutely everything instead.",
            ),
            force_param(),
        ],
        category="Chapter Production",
    ),
    Command(
        "full-recap",
        "Compile every chapter of a project into ONE continuous recap video "
        "(single BGM pass, single loudnorm pass - no per-chapter restarts/joins)",
        project_handlers.full_recap,
        [
            project_param(),
            Param("chapters", ["--chapters", "-c"], required=False, default=None,
                  help="Comma-separated chapter numbers to include, in any order (default: every "
                       "chapter found, in order)",
                  prompt="Chapters to include"),
            force_param("Force a full recompile even if already compiled"),
        ],
        category="Project-wide",
    ),
    Command(
        "remix",
        "Re-mix + re-render a project's chapter video(s) after a BGM/volume change - "
        "no re-narration, no re-cropping, and re-joins the full-recap video if one exists",
        project_handlers.remix,
        [
            project_param(),
            Param("chapters", ["--chapters", "-c"], required=False, default=None,
                  help="Comma-separated chapter numbers to remix (default: every chapter found)",
                  prompt="Chapters to remix"),
            Param("bgm", ["--bgm", "-b"], required=False, default=None,
                  help="Override background music audio path", prompt="Background music override"),
            Param("no_rejoin", ["--no-rejoin"], type="bool", default=False,
                  help="Don't recompile the full-recap video even if one exists",
                  prompt="Skip recompiling the full-recap video?"),
        ],
        category="Project-wide",
    ),
    Command(
        "status",
        "Inspect chapter production status",
        project_handlers.status,
        [project_param(), chapter_param()],
        category="Project-wide",
    ),
    Command(
        "verify",
        "Strictly verify every chapter's audio/video is complete and decodable, not just present "
        "on disk (catches a file left truncated by a kill mid-write) - reports exactly what to "
        "re-run, if anything",
        project_handlers.verify,
        [
            project_param(),
            Param("chapters", ["--chapters", "-c"], required=False, default=None,
                  help="Comma-separated chapter numbers to verify (default: every chapter found)",
                  prompt="Chapters to verify"),
            Param("no_video", ["--no-video"], type="bool", default=False,
                  help="Skip verifying rendered videos, audio only (faster)",
                  prompt="Skip verifying rendered videos (audio only)?"),
        ],
        category="Project-wide",
    ),
    Command(
        "restart",
        "Wipe a chapter back to just its downloaded pages so it can be reprocessed from scratch",
        cleanup_handlers.restart,
        [
            project_param(), chapter_param(),
            force_param(),
            Param(
                "mode", ["--mode", "-m"], type="choice", default="hard",
                choices=[mode.name for mode in RESTART_MODES],
                prompt="How much to keep",
                help=f"How much of the chapter's source folder survives. {_RESTART_MODE_HELP}.",
            ),
            Param("no_reverify", ["--no-reverify"], type="bool", default=False,
                  help="Skip re-checking/re-fetching downloaded pages afterward",
                  prompt="Skip re-checking downloaded pages afterward?"),
        ],
        category="Project-wide",
    ),
    Command(
        "wipe-chapters",
        "Wipe multiple chapters at once (comma list and/or 'N-M' ranges, e.g. '1,3,7-9') - same "
        "dynamic keep-anything behavior as `wipe`, one confirmation covering every selected "
        "chapter.",
        cleanup_handlers.wipe_chapters,
        [
            project_param(),
            Param(
                "chapters", ["--chapters", "-c"], required=True,
                prompt="Chapters to wipe",
                help="Chapter numbers to wipe: comma-separated, numeric ranges allowed (e.g. "
                     "'1,3,7-9'). A range only expands against chapters this project actually has.",
            ),
            Param(
                "keep", ["--keep", "-k"], required=False, default=None,
                prompt="Keep which files in every selected chapter?",
                help="Same as `wipe`'s --keep - comma-separated names to keep, or 'none' for a full "
                     f"wipe. Left unset (the default): keeps {_DEFAULT_KEEP_TEXT} in every selected "
                     "chapter.",
            ),
            force_param(),
        ],
        category="Project-wide",
    ),
]

COMMAND_BY_NAME: Dict[str, Command] = {cmd.name: cmd for cmd in COMMAND_REGISTRY}


def commands_by_category() -> "Dict[Category, List[Command]]":
    """Groups the registry by category, in CATEGORIES order. A command whose
    category isn't in CATEGORIES still gets a group of its own at the end
    rather than disappearing from the wizard - a new category should show up
    the moment a command claims it, described or not."""
    groups: Dict[str, List[Command]] = {}
    for cmd in COMMAND_REGISTRY:
        groups.setdefault(cmd.category, []).append(cmd)

    known = {category.name: category for category in CATEGORIES}
    ordered: Dict[Category, List[Command]] = {}
    for category in CATEGORIES:
        if category.name in groups:
            ordered[category] = groups.pop(category.name)
    for name, cmds in groups.items():
        ordered[known.get(name, Category(name, ""))] = cmds
    return ordered
