"""`auto`: a run of chapters from download to rendered video, where the only
thing a person does is the Gemini hand-offs - uploading, and pasting replies.

Nothing waits for Enter. Every chapter's next stage is read off disk each
tick, so `auto` can be stopped and started again at any point and picks up
where things are:

    download -> grid (MAGI labels) -> [crop reply pasted] -> import + cut
    -> package -> [narration.json + memory.json pasted] -> tts -> mix -> render

Stages in brackets are the hand-offs. When a chapter reaches one, its upload
is listed once, and `auto` watches the files: a reply saved into
llm_crops.json is checked and imported as soon as it lands (a reply that
doesn't check out gets its fix request written and is watched for the
corrected one); a narration.json that matches the panels is voiced, mixed
and rendered. Meanwhile every other chapter keeps moving, so all of a run's
crop uploads can go to Gemini at once.

Narration is handed off in chapter order, because each chapter's narration
needs memory.json as the chapter before it left it.

The steps a person would otherwise sit through - the Panel Marker, the pause
stage, the review loop - are not part of this. A stage that fails is
reported and the chapter is left alone until one of its source files
changes, so one bad chapter doesn't stop the others."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.json_io import has_real_json_content
from remanga.paths import (
    get_audio_timing_path,
    get_chapter_dir,
    get_final_video_path,
    get_master_audio_path,
    get_memory_path,
    get_panels_pdf_dir,
    get_panels_zip_dir,
    get_sheets_dir,
    get_sheets_zip_dir,
)

POLL_SECONDS = 4

WAIT_CROP_REPLY = "waiting for Gemini's crop reply"
WAIT_FIXED_REPLY = "waiting for a corrected crop reply"
WAIT_NARRATION = "waiting for narration.json + memory.json"
WAIT_EARLIER_NARRATION = "waiting for the chapter before it to be narrated"
WAIT_MATCHING_NARRATION = "waiting for a narration.json that matches the panels"
BLOCKED = "stopped by an error - fix it or change a file to retry"
DONE = "done"


def _mtime(path: Path) -> float:
    return path.stat().st_mtime if path.exists() else 0.0


@dataclass
class ChapterRun:
    chapter: str
    state: str = ""
    # The file state a hand-off or failure was last seen at, so an unchanged
    # file is neither re-checked nor re-announced every tick.
    seen: tuple = ()
    detail: str = ""
    announced: set[str] = field(default_factory=set)


class AutoRun:
    def __init__(self, project: str, chapters: list[str], config: RemangaConfig):
        from remanga.extensions.llm_crop.handoff import llm_config
        from remanga.settings.project_prefs import cropper_config_for

        self.project = project
        self.config = config
        self.llm = llm_config(config)
        self.cropper = cropper_config_for(config, project)
        self.runs = [ChapterRun(chapter) for chapter in chapters]
        self._board_stale = True

    # --- what a chapter has on disk ----------------------------------------

    def _dir(self, chapter: str) -> Path:
        return get_chapter_dir(self.project, chapter)

    def _files(self, chapter: str) -> tuple:
        """The source files a person changes - what un-sticks a chapter."""
        from remanga.extensions.llm_crop.paths import get_llm_crops_path

        chapter_dir = self._dir(chapter)
        return (_mtime(get_llm_crops_path(self.project, chapter)), _mtime(chapter_dir / "crops.json"),
                _mtime(chapter_dir / "narration.json"), _mtime(get_memory_path(self.project)))

    def _has_pages(self, chapter: str) -> bool:
        pages = self._dir(chapter) / "pages"
        return pages.exists() and any(p.is_file() for p in pages.iterdir())

    def _panels(self, chapter: str) -> list[Path]:
        panels = self._dir(chapter) / "panels"
        return sorted(p for p in panels.iterdir() if p.is_file()) if panels.exists() else []

    def _package_current(self, chapter: str) -> bool:
        """Every active upload format built, and built after the panels were."""
        from remanga.cropper.llm_bundles import is_up_to_date

        if not is_up_to_date(self.cropper, self.project, chapter):
            return False
        panels = self._panels(chapter)
        newest_panel = max((_mtime(p) for p in panels), default=0.0)
        outputs = [p for d in (get_panels_zip_dir(self.project, chapter, create=False),
                               get_panels_pdf_dir(self.project, chapter, create=False),
                               get_sheets_zip_dir(self.project, chapter, create=False),
                               get_sheets_dir(self.project, chapter, create=False))
                   if d.exists() for p in d.iterdir() if p.is_file()]
        return all(_mtime(p) >= newest_panel for p in outputs)

    def _narrated(self, chapter: str) -> bool:
        return has_real_json_content(self._dir(chapter) / "narration.json")

    # --- one chapter's next stage ------------------------------------------

    def _next(self, run: ChapterRun, index: int) -> tuple[str, Callable[[], None] | None]:
        """(state, the work to do now or None when waiting)."""
        from remanga.extensions.llm_crop.bundles import grid_built
        from remanga.extensions.llm_crop.paths import get_llm_crops_path

        chapter, project = run.chapter, self.project
        if not self._has_pages(chapter):
            return "downloading", lambda: self._download(chapter)

        crops_path = self._dir(chapter) / "crops.json"
        reply = get_llm_crops_path(project, chapter)
        reply_pasted = has_real_json_content(reply)
        crops_current = has_real_json_content(crops_path) and (not reply_pasted or _mtime(crops_path) >= _mtime(reply))
        if not crops_current:
            if not reply_pasted:
                if not grid_built(self.llm, project, chapter):
                    return "building the grid upload", lambda: self._grid(chapter)
                return WAIT_CROP_REPLY, None
            if run.state == WAIT_FIXED_REPLY and run.seen == self._files(chapter):
                return WAIT_FIXED_REPLY, None
            return "importing Gemini's crops", lambda: self._import(run)
        if not self._panels(chapter):
            return "cutting panels", lambda: self._cut(chapter)
        if not self._package_current(chapter):
            return "packaging", lambda: self._package(chapter)

        if not self._narrated(chapter):
            earlier = [r.chapter for r in self.runs[:index] if not self._narrated(r.chapter)]
            return (WAIT_EARLIER_NARRATION, None) if earlier else (WAIT_NARRATION, None)

        from remanga.verify.panels import check_panel_narration_mismatch

        issue = check_panel_narration_mismatch(project, chapter)
        if issue:
            run.detail = issue
            return WAIT_MATCHING_NARRATION, None
        if not get_audio_timing_path(project, chapter, create=False).exists():
            return "voicing (tts)", lambda: self._tts(chapter)
        if not get_master_audio_path(project, chapter, create=False).exists():
            return "mixing", lambda: self._mix(chapter)
        if not get_final_video_path(project, chapter, create=False).exists():
            return "rendering", lambda: self._render(chapter)
        return DONE, None

    # --- the work ------------------------------------------------------------

    def _download(self, chapter: str) -> None:
        from remanga.downloader import MangaDexDownloader

        MangaDexDownloader(self.config.downloader).download_chapter(None, chapter, self.project)

    def _grid(self, chapter: str) -> None:
        from remanga.extensions.llm_crop.bundles import build_grid_bundles

        build_grid_bundles(self.llm, self.project, chapter, self.config.marker)

    def _import(self, run: ChapterRun) -> None:
        from remanga.extensions.llm_crop.reply_import import import_llm_crops

        # Pasting a reply into an auto run is the decision to use it, over
        # any marks the chapter had.
        outcome = import_llm_crops(self.llm, self.cropper, self.project, run.chapter, replace_marks=True)
        if outcome.state == "invalid":
            run.state, run.seen = WAIT_FIXED_REPLY, self._files(run.chapter)
            console.print(f"[yellow]Chapter {run.chapter}: paste the fix request into the same Gemini chat, and "
                          f"its corrected reply over llm_crops.json:[/] {_esc(str(outcome.fix_path))}")

    def _cut(self, chapter: str) -> None:
        from remanga.cropper.crop import CoordinateCropper

        CoordinateCropper(self.cropper).crop_chapter_from_json(self.project, chapter, force=True)

    def _package(self, chapter: str) -> None:
        from remanga.packaging import package_chapter

        package_chapter(self.config, self.project, chapter, required=False)

    def _tts(self, chapter: str) -> None:
        from remanga.audio import TTSEngine

        TTSEngine(self.config.tts, self.config.audio).generate_narration_audio(self.project, chapter, interactive=False)

    def _mix(self, chapter: str) -> None:
        from remanga.audio import AudioProcessor

        AudioProcessor(self.config.audio).mix_master_audio(self.project, chapter, interactive=False)

    def _render(self, chapter: str) -> None:
        from remanga.video import VideoRenderer

        path = VideoRenderer(self.config.system, self.config.video).render_video(self.project, chapter)
        console.print(f"[bold green]✓ Chapter {chapter} rendered:[/] {_esc(str(path))}")

    # --- hand-offs ------------------------------------------------------------

    def _announce(self, run: ChapterRun, state: str) -> None:
        """Lists a hand-off's upload the first time a chapter reaches it."""
        if state in run.announced:
            return
        run.announced.add(state)
        if state == WAIT_CROP_REPLY:
            from remanga.extensions.llm_crop.handoff import print_llm_crop_handoff

            print_llm_crop_handoff(self.project, run.chapter, self.config)
        elif state == WAIT_NARRATION:
            from remanga.wizard.narration import print_narration_handoff

            print_narration_handoff(self.project, run.chapter, self.config)
        elif state == WAIT_MATCHING_NARRATION:
            console.print(f"[yellow]Chapter {run.chapter}'s narration.json doesn't match its panels:[/] "
                          f"{_esc(run.detail)}")

    # --- the loop -----------------------------------------------------------

    def tick(self) -> bool:
        """Advances every chapter as far as it can go right now. True when
        some work was done (so the next tick runs straight away)."""
        worked = False
        for index, run in enumerate(self.runs):
            if run.state == BLOCKED:
                if run.seen == self._files(run.chapter):
                    continue
                run.state = ""
            state, work = self._next(run, index)
            if work is None:
                if state != run.state:
                    run.state = state
                    self._board_stale = True
                    try:
                        self._announce(run, state)
                    except Exception as error:
                        run.state, run.seen = BLOCKED, self._files(run.chapter)
                        console.print(f"[bold red]✗ Chapter {run.chapter}: {state} failed:[/] {_esc(str(error))}")
                continue
            console.print(f"\n[bold cyan]Chapter {run.chapter}: {state}[/]")
            run.state = state
            try:
                work()
            except Exception as error:  # one chapter's failure must not stop the others
                run.state, run.seen = BLOCKED, self._files(run.chapter)
                console.print(f"[bold red]✗ Chapter {run.chapter}: {state} failed:[/] {_esc(str(error))}")
            worked = self._board_stale = True
            # One stage per tick, then look at every chapter again: a reply
            # saved meanwhile for another chapter gets its turn.
            break
        return worked

    def _print_board(self) -> None:
        console.print("\n[bold]auto — where every chapter is[/] [dim](Ctrl+C stops; run again to resume)[/]")
        for run in self.runs:
            style = "green" if run.state == DONE else "yellow" if run.state.startswith("waiting") else \
                "red" if run.state == BLOCKED else "cyan"
            console.print(f"  chapter {run.chapter:>6}  [{style}]{run.state}[/]")

    def run(self) -> None:
        while True:
            if self.tick():
                continue
            if self._board_stale:
                self._print_board()
                self._board_stale = False
            if all(run.state == DONE for run in self.runs):
                console.print(f"\n[bold green]✓ All {len(self.runs)} chapter(s) rendered.[/]")
                return
            time.sleep(POLL_SECONDS)
