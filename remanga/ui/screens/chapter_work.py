"""What the chapter menu actually does: download, mark the panels, make the
PDF, make the video - each shown as a task and ending on a result.

A mixin rather than free functions: every one of these runs AS the chapters
screen (it pushes the task and result screens and reloads the table
afterwards), and mixing them in keeps that without passing the screen
around."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text

from remanga import workflow
from remanga.config import RemangaConfig
from remanga.paths import get_audio_dir, get_log_path
from remanga.ui.dialogs import Result
from remanga.ui.screens.common import _short
from remanga.ui.tasks import Step, TaskOutcome, TaskScreen


class ChapterWork:
    """The chapters screen's other half: the steps behind its menu."""

    async def run_task(self, title: str, steps: list[Step], log: Path) -> TaskOutcome:
        return await self.app.push_screen_wait(TaskScreen(self.path, title, steps, log))

    async def show(self, title: str, lines: list, **kwargs: Any) -> None:
        await self.app.push_screen_wait(Result(self.path, title, lines, **kwargs))

    async def download(self, chapters: list[str], force: bool = False) -> None:
        project, config, log = self.project, self.config, get_log_path(self.project)
        outcome = await self.run_task(
            f"Downloading {len(chapters)} chapter(s)",
            [Step(f"Chapter {ch}", lambda ch=ch: workflow.download(project, [ch], config, force=force))
             for ch in chapters], log)
        if outcome.ok:
            await self.show("Downloaded", [f"Chapter(s) {', '.join(chapters)} - every page checked against "
                                           f"MangaDex."], ok=True, log=log)
        else:
            await self.show("Download stopped" if outcome.stopped else "Download failed", [outcome.error],
                            ok=False, log=log)

    async def mark(self, chapters: list[str], config: RemangaConfig) -> None:
        """The browser does the work; the task screen just waits for it."""
        project, log = self.project, get_log_path(self.project)
        outcome = await self.run_task(
            f"Marking {len(chapters)} chapter(s)",
            [Step("Panel Marker (waiting for the browser)", lambda: workflow.mark(project, chapters, config))], log)
        if outcome.ok:
            marked = [ch for ch in chapters if workflow.has_marks(project, ch)]
            await self.show("Panels marked", [f"Chapter(s) {', '.join(marked) or '-'} have their panels marked.",
                                              "", Text("Then Make PDF for the chapter.", style="dim")],
                            ok=True, log=log)
        else:
            await self.show("Marking stopped" if outcome.stopped else "Marking failed", [outcome.error],
                            ok=False, log=log)

    async def narration_pass(self, which: str, chapters: list[str], config: RemangaConfig) -> None:
        """The browser passes over the narration: writing it, or reviewing it.
        One chapter at a time - each is its own tab and its own file."""
        project = self.project
        writing = which == "write"
        title = "Writing the narration" if writing else "Reviewing the narration"
        step = workflow.write_narration if writing else workflow.review_narration
        for chapter in chapters:
            log = get_log_path(project, chapter)
            outcome = await self.run_task(
                f"Chapter {chapter}: {title.lower()}",
                [Step("Waiting for the browser", lambda ch=chapter: step(project, ch, config))], log)
            if not outcome.ok:
                await self.show(f"{title} {'stopped' if outcome.stopped else 'failed'}", [outcome.error],
                                ok=False, log=log)
                return
            written = _short(outcome.results[0])
            lines: list[str | Text] = [f"Chapter {chapter}: {written}"]
            if writing:
                lines += ["", Text("Then Make video for the chapter.", style="dim")]
            else:
                lines += ["", Text("Give that file to the LLM with prompts/narration_review.md, and paste the "
                                   "new reply into narration.json.", style="dim")]
            await self.show("Narration saved" if writing else "Review saved", lines, ok=True, log=log,
                            copy=[written])

    async def make_pdfs(self, chapters: list[str], config: RemangaConfig) -> None:
        project = self.project
        for chapter in chapters:
            log = get_log_path(project, chapter)
            outcome = await self.run_task(f"Chapter {chapter}: PDF", [
                Step("Cut the panels and build their PDF",
                     lambda ch=chapter: workflow.make_pdf(project, ch, config)),
            ], log)
            if not outcome.ok:
                await self.show(f"Chapter {chapter}: PDF {'stopped' if outcome.stopped else 'failed'}",
                                [outcome.error], ok=False, log=log)
                return
            result = outcome.results[0]
            files = [_short(result.prompt), *[_short(p) for p in result.parts]]
            lines: list[str | Text] = [
                Text("Give the LLM these files:", style="bold"), *[f"  {f}" for f in files], "",
                Text("Paste its whole reply into:", style="bold"), f"  {_short(result.narration)}", "",
                Text("Then pick the chapter and Make video.", style="dim"),
            ]
            if result.story_from:
                lines[:0] = [Text(f"Story so far carried from chapter {result.story_from}.", style="dim"), ""]
            await self.show(f"Chapter {chapter}: PDF ready", lines, ok=True, warnings=result.warnings(), log=log,
                            copy=[*files, _short(result.narration)])

    async def remix_videos(self, chapters: list[str], config: RemangaConfig) -> None:
        """A new mix and render from the narration already on disk."""
        project = self.project
        for chapter in chapters:
            log = get_log_path(project, chapter)
            outcome = await self.run_task(f"Chapter {chapter}: rebuilding the video (narration kept)", [
                Step("Mix the kept narration with the music, render, add the intro",
                     lambda ch=chapter: workflow.remix_video(project, ch, config)),
            ], log)
            if not outcome.ok:
                await self.show(f"Chapter {chapter}: remix {'stopped' if outcome.stopped else 'failed'}",
                                outcome.error.splitlines(), ok=False, log=log)
                return
            video = _short(outcome.results[-1])
            await self.show(f"Chapter {chapter}: video ready", [video], ok=True, log=log, copy=[video])

    async def make_videos(self, chapters: list[str], config: RemangaConfig, force: bool = False,
                         audio_only: bool = False) -> None:
        project = self.project
        verb = "narrating again" if audio_only else ("narrating and making the video" if force else "video")
        for chapter in chapters:
            log = get_log_path(project, chapter)
            found: dict[str, Any] = {}

            def check(ch: str = chapter, found: dict = found) -> list:
                found["panels"], found["warnings"] = workflow.check_narration(project, ch)
                found["warnings"] += workflow.quality_warnings(project, ch, config, found["panels"])
                return found["panels"]

            steps = [
                Step("Check the narration", check),
                Step(f"Narrate the panels ({config.tts.spec.display_name})",
                     lambda ch=chapter, found=found: workflow.narrate(project, ch, found["panels"], config, force)),
                Step("Mix with the music", lambda ch=chapter: workflow.mix(project, ch, config, force)),
                Step("Render the video", lambda ch=chapter: workflow.render(project, ch, config, force)),
            ]
            if audio_only:
                # Mixing and rendering run anyway - it's how a changed voice
                # or narration is proven good end to end - but only the raw
                # clips are worth keeping afterwards; the mix and the render
                # come back later from them (Rebuild video) rather
                # than sitting on disk twice.
                steps.append(Step("Keep the new narration, delete the test mix and video",
                                  lambda ch=chapter: workflow.drop_mix_and_video(project, ch)))
            outcome = await self.run_task(f"Chapter {chapter}: {verb}", steps, log)
            if not outcome.ok:
                await self.show(f"Chapter {chapter}: {'audio' if audio_only else 'video'} "
                                f"{'stopped' if outcome.stopped else 'failed'}",
                                outcome.error.splitlines(), ok=False, log=log)
                return
            if audio_only:
                audio_dir = _short(get_audio_dir(project, chapter))
                await self.show(f"Chapter {chapter}: narration ready", [audio_dir], ok=True,
                                warnings=found.get("warnings", []), log=log, copy=[audio_dir])
            else:
                video = _short(outcome.results[-1])
                await self.show(f"Chapter {chapter}: video ready", [video], ok=True,
                                warnings=found.get("warnings", []), log=log, copy=[video])
