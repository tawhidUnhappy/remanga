"""The Project-wide category: whole-project setup (fetch every chapter, give
every chapter a narration file), compile, status, verify and cleanup."""

from __future__ import annotations

from remanga.commands.handlers import (
    cleanup as cleanup_handlers,
    project as project_handlers,
)
from remanga.commands.help_text import (
    DEFAULT_KEEP_TEXT,
    RESTART_MODE_HELP,
)
from remanga.commands.setup_rows import BGM_SETUP, CROP_SETUP, VIDEO_SETUP
from remanga.commands.spec import (
    Command,
    Param,
    chapter_param,
    chapters_param,
    force_param,
    formats_param,
    project_param,
    url_param,
)
from remanga.reset import (
    DEFAULT_REBUILD_MODE,
    REBUILD_MODE_NAMES,
    REBUILD_MODES,
    RESTART_MODES,
)

PROJECT_COMMANDS: list[Command] = [
    Command(
        "download-all",
        "Download EVERY chapter MangaDex lists for this project's manga - no picker, no "
        "selection: the whole manga in the configured translation language (English by "
        "default), taking the newest upload of each chapter number when more than one exists. "
        "Chapters already downloaded are verified rather than re-fetched",
        project_handlers.download_all,
        [
            project_param(),
            url_param(),
            # Both deliberately unasked by the wizard: the handler prints how
            # many chapters there are and how many are already here, then asks
            # one question about the run as a whole. Two yes/no boxes in front
            # of that would be answering before knowing the size of the job.
            Param("force", ["--force", "-f"], type="bool", default=False, cli_only=True,
                  help="Re-fetch every chapter clean - wipe each chapter's pages first and "
                       "download again, even ones already complete",
                  prompt="Re-fetch every chapter clean?"),
            Param("refetch", ["--refetch"], type="bool", default=False, cli_only=True,
                  help="Refetch the chapter list from MangaDex instead of the 24h cached listing",
                  prompt="Refetch the chapter list from MangaDex?"),
        ],
        category="Project-wide",
        detail="the whole manga in one go - re-runnable, and only downloads what's actually missing",
    ),
    Command(
        "download-range",
        "Download a range of chapters from MangaDex - '1-5' takes every chapter from 1 to the end "
        "of 5, parts included (2.1, 2.2, 5.1, 5.2); commas combine ranges and single chapters. "
        "Chapters already downloaded are re-verified page by page against MangaDex's checksums, "
        "with anything in pages/ that isn't theirs removed",
        project_handlers.download_range,
        [
            project_param(),
            url_param(),
            # cli_only, both: the handler asks for the range itself, after
            # showing which chapters MangaDex has - a range typed blind, before
            # knowing whether the manga numbers 5 as "5" or "5.1, 5.2", is the
            # question asked too early.
            Param("range", ["--range", "-r"], required=False, default=None, cli_only=True,
                  help="Chapters to download: a range ('1-5'), single chapters, or both, comma-"
                       "separated ('1-5,8,10-12'). A whole-number end includes that chapter's "
                       "parts (1-5 takes 5.1 and 5.2); a decimal end is exact (1-4.1). Asked "
                       "interactively when left out.",
                  prompt="Chapters to download"),
            Param("force", ["--force", "-f"], type="bool", default=False, cli_only=True,
                  help="Re-fetch every selected chapter clean - wipe its pages first and "
                       "download all of them again, even pages that verify",
                  prompt="Re-fetch every selected chapter clean?"),
        ],
        category="Project-wide",
        detail="a run of chapters by number - shows what the range covers before downloading, "
               "and re-verifies anything already here",
    ),
    Command(
        "mark-all",
        "Mark panels for every chapter in the project in ONE browser tab - saving a chapter "
        "writes its crops.json and swaps the next chapter into the same page, and the chapter "
        "arrows go back to one already done, so a whole manga is marked and checked in a single "
        "sitting instead of one launch per chapter",
        project_handlers.mark_all,
        [
            project_param(),
            chapters_param("mark", "Chapters with no downloaded pages are skipped."),
        ],
        category="Project-wide",
        detail="one tab, one server, one MAGI load per chapter - the whole manga in one session",
    ),
    Command(
        "view-marks",
        "Look through every chapter's marked panels WITHOUT being able to change any of them - "
        "the same one-tab session as mark-all, read-only: navigate the whole project from the "
        "sidebar outline, chapter by chapter, page by page, panel by panel, and check the marks "
        "are what you think they are. Nothing is saved, and MAGI never runs",
        project_handlers.view_marks,
        [
            project_param(),
            chapters_param("look through", "Chapters with no downloaded pages are skipped."),
        ],
        category="Project-wide",
        detail="the double-check pass - read-only, enforced on the server, not just hidden",
    ),
    Command(
        "crop-all",
        "Crop panels for every marked chapter in the project at once, from each chapter's "
        "crops.json - the same cropping as `crop`, run over the whole manga instead of one "
        "chapter at a time. Chapters not marked yet are skipped and named; chapters already "
        "cropped are left alone unless you say otherwise",
        project_handlers.crop_all,
        [
            project_param(),
            chapters_param("crop", "Chapters with no crops.json are skipped."),
            # cli_only: the handler asks this itself, once, naming the
            # chapters that are actually already cropped - asked up front it
            # would be "re-crop the cropped ones?" before anyone knows
            # whether there are any.
            Param("force", ["--force", "-f"], type="bool", default=False, cli_only=True,
                  help="Re-crop chapters that are already cropped too - wipes their panels/ and "
                       "cuts them again from crops.json",
                  prompt="Re-crop chapters that are already cropped too?"),
        ],
        category="Project-wide",
        detail="the whole-project form of `crop` - every marked chapter cut into panels in one go",
        setup=CROP_SETUP,
    ),
    Command(
        "package-all",
        "Build/rebuild sheets, sheets.zip, panels.zip, and/or panels.pdf for every cropped chapter "
        "in the project at once - the same formats checklist as `package`, answered once for the "
        "whole manga instead of once per chapter. Chapters that haven't been cropped yet are "
        "skipped and named",
        project_handlers.package_all,
        [
            project_param(),
            chapters_param("package", "Chapters with no cropped panels are skipped."),
            formats_param("What to build for every chapter"),
        ],
        category="Project-wide",
        detail="the whole-project form of `package` - one formats answer covers every chapter, "
               "and sticks for the project",
    ),
    Command(
        "narration-init-all",
        "Create a blank narration.json for every chapter in the project - zero bytes, not even "
        "'{}', so every chapter has a script file waiting to be filled in. Chapters that already "
        "have a narration.json with content in it are left alone unless you say otherwise",
        project_handlers.narration_init_all,
        [
            project_param(),
            chapters_param("give a blank narration.json"),
            # cli_only: the handler asks this itself, once, naming the
            # chapters that actually have a script - which is a question
            # worth answering. Asked up front by the wizard it would be
            # "replace the written ones?" before anyone knows whether there
            # are any, and then asked again by the handler when there are.
            Param("force", ["--force", "-f"], type="bool", default=False, cli_only=True,
                  help="Blank chapters that already have a written narration.json too",
                  prompt="Blank chapters that already have a written narration.json too?"),
        ],
        category="Project-wide",
        detail="the whole-project form of the pipeline's init-narration step - one answer covers "
               "every chapter",
    ),
    Command(
        "full-recap",
        "Compile every chapter of a project into ONE continuous recap video "
        "(single BGM pass, single loudnorm pass - no per-chapter restarts/joins)",
        project_handlers.full_recap,
        [
            project_param(),
            chapters_param("include"),
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
            chapters_param("remix"),
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
            chapters_param("verify"),
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
