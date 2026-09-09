"""The Project-wide category: whole-project compile, status, verify and cleanup."""

from __future__ import annotations

from remanga.commands.handlers import (
    cleanup as cleanup_handlers,
    project as project_handlers,
)
from remanga.commands.help_text import (
    DEFAULT_KEEP_TEXT,
    RESTART_MODE_HELP,
)
from remanga.commands.setup_rows import BGM_SETUP, VIDEO_SETUP
from remanga.commands.spec import Command, Param, chapter_param, force_param, project_param
from remanga.reset import (
    DEFAULT_REBUILD_MODE,
    REBUILD_MODE_NAMES,
    REBUILD_MODES,
    RESTART_MODES,
)

PROJECT_COMMANDS: list[Command] = [
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
            Param(
                "rebuild", ["--rebuild"], type="choice", default=DEFAULT_REBUILD_MODE,
                choices=list(REBUILD_MODE_NAMES),
                prompt="How much to rebuild",
                help="How much of this project to rebuild. Replaces the old --force / "
                     "--regenerate-effects / --regenerate-all trio, which were three yes/no "
                     "flags a person had to combine correctly to express one decision. "
                     + " ".join(
                         f"'{m.name}': deletes {m.deletes}, keeps {m.keeps} ({m.cost})."
                         for m in REBUILD_MODES
                     ),
                choice_help={m.name: f"deletes {m.deletes}" for m in REBUILD_MODES},
                choice_detail={
                    m.name: f"Deletes {m.deletes}. Keeps {m.keeps}. {m.cost[:1].upper()}{m.cost[1:]}."
                    for m in REBUILD_MODES
                },
            ),
        ],
        category="Project-wide",
        detail="one BGM pass and one render for the whole manga - both configured below",
        setup=BGM_SETUP + VIDEO_SETUP,
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
        detail="change the music or the video settings here, then re-mix and re-render with them",
        setup=BGM_SETUP + VIDEO_SETUP,
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
                help=f"How much of the chapter's source folder survives. {RESTART_MODE_HELP}.",
                choice_help={mode.name: mode.summary for mode in RESTART_MODES},
                choice_detail={mode.name: f"keeps: {mode.keeps}" for mode in RESTART_MODES},
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
                     f"wipe. Left unset (the default): keeps {DEFAULT_KEEP_TEXT} in every selected "
                     "chapter.",
            ),
            force_param(),
        ],
        category="Project-wide",
    ),
]
