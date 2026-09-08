"""The Chapter Production category: one chapter, download to rendered video."""

from __future__ import annotations

from remanga.commands.handlers import (
    chapter as chapter_handlers,
    cleanup as cleanup_handlers,
)
from remanga.commands.help_text import (
    DEFAULT_KEEP_TEXT,
    STEP_NAMES,
)
from remanga.commands.setup_rows import BGM_SETUP, TTS_SETUP, VIDEO_SETUP
from remanga.commands.spec import Command, Param, chapter_param, force_param, project_param
from remanga.config.tts import TTS_ENGINE_SPECS, TTS_ENGINES
from remanga.narration import NARRATION_FILE_MODES, TEMPLATE
from remanga.settings.vision import package_switch_names

CHAPTER_COMMANDS: list[Command] = [
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
        "download-chapters",
        "Download several chapters at once from MangaDex, or open the picker showing which "
        "chapters this project already has vs. what's available upstream",
        chapter_handlers.download_chapters,
        [
            project_param(),
            Param("url", ["--url", "-u"], required=False, default=None,
                  help="Manga title or MangaDex URL/UUID (optional if saved)",
                  prompt="Manga title or MangaDex URL"),
            # Deliberately NOT named "chapters" - that name is special-cased
            # in wizard/params.py to mean "pick from chapters this project
            # already has on disk" (select_chapters/discover_chapters),
            # which is exactly wrong here: this picks from what MangaDex
            # has *upstream*, very possibly chapters not downloaded yet.
            # All three are cli_only: the picker screen this command opens
            # (remanga/wizard/downloads.py) asks every one of them itself,
            # against the actual chapter list - which chapters, on rows that
            # show what's already downloaded; clean-reverify, as a confirm
            # after picking; refetch, as its own menu row. Prompting them
            # generically first would put three text/yes-no boxes in front of
            # the screen that asks the same things far better, and ask about
            # force twice.
            Param("select", ["--select"], required=False, default=None, cli_only=True,
                  help="Comma list and/or ranges ('1,3,7-9'), or 'all' for every chapter MangaDex "
                       "has. Left unset in an interactive terminal opens the picker screen instead.",
                  prompt="Chapters (comma list / ranges / 'all', or leave empty for the picker)"),
            Param("force", ["--force", "-f"], type="bool", default=False, cli_only=True,
                  help="Reverify and download clean - wipe each selected chapter's pages first and "
                       "redownload everything, even ones already marked downloaded",
                  prompt="Reverify and download clean (ignore existing pages)?"),
            Param("refetch", ["--refetch"], type="bool", default=False, cli_only=True,
                  help="Refetch the chapter list from MangaDex instead of using the cached listing "
                       "(cached for 24h)",
                  prompt="Refetch the chapter list from MangaDex instead of using the 24h cache?"),
        ],
        category="Chapter Production",
        detail="the normal (non-force) path always just verifies and fills in whatever's missing - "
               "picking an already-downloaded chapter again is never wasted work",
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
        "narration-init",
        "Create this chapter's narration.json from scratch - either a full template with one "
        "empty entry per cropped panel (the same skeleton the Narration Writer creates), or a "
        "completely empty file (zero bytes, not even '{}')",
        chapter_handlers.narration_init,
        [
            project_param(), chapter_param(),
            Param(
                "mode", ["--mode", "-m"], type="choice", default=TEMPLATE,
                choices=[mode.name for mode in NARRATION_FILE_MODES],
                prompt="What kind of narration.json",
                help="How to create the file. " + ". ".join(
                    f"{mode.name}: {mode.summary}" for mode in NARRATION_FILE_MODES) + ".",
                choice_help={mode.name: mode.summary for mode in NARRATION_FILE_MODES},
                choice_detail={mode.name: mode.detail for mode in NARRATION_FILE_MODES},
            ),
            force_param("Replace an existing narration.json that already has content"),
        ],
        category="Chapter Production",
        detail="a starting point to fill in by hand, or to hand an LLM as the exact structure",
    ),
    Command(
        "normalize-narration",
        "Rewrite this chapter's narration.json into text that's safe to synthesize - removes "
        "emoji, markdown, URLs, SHOUTED words, streeetched letters and every other character "
        "that makes a TTS engine produce artifacts, and writes digits out as words. Never "
        "removes ? ! or ... - those are what the engine reads emotion and pacing from",
        chapter_handlers.normalize_narration_cmd,
        [
            project_param(), chapter_param(),
            Param("dry_run", ["--dry-run"], type="bool", default=False,
                  prompt="Preview only, without writing?",
                  help="Show what would change and exit without touching narration.json"),
            force_param("Write without confirming the preview"),
        ],
        category="Chapter Production",
        detail="shows every line it would change before writing anything",
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
        "chapter's panels - pick the formats per run, no re-crop needed",
        chapter_handlers.package,
        [
            project_param(), chapter_param(),
            Param(
                "formats", ["--formats"], required=False, default=None,
                prompt="What to build for this chapter",
                help="Comma-separated package formats to build - any of: "
                     f"{', '.join(package_switch_names())}, or 'none'. The wizard offers this as a "
                     "checklist. Whatever you pick is remembered for the project, so later chapters "
                     "build the same thing without asking. Left unset: this project's remembered "
                     "choice, or config.json's cropper.package switches if it has never chosen.",
            ),
        ],
        category="Chapter Production",
        detail="pick the upload formats for this chapter; the choice sticks for the project",
    ),
    Command(
        "tts",
        "Generate vocal audio from narration.json",
        chapter_handlers.tts,
        [
            project_param(), chapter_param(),
            Param(
                "engine", ["--engine", "-e"], type="choice", default=None,
                choices=list(TTS_ENGINES),
                prompt="TTS engine",
                help="Synthesize with this engine instead of config.json's tts.engine, just for "
                     "this run - " + ". ".join(
                         f"{spec.name}: {spec.summary}" for spec in TTS_ENGINE_SPECS) + ". Its "
                     "weights download automatically the first time it's used.",
                choice_help={spec.name: spec.display_name for spec in TTS_ENGINE_SPECS},
                choice_detail={spec.name: spec.summary for spec in TTS_ENGINE_SPECS},
            ),
            Param("voice", ["--voice", "-v"], required=False, default=None,
                  help="Override the reference speaker WAV for this run (the configured one is "
                       "used otherwise - change it permanently with `remanga paths`)",
                  prompt="Reference voice"),
            force_param("Force re-synthesis of all panels"),
        ],
        category="Chapter Production",
        detail="uses the configured voice and engine unless you pick otherwise",
        setup=TTS_SETUP,
    ),
    Command(
        "mix",
        "Mix narration, apply edge fades, BGM, and normalize",
        chapter_handlers.mix,
        [
            project_param(), chapter_param(),
            Param("bgm", ["--bgm", "-b"], required=False, default=None,
                  help="Override the background music file for this run (the configured one is "
                       "used otherwise - change it permanently with `remanga paths`)",
                  prompt="Background music"),
        ],
        category="Chapter Production",
        detail="uses the configured background music unless you pick otherwise",
        setup=BGM_SETUP,
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
        detail="renders at the resolution, background and encoder set below",
        setup=VIDEO_SETUP,
    ),
    Command(
        "run",
        "Run this project's saved pipeline (or the full default step order, if it has never "
        "chosen one) for one chapter, or an explicit --steps subset/order instead - 'just one "
        f"tool', 'a lot of them', or a full custom pipeline. Steps: {STEP_NAMES}",
        chapter_handlers.run,
        [
            project_param(), chapter_param(),
            Param("steps", ["--steps", "-s"], required=False, default=None,
                  help="Comma-separated step names to run, in order (a one-off override - unlike "
                       "the wizard's checklist, it never saves). Default: this project's saved "
                       f"pipeline (project.json's \"pipeline\"), or the full default order if it "
                       f"has never chosen one ({STEP_NAMES}).",
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
                     f"(the default): keeps {DEFAULT_KEEP_TEXT} - the downloaded pages, marks, and "
                     "narration script, wiping only what's cheaply regenerated from them. Pass "
                     "'none' to wipe absolutely everything instead.",
            ),
            force_param(),
        ],
        category="Chapter Production",
    ),
]
