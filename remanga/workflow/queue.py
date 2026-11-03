"""The job queue: work on chapters of any project, lined up to run one after
another without anyone at the keyboard (user request, 2026-09-29).

A job is one chapter of one project and one thing to do to it - only the
things that run unattended. Marking, writing and reviewing wait on the
browser, so they are not jobs.

The queue lives in projects/queue.json, so it survives closing the menus, and
the menus (ui/screens/queue.py) and the command line (`remanga queue`) read
the same file and run jobs through the same run_job."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from remanga import plugins
from remanga.config import RemangaConfig
from remanga.json_io import read_json_or, write_json

QUEUE_PATH = Path("projects") / "queue.json"

def jobs() -> dict[str, tuple[str, str]]:
    """action -> (what the queue calls it, what it does), from the "job"
    plug-ins (plugins/jobs/ has the built-in ones), in their order."""
    return {job.name: (job.label, job.help) for job in plugins.items("job")}


WAITING, DONE, FAILED = "waiting", "done", "failed"


@dataclass
class Job:
    project: str
    chapter: str
    action: str
    state: str = WAITING
    error: str = ""
    added: str = ""
    finished: str = ""
    # Which row of the queue file this is, so a finished job is written back
    # to itself and not to another job doing the same work.
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def label(self) -> str:
        return plugins.get("job", self.action).label

    @property
    def title(self) -> str:
        return f"{self.project} · ch {self.chapter}: {self.label}"

    def same_work(self, other: Job) -> bool:
        return (self.project, self.chapter, self.action) == (other.project, other.chapter, other.action)


def load_queue() -> list[Job]:
    rows = [row for row in read_json_or(QUEUE_PATH, []) or []
            if isinstance(row, dict) and plugins.find("job", row.get("action"))]
    jobs = [Job(**row) for row in rows]
    if any("id" not in row for row in rows):
        # A row with no id got a new one just now; kept, or the next load
        # would give it another and record() could never find it again.
        save_queue(jobs)
    return jobs


def save_queue(jobs: list[Job]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_json(QUEUE_PATH, [asdict(job) for job in jobs])


def add_jobs(project: str, chapters: list[str], action: str) -> int:
    """Queues `action` for each chapter; returns how many were new. A job
    already waiting for the same work is not queued twice - one that already
    ran (done or failed) is, since asking again means running it again."""
    jobs = load_queue()
    added = 0
    for chapter in chapters:
        job = Job(project, chapter, action, added=f"{datetime.now():%Y-%m-%d %H:%M}")
        if any(j.state == WAITING and j.same_work(job) for j in jobs):
            continue
        jobs.append(job)
        added += 1
    save_queue(jobs)
    return added


def to_run(jobs: list[Job]) -> list[Job]:
    """What a run of the queue does: every job not done yet, failed ones
    again included, in queue order."""
    return [job for job in jobs if job.state != DONE]


def run_job(job: Job, machine: RemangaConfig) -> Any:
    """Does the job, with the settings as they are now."""
    from remanga import workflow

    action = plugins.find("job", job.action)
    if action is None:
        raise ValueError(f"Unknown job: {job.action} - its plug-in is not installed")
    if action.needs_pages and not workflow.page_files(job.project, job.chapter):
        raise FileNotFoundError(f"{job.project} chapter {job.chapter} is not downloaded - queue a Download first.")
    return plugins.call(action.run, job.project, job.chapter, machine)


def record(job: Job, error: str | None) -> None:
    """Writes how `job` ended into the queue file. Reloads first: the file,
    not the list the run started from, is the queue."""
    jobs = load_queue()
    for queued in jobs:
        if queued.id == job.id:
            queued.state = FAILED if error else DONE
            queued.error = error or ""
            queued.finished = f"{datetime.now():%Y-%m-%d %H:%M}"
            break
    save_queue(jobs)
