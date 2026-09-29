"""The queue screen: jobs lined up across projects, and running them.

Jobs are added from a chapter's menu (Add to queue) in any project; this
screen lists them in the order they run, lets them be reordered or removed,
and runs everything not done yet in one task screen - a job that fails is
marked and the next one starts."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Footer

from remanga.config import RemangaConfig
from remanga.ui.dialogs import Confirm, Result
from remanga.ui.screens.common import _global_log
from remanga.ui.tasks import Step, TaskOutcome, TaskScreen
from remanga.ui.widgets import SafeTable, TopBar
from remanga.workflow.queue import DONE, FAILED, Job, load_queue, record, run_job, save_queue, to_run

_STATE = {"waiting": ("· waiting", "cyan"), DONE: ("✓ done", "green"), FAILED: ("✗ failed", "red")}


class QueueScreen(Screen):
    BINDINGS = [
        Binding("r", "run", "Run queue"),
        Binding("x,delete", "remove", "Remove"),
        Binding("shift+up", "move(-1)", "Move up"),
        Binding("shift+down", "move(1)", "Move down"),
        Binding("c", "clear", "Clear finished"),
        Binding("escape", "back", "Back"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self, machine: RemangaConfig, path: list[str]) -> None:
        super().__init__()
        self.machine = machine
        self.path = [*path, "Queue"]
        self.jobs: list[Job] = []

    def compose(self) -> ComposeResult:
        yield TopBar(self.path)
        yield SafeTable(id="queue")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(SafeTable)
        for label, width in (("State", 9), ("Project", 36), ("Ch", 6), ("Job", 24), ("Note", None)):
            table.add_column(label, width=width)
        self.load()
        table.focus()

    def on_screen_resume(self) -> None:
        self.load()

    def load(self, cursor: int | None = None) -> None:
        table = self.query_one(SafeTable)
        row = cursor if cursor is not None else table.picked_row
        table.clear()
        self.jobs = load_queue()
        for job in self.jobs:
            label, style = _STATE[job.state]
            note = (job.error.splitlines()[0] if job.error else
                    f"finished {job.finished}" if job.finished else f"added {job.added}")
            table.add_row(Text(label, style=style), job.project, job.chapter, job.label,
                          Text(note, style="red" if job.error else "dim"))
        if row is not None and self.jobs:
            table.show_cursor = True
            table.move_cursor(row=max(0, min(row, len(self.jobs) - 1)))
        pending = len(to_run(self.jobs))
        self.query_one(TopBar).set_info(
            f"{pending} to run · {len(self.jobs) - pending} done" if self.jobs else
            "empty - pick chapters in a project and choose Add to queue")

    def action_remove(self) -> None:
        row = self.query_one(SafeTable).picked_row
        if row is None:
            return
        del self.jobs[row]
        save_queue(self.jobs)
        self.load(cursor=row)

    def action_move(self, step: int) -> None:
        row = self.query_one(SafeTable).picked_row
        if row is None or not 0 <= row + step < len(self.jobs):
            return
        self.jobs[row], self.jobs[row + step] = self.jobs[row + step], self.jobs[row]
        save_queue(self.jobs)
        self.load(cursor=row + step)

    def action_clear(self) -> None:
        save_queue([job for job in self.jobs if job.state != DONE])
        self.load()

    def action_back(self) -> None:
        self.dismiss()

    @work(exclusive=True)
    async def action_run(self) -> None:
        jobs = to_run(self.jobs)
        if not jobs:
            self.notify("Nothing to run - every job in the queue is done.")
            return
        if not await self.app.push_screen_wait(Confirm(
                "Run queue", f"Run {len(jobs)} job(s) one after another? A job that fails is marked and the "
                f"next one starts; Ctrl+C stops the run and leaves the rest waiting.", yes="Run")):
            return
        log = _global_log()
        outcome: TaskOutcome = await self.app.push_screen_wait(TaskScreen(
            self.path, f"Running the queue ({len(jobs)} job(s))",
            [Step(job.title, lambda job=job: self._run(job)) for job in jobs], log, keep_going=True))
        self.load()
        failed = [job for job in load_queue() if job.state == FAILED]
        if outcome.stopped:
            await self.app.push_screen_wait(Result(self.path, "Queue stopped", [
                "Stopped with Ctrl+C. The jobs not finished are still waiting - r runs them."], ok=False, log=log))
        elif failed:
            await self.app.push_screen_wait(Result(self.path, f"Queue finished, {len(failed)} failed",
                                                   [f"{job.title} - {job.error}" for job in failed],
                                                   ok=False, log=log))
        else:
            await self.app.push_screen_wait(Result(self.path, "Queue finished", [
                f"All {len(jobs)} job(s) done."], ok=True, log=log))
        self.load()

    def _run(self, job: Job) -> object:
        try:
            result = run_job(job, self.machine)
        except Exception as error:
            record(job, str(error) or type(error).__name__)
            raise
        record(job, None)
        return result
