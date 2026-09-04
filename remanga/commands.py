"""Single shared registry of every remanga subcommand - name, help text,
argparse-equivalent param specs, and the handler that does the actual work.
remanga/cli.py builds its argparse subparsers by iterating this list, and
remanga/wizard.py's interactive menu lists/prompts for the same commands, so
the two front-ends can never drift apart the way two hand-maintained lists
did. Every handler below is a thin wrapper around exactly the same
downloader/cropper/audio/video/webui/pipeline calls cli.py's main() always
used - no business logic changed, just relocated so both front-ends can call
it uniformly as handler(params: dict, config: RemangaConfig).

`interactive` itself is deliberately NOT in this registry - it's the thing
that shows this menu, so listing it as an option inside itself would be
confusing self-reference (see wizard.py)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from rich.prompt import Confirm

from remanga import reset
from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.full_recap import FullRecapCompiler, chapter_sort_key
from remanga.audio.synth import create_synthesizer
from remanga.remix import remix_project
from remanga.verify import verify_project
from remanga.setup_wizard import run_setup_wizard
from remanga.paths_manager import run_paths_manager
from remanga.pipeline import STEP_REGISTRY, load_pipeline, run_pipeline
from remanga.status import render_status_panel
from remanga.video import VideoRenderer
from remanga.webui import launch_and_wait as launch_panel_marker
from remanga.webui import launch_and_wait_writer


@dataclass
class Param:
    """One argparse argument for a Command. `name` doubles as the argparse
    dest, so it MUST match what argparse infers from `flags`' first long
    option (e.g. flags=["--no-rejoin"] -> name="no_rejoin"). `type` is
    "str", "bool" (store_true), or "choice" (str + `choices`)."""
    name: str
    flags: List[str]
    type: str = "str"
    required: bool = False
    default: Any = None
    choices: Optional[List[str]] = None
    help: str = ""


@dataclass
class Command:
    name: str
    help: str
    handler: Callable[[Dict[str, Any], RemangaConfig], None]
    params: List[Param] = field(default_factory=list)
    # Purely a grouping hint for the wizard's nested menu (Setup / Chapter
    # Production / Project-wide) - cli.py's argparse ignores it entirely, so
    # this can never make the CLI and the wizard drift: both still read every
    # other field off the same Command.
    category: str = "General"


def add_param_to_parser(parser, param: Param) -> None:
    """Adds one Param to an argparse (sub)parser exactly the way cli.py's
    hand-written add_argument() calls used to, so --help output stays
    byte-identical."""
    kwargs: Dict[str, Any] = {"help": param.help}
    if param.type == "bool":
        kwargs["action"] = "store_true"
    else:
        if param.choices:
            kwargs["choices"] = param.choices
        kwargs["required"] = param.required
        kwargs["default"] = param.default
    parser.add_argument(*param.flags, **kwargs)


def params_from_namespace(cmd: Command, ns) -> Dict[str, Any]:
    """Pulls this command's own params out of an argparse Namespace (or
    anything with matching attributes) into a plain dict keyed by param name."""
    return {p.name: getattr(ns, p.name, p.default) for p in cmd.params}


# ---------------------------------------------------------------------------
# Handlers - one per subcommand, same logic cli.py's main() always ran.
# ---------------------------------------------------------------------------


def _h_setup_config(params: Dict[str, Any], config: RemangaConfig) -> None:
    run_setup_wizard(config)


def _h_paths(params: Dict[str, Any], config: RemangaConfig) -> None:
    run_paths_manager(config)


def _h_setup_models(params: Dict[str, Any], config: RemangaConfig) -> None:
    # Only the currently-configured TTS engine's weights are fetched -
    # switching tts.engine later (setup-config) downloads the other engine's
    # weights the first time it's actually used, same as every engine's own
    # lazy ensure_model() already does.
    create_synthesizer(config.tts, config.audio).model_manager.ensure_model()
    from remanga.webui.magi_assist import ensure_weights_downloaded
    ensure_weights_downloaded(config.marker)

    # DeepSeek-OCR-2 (powers the Narration Writer's "OCR this panel" button -
    # see remanga/ocr/engine.py). Reuses OCREngine's own ModelManager instead
    # of building a second one here, so the expected_files/repo_id live in
    # exactly one place.
    from remanga.ocr import OCREngine
    OCREngine(config.ocr).model_manager.ensure_model()


def _h_download(params: Dict[str, Any], config: RemangaConfig) -> None:
    dl = MangaDexDownloader(config.downloader)
    dl.download_chapter(params.get("url"), params["chapter"], params["project"])


def _h_mark(params: Dict[str, Any], config: RemangaConfig) -> None:
    launch_panel_marker(params["project"], params["chapter"], config.marker)


def _h_review(params: Dict[str, Any], config: RemangaConfig) -> None:
    # Deferred import: wizard.py imports this module (COMMAND_REGISTRY), so a
    # top-level import of wizard.py here would be circular.
    from remanga.wizard import run_narration_review_loop
    run_narration_review_loop(params["project"], params["chapter"], config)


def _h_write(params: Dict[str, Any], config: RemangaConfig) -> None:
    launch_and_wait_writer(params["project"], params["chapter"], config.writer, config.ocr)


def _h_crop(params: Dict[str, Any], config: RemangaConfig) -> None:
    cropper = CoordinateCropper(config.cropper)
    cropper.crop_chapter_from_json(params["project"], params["chapter"], force=bool(params.get("force")))


def _h_package(params: Dict[str, Any], config: RemangaConfig) -> None:
    # Deliberately separate from `crop` (which only tops up a package format
    # for a chapter that's *already* cropped, if it's missing entirely - see
    # CoordinateCropper.crop_chapter_from_json's resume-check) - this always
    # rebuilds every currently-enabled format (sheets/sheets_zip/sheets_
    # folders/panels_zip/panels_pdf/...) from this chapter's existing
    # panels/, e.g. right after flipping one on in setup-config, without
    # forcing a full re-crop just to pick it up.
    from remanga.cropper.crop_report import package_outputs
    from remanga.paths import get_chapter_dir

    project_name, chapter_num = params["project"], params["chapter"]
    panels_dir = get_chapter_dir(project_name, chapter_num) / "panels"
    panel_paths = sorted(p for p in panels_dir.iterdir() if p.is_file()) if panels_dir.exists() else []
    if not panel_paths:
        raise FileNotFoundError(
            f"No cropped panels found for chapter {chapter_num}: {panels_dir}\n"
            f"Run `crop` for this chapter first."
        )
    package_outputs(config.cropper, panel_paths, project_name, chapter_num)


def _h_tts(params: Dict[str, Any], config: RemangaConfig) -> None:
    tts = TTSEngine(config.tts, config.audio)
    tts.generate_narration_audio(
        params["project"], params["chapter"],
        voice_override=params.get("voice"), interactive=True, force=bool(params.get("force")),
    )


def _h_mix(params: Dict[str, Any], config: RemangaConfig) -> None:
    mixer = AudioProcessor(config.audio)
    mixer.mix_master_audio(params["project"], params["chapter"], bgm_override=params.get("bgm"), interactive=True)


def _h_render(params: Dict[str, Any], config: RemangaConfig) -> None:
    renderer = VideoRenderer(config.system, config.video)
    renderer.render_video(params["project"], params["chapter"], force=bool(params.get("force")))


def _split_chapters(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    return sorted({c.strip() for c in raw.split(",") if c.strip()}, key=chapter_sort_key)


def _h_full_recap(params: Dict[str, Any], config: RemangaConfig) -> None:
    chapters = _split_chapters(params.get("chapters"))
    compiler = FullRecapCompiler(config)
    compiler.compile_full_manga(params["project"], force=bool(params.get("force")), chapters=chapters)


def _h_remix(params: Dict[str, Any], config: RemangaConfig) -> None:
    chapters = _split_chapters(params.get("chapters"))
    remix_project(
        params["project"], config, chapters=chapters,
        bgm_override=params.get("bgm"), rejoin=not params.get("no_rejoin"),
    )


def _h_run(params: Dict[str, Any], config: RemangaConfig) -> None:
    steps_raw = params.get("steps")
    steps = [s.strip() for s in steps_raw.split(",") if s.strip()] if steps_raw else load_pipeline(params["project"])
    run_pipeline(params["project"], params["chapter"], config, steps)


def _h_status(params: Dict[str, Any], config: RemangaConfig) -> None:
    console.print(render_status_panel(params["project"], params["chapter"]))


def _h_verify(params: Dict[str, Any], config: RemangaConfig) -> None:
    chapters = _split_chapters(params.get("chapters"))
    verify_project(params["project"], chapters=chapters, check_video=not params.get("no_video"))


def _h_restart(params: Dict[str, Any], config: RemangaConfig) -> None:
    project, chapter, mode = params["project"], params["chapter"], params.get("mode") or "hard"
    # "remark" isn't a real reset.py mode - it deletes exactly like
    # marks_only, then additionally reopens the Panel Marker below.
    deletion_mode = "marks_only" if mode == "remark" else mode
    candidates = reset.restart_candidates(project, chapter, mode=deletion_mode)
    kind = {"hard": "Restart", "marks_only": "Marks-only restart", "remark": "Re-mark restart", "soft": "Soft restart"}[mode]
    kept = {
        "hard": "downloaded pages",
        "marks_only": "downloaded pages and crops.json (narration.json gets emptied, not kept)",
        "remark": "downloaded pages and crops.json (narration.json gets emptied, not kept)",
        "soft": "downloaded pages, crops.json, panels/, and narration.json",
    }[mode]
    if not candidates:
        console.print(f"[dim]Nothing to delete for a {kind.lower()} - everything it would keep is already all that's here.[/]")
        return
    console.print(f"[bold red]{kind}: the following will be permanently deleted:[/]")
    for c in candidates:
        console.print(f"  [dim]- {c}[/]")
    console.print(f"[dim]Kept: {kept}.[/]")
    if params.get("force") or Confirm.ask(
        f"[bold red]Confirm: permanently delete these {len(candidates)} item(s) for Chapter {chapter}? This cannot be undone.[/]",
        default=False,
    ):
        reset.restart_chapter(project, chapter, mode=deletion_mode, reverify_downloads=not params.get("no_reverify"))
        console.print(f"[bold green]✓ Chapter {chapter} {kind.lower()} complete. Downloaded pages kept — ready to reprocess.[/]")
        if mode == "remark":
            console.print("[yellow]Reopening the Panel Marker - your existing marks are pre-loaded (MAGI won't touch them).[/]")
            launch_panel_marker(project, chapter, config.marker)
            console.print(f"[bold green]✓ Marks for Chapter {chapter} updated and saved.[/]")
    else:
        console.print("[dim]Restart cancelled.[/]")


# Applied whenever --keep is left unset entirely (None) - the three things
# most expensive/annoying to redo (a re-download, re-marking panels, and an
# LLM narration pass) survive a wipe by default; everything generated from
# them (panels/, sheets/zips, audio, video) does not. Pass --keep explicitly
# (a comma list, or "none" for an absolute full wipe) to override this.
DEFAULT_WIPE_KEEP = {"pages", "crops.json", "narration.json"}


def _resolve_wipe_keep(keep_raw: Optional[str]) -> set:
    """Shared by the single- and multi-chapter wipe handlers below. None
    (flag left unset) -> DEFAULT_WIPE_KEEP; 'none'/'nothing' -> wipe
    absolutely everything; anything else -> that comma list, verbatim."""
    if keep_raw is None:
        return set(DEFAULT_WIPE_KEEP)
    if keep_raw.strip().lower() in ("none", "nothing"):
        return set()
    return {n.strip() for n in keep_raw.split(",") if n.strip()}


def _parse_chapter_selection(raw: str, project_name: str) -> List[str]:
    """Comma-separated chapter numbers and/or numeric ranges ('N-M') for the
    multi-chapter `wipe-chapters` command - e.g. '1,3,7-9'. A range expands
    only against chapters this project actually has (full_recap.
    discover_chapters), so '1-24' doesn't manufacture chapter numbers that
    were never downloaded; a plain (non-range) token is passed through
    literally even if it doesn't exist yet, matching _split_chapters'
    existing permissiveness elsewhere - wipe naturally no-ops on one that
    isn't there."""
    from remanga.full_recap import discover_chapters

    existing = discover_chapters(project_name)
    result: set = set()
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            lo_s, _, hi_s = token.partition("-")
            try:
                lo, hi = float(lo_s), float(hi_s)
            except ValueError:
                result.add(token)  # not a numeric range (e.g. a literal label with a dash) - keep as-is
                continue
            for ch in existing:
                try:
                    val = float(ch)
                except ValueError:
                    continue
                if lo <= val <= hi:
                    result.add(ch)
            continue
        result.add(token)
    return sorted(result, key=chapter_sort_key)


def _h_wipe(params: Dict[str, Any], config: RemangaConfig) -> None:
    project, chapter = params["project"], params["chapter"]
    keep_names = _resolve_wipe_keep(params.get("keep"))
    candidates = [e for e in reset.wipeable_entries(project, chapter) if e.name not in keep_names]
    if not candidates:
        console.print("[dim]Nothing to wipe - everything here is already in the keep list.[/]")
        return
    console.print("[bold red]Wipe: the following will be permanently deleted:[/]")
    for c in candidates:
        console.print(f"  [dim]- {c}[/]")
    console.print(f"[dim]Kept: {', '.join(sorted(keep_names)) or '(nothing - full wipe)'}.[/]")
    if params.get("force") or Confirm.ask(
        f"[bold red]Confirm: permanently delete these {len(candidates)} item(s) for Chapter {chapter}? This cannot be undone.[/]",
        default=False,
    ):
        # Downloads are always re-verified afterward, regardless of whether
        # pages/ itself was kept - a wipe that deleted it should still end
        # up re-downloaded rather than just missing (see reset.wipe_chapter).
        reset.wipe_chapter(project, chapter, keep_names, reverify_downloads=True)
        console.print(f"[bold green]✓ Chapter {chapter} wipe complete. Downloaded pages re-verified.[/]")
    else:
        console.print("[dim]Wipe cancelled.[/]")


def _h_wipe_chapters(params: Dict[str, Any], config: RemangaConfig) -> None:
    project = params["project"]
    keep_names = _resolve_wipe_keep(params.get("keep"))
    chapters = _parse_chapter_selection(params["chapters"], project)
    if not chapters:
        console.print(f"[dim]No chapters matched '{params['chapters']}' for project '{project}'.[/]")
        return

    per_chapter: Dict[str, List] = {}
    total = 0
    for ch in chapters:
        candidates = [e for e in reset.wipeable_entries(project, ch) if e.name not in keep_names]
        if candidates:
            per_chapter[ch] = candidates
            total += len(candidates)

    if not total:
        console.print("[dim]Nothing to wipe across the selected chapter(s) - everything is already in the keep list.[/]")
        return

    console.print(f"[bold red]Wipe: the following will be permanently deleted across {len(per_chapter)} chapter(s):[/]")
    for ch, candidates in per_chapter.items():
        console.print(f"[bold]Chapter {ch}:[/]")
        for c in candidates:
            console.print(f"  [dim]- {c}[/]")
    console.print(f"[dim]Kept: {', '.join(sorted(keep_names)) or '(nothing - full wipe)'}.[/]")
    if params.get("force") or Confirm.ask(
        f"[bold red]Confirm: permanently delete these {total} item(s) across {len(per_chapter)} chapter(s)? "
        f"This cannot be undone.[/]",
        default=False,
    ):
        for ch in per_chapter:
            reset.wipe_chapter(project, ch, keep_names, reverify_downloads=True)
        console.print(f"[bold green]✓ Wipe complete for chapter(s) {', '.join(per_chapter)}. Downloaded pages re-verified.[/]")
    else:
        console.print("[dim]Wipe cancelled.[/]")


_PROJECT = lambda help_: Param("project", ["--project", "-p"], required=True, help=help_)
_CHAPTER = lambda help_="Chapter number": Param("chapter", ["--chapter", "-c"], required=True, help=help_)

COMMAND_REGISTRY: List[Command] = [
    Command(
        "setup-config",
        "Walkthrough configuration setup (voice, BGM, resolution, vision format, blur)",
        _h_setup_config,
        category="Setup",
    ),
    Command(
        "paths",
        "View/edit the shared asset paths (reference voice WAV, BGM file, audio8 TTS transcript) "
        "in one place, without the full setup-config walkthrough",
        _h_paths,
        category="Setup",
    ),
    Command(
        "setup-models",
        "Verify and download model weights with SHA-256 verification",
        _h_setup_models,
        category="Setup",
    ),
    Command(
        "download",
        "Download manga chapter from MangaDex",
        _h_download,
        [
            _PROJECT("Project name"),
            _CHAPTER("Chapter number (e.g. 1 or 01)"),
            Param("url", ["--url", "-u"], required=False, default=None,
                  help="Manga title or MangaDex URL/UUID (optional if saved)"),
        ],
        category="Chapter Production",
    ),
    Command(
        "mark",
        "Launch the Panel Marker web UI to mark panels (writes crops.json)",
        _h_mark,
        [_PROJECT("Project name"), _CHAPTER()],
        category="Chapter Production",
    ),
    Command(
        "review",
        "Launch the Narration Reviewer web UI to flag narration issues (writes narration_review.json), "
        "looping for as many rounds as you want before continuing to voice synthesis",
        _h_review,
        [_PROJECT("Project name"), _CHAPTER()],
        category="Chapter Production",
    ),
    Command(
        "write",
        "Launch the Narration Writer web UI to hand-write narration.json yourself, instead of "
        "an LLM - same panel-by-panel layout as the Narration Reviewer, but each field is the "
        "narration text itself. Generates an empty narration.json, then fills it in from what "
        "you type as you save",
        _h_write,
        [_PROJECT("Project name"), _CHAPTER()],
        category="Chapter Production",
    ),
    Command(
        "crop",
        "Crop panels using coordinates in crops.json and package sheets.zip or panels.zip",
        _h_crop,
        [
            _PROJECT("Project name"), _CHAPTER(),
            Param("force", ["--force", "-f"], type="bool", default=False, help="Force re-cropping even if panels exist"),
        ],
        category="Chapter Production",
    ),
    Command(
        "package",
        "Build/rebuild sheets, sheets.zip, panels.zip, and/or panels.pdf from an already-cropped "
        "chapter's panels, per config.json's cropper.package switches - no re-crop needed",
        _h_package,
        [_PROJECT("Project name"), _CHAPTER()],
        category="Chapter Production",
    ),
    Command(
        "wipe",
        "Wipe everything for a chapter (source files and generated sheets/zips/audio/video) except "
        "whatever you choose to keep - unlike restart's fixed modes, any combination can be kept. "
        "Downloaded pages are always re-verified/re-fetched afterward. See wipe-chapters (Project-wide) "
        "for multiple chapters at once.",
        _h_wipe,
        [
            _PROJECT("Project name"), _CHAPTER(),
            Param(
                "keep", ["--keep", "-k"], required=False, default=None,
                help="Comma-separated names of items to keep (e.g. pages,narration.json) - see the "
                     "wizard's numbered listing for what actually exists on a given chapter, or run "
                     "`status`/look in the chapter's folder. Left unset (the default): keeps "
                     f"{', '.join(sorted(DEFAULT_WIPE_KEEP))} - the downloaded pages, marks, and "
                     "narration script, wiping only what's cheaply regenerated from them. Pass 'none' "
                     "to wipe absolutely everything instead.",
            ),
            Param("force", ["--force", "-f"], type="bool", default=False, help="Skip the confirmation prompt"),
        ],
        category="Chapter Production",
    ),
    Command(
        "tts",
        "Generate vocal audio via IndexTTS-2.5 from narration.json",
        _h_tts,
        [
            _PROJECT("Project name"), _CHAPTER(),
            Param("voice", ["--voice", "-v"], required=False, default=None, help="Override reference speaker WAV path"),
            Param("force", ["--force", "-f"], type="bool", default=False, help="Force re-synthesis of all panels"),
        ],
        category="Chapter Production",
    ),
    Command(
        "mix",
        "Mix narration, apply edge fades, BGM, and normalize",
        _h_mix,
        [
            _PROJECT("Project name"), _CHAPTER(),
            Param("bgm", ["--bgm", "-b"], required=False, default=None, help="Override background music audio path"),
        ],
        category="Chapter Production",
    ),
    Command(
        "render",
        "Render final recap MP4 video",
        _h_render,
        [
            _PROJECT("Project name"), _CHAPTER(),
            Param("force", ["--force", "-f"], type="bool", default=False, help="Force re-rendering video"),
        ],
        category="Chapter Production",
    ),
    Command(
        "full-recap",
        "Compile every chapter of a project into ONE continuous recap video "
        "(single BGM pass, single loudnorm pass - no per-chapter restarts/joins)",
        _h_full_recap,
        [
            _PROJECT("Project name"),
            Param("chapters", ["--chapters", "-c"], required=False, default=None,
                  help="Comma-separated chapter numbers to include, in any order (default: every chapter found, in order)"),
            Param("force", ["--force", "-f"], type="bool", default=False, help="Force a full recompile even if already compiled"),
        ],
        category="Project-wide",
    ),
    Command(
        "remix",
        "Re-mix + re-render a project's chapter video(s) after a BGM/volume change - "
        "no re-narration, no re-cropping, and re-joins the full-recap video if one exists",
        _h_remix,
        [
            _PROJECT("Project name"),
            Param("chapters", ["--chapters", "-c"], required=False, default=None,
                  help="Comma-separated chapter numbers to remix (default: every chapter found)"),
            Param("bgm", ["--bgm", "-b"], required=False, default=None, help="Override background music audio path"),
            Param("no_rejoin", ["--no-rejoin"], type="bool", default=False,
                  help="Don't recompile the full-recap video even if one exists"),
        ],
        category="Project-wide",
    ),
    Command(
        "run",
        "Run this project's pipeline.json (or the full default step order, if it has none) for "
        "one chapter, or an explicit --steps subset/order instead - 'just one tool', 'a lot of "
        f"them', or a full custom pipeline. Steps: {', '.join(s.name for s in STEP_REGISTRY)}",
        _h_run,
        [
            _PROJECT("Project name"), _CHAPTER(),
            Param("steps", ["--steps", "-s"], required=False, default=None,
                  help="Comma-separated step names to run, in order (one-off override - doesn't touch "
                       "pipeline.json). Default: this project's saved pipeline.json, or the full default "
                       f"order if it has none ({', '.join(s.name for s in STEP_REGISTRY)})."),
        ],
        category="Chapter Production",
    ),
    Command(
        "status",
        "Inspect chapter production status",
        _h_status,
        [_PROJECT("Project name"), _CHAPTER()],
        category="Project-wide",
    ),
    Command(
        "verify",
        "Strictly verify every chapter's audio/video is complete and decodable, not just present on disk "
        "(catches a file left truncated by a kill mid-write) - reports exactly what to re-run, if anything",
        _h_verify,
        [
            _PROJECT("Project name"),
            Param("chapters", ["--chapters", "-c"], required=False, default=None,
                  help="Comma-separated chapter numbers to verify (default: every chapter found)"),
            Param("no_video", ["--no-video"], type="bool", default=False,
                  help="Skip verifying rendered videos, audio only (faster)"),
        ],
        category="Project-wide",
    ),
    Command(
        "restart",
        "Wipe a chapter back to just its downloaded pages so it can be reprocessed from scratch",
        _h_restart,
        [
            _PROJECT("Project name"), _CHAPTER(),
            Param("force", ["--force", "-f"], type="bool", default=False, help="Skip the confirmation prompt"),
            Param(
                "mode", ["--mode", "-m"], type="choice", default="hard",
                choices=["hard", "marks_only", "remark", "soft"],
                help="hard (default): keep only downloaded pages. marks_only: also keep crops.json, "
                     "narration.json still gets wiped/emptied. remark: same deletion as marks_only, then "
                     "reopens the Panel Marker web UI (pre-loaded with the kept marks) so you can adjust "
                     "them. soft: also keep crops.json, panels/, and narration.json.",
            ),
            Param("no_reverify", ["--no-reverify"], type="bool", default=False,
                  help="Skip re-checking/re-fetching downloaded pages afterward"),
        ],
        category="Project-wide",
    ),
    Command(
        "wipe-chapters",
        "Wipe multiple chapters at once (comma list and/or 'N-M' ranges, e.g. '1,3,7-9') - same "
        "dynamic keep-anything behavior as `wipe`, one confirmation covering every selected chapter.",
        _h_wipe_chapters,
        [
            _PROJECT("Project name"),
            Param(
                "chapters", ["--chapters", "-c"], required=True,
                help="Chapter numbers to wipe: comma-separated, numeric ranges allowed (e.g. '1,3,7-9'). "
                     "A range only expands against chapters this project actually has.",
            ),
            Param(
                "keep", ["--keep", "-k"], required=False, default=None,
                help="Same as `wipe`'s --keep - comma-separated names to keep, or 'none' for a full wipe. "
                     f"Left unset (the default): keeps {', '.join(sorted(DEFAULT_WIPE_KEEP))} in every "
                     "selected chapter.",
            ),
            Param("force", ["--force", "-f"], type="bool", default=False, help="Skip the confirmation prompt"),
        ],
        category="Project-wide",
    ),
]

COMMAND_BY_NAME = {cmd.name: cmd for cmd in COMMAND_REGISTRY}
