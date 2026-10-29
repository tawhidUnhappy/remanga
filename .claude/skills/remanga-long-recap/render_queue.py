"""Renders a project's chapters in order as their narration becomes ready, then (with --long) joins the
long video and stamps the upload set - the background half of a long recap, so one chapter renders while
the next is being narrated.

    setsid nohup env PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/render_queue.py \
        P [CHAPTERS] [--long] >> projects/P/logs/render_queue.log 2>&1 < /dev/null &

A chapter renders (./run.sh video) once Make video's check says its narration is ok, and again whenever
narration.json changes after it was narrated; a chapter whose video already says what narration.json says
is skipped. verify.py checks every chapter after its render. It waits while another render or MAGI run
holds the GPU (Drama 3 needs all 12 GB) and runs once per project (a lock in logs/). A chapter that fails
twice, or fails its check, is left for a look and the long video is not joined; the log ends "EXIT n".
After a power-off just start it again: every finished take comes back from the store.
With CHAPTERS (1-14), --long joins exactly those - a long video of the story so far while the rest wait."""
from __future__ import annotations

import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path

from remanga.chapters import discover_chapters, expand_chapter_selection
from remanga.config import RemangaConfig
from remanga.paths import get_final_video_path, get_project_dir
from remanga.workflow.video import check_chapter

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
POLL_SECONDS = 30
TRIES = 2
GPU_USERS = ("remanga.cli video", "remanga.cli long", "drama3_worker.py", "speech worker", "detect.py")
CHANGED = "narration.json has changed since it was narrated"


def say(line: str) -> None:
    print(f"=== {time.strftime('%Y-%m-%d %I:%M:%S %p')}  {line}", flush=True)


def gpu_user() -> str | None:
    """Another process that needs the GPU (a render, a long join, MAGI), or None."""
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            command = (proc / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except OSError:
            continue
        if "render_queue.py" not in command and any(user in command for user in GPU_USERS):
            return f"pid {proc.name}: {command.strip()[:100]}"
    return None


def chapter_state(project: str, chapter: str, config: RemangaConfig) -> tuple[bool, bool, str]:
    """(rendered, ready to render, why not ready)."""
    result = check_chapter(project, chapter, config)
    narrated = not any("not narrated yet" in note for note in result["notes"])
    rendered = result["state"] == "ok" and narrated and get_final_video_path(project, chapter, create=False).exists()
    changed = bool(result["errors"]) and all(error.startswith(CHANGED) for error in result["errors"])
    ready = result["state"] == "ok" or changed
    return rendered, ready, "; ".join(result["notes"] + result["errors"])[:200]


def run(command: list[str]) -> int:
    say("$ " + " ".join(command))
    return subprocess.run(command, cwd=REPO, check=False).returncode


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    project = args[0]
    every = discover_chapters(project)
    chapters = [str(c) for c in (expand_chapter_selection(args[1], every) if len(args) > 1 and args[1] != "all"
                                 else every)]
    logs = get_project_dir(project) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    lock = (logs / "render_queue.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        say("another render queue is already running for this project - leaving it to that one")
        return
    config = RemangaConfig.load()
    join = "--long" in sys.argv
    say(f"render queue for {project}: chapters {chapters[0]}-{chapters[-1]} ({len(chapters)})"
        + (", then the long video" if join else ""))
    failures: dict[str, int] = {}
    told = None
    while True:
        todo = None
        for chapter in chapters:
            if failures.get(chapter, 0) >= TRIES:
                continue
            rendered, ready, why = chapter_state(project, chapter, config)
            if not rendered:
                todo = (chapter, ready, why)
                break
        if todo is None:
            break
        chapter, ready, why = todo
        busy = gpu_user() if ready else None
        if not ready or busy:
            news = f"chapter {chapter}: waiting for " + (f"the GPU ({busy})" if busy else f"its narration ({why})")
            if news != told:
                say(news)
                told = news
            time.sleep(POLL_SECONDS)
            continue
        told = None
        say(f"chapter {chapter}: rendering")
        code = run(["./run.sh", "video", "-p", project, "-c", chapter])
        if code:
            failures[chapter] = failures.get(chapter, 0) + 1
            say(f"chapter {chapter}: FAILED (exit {code}, try {failures[chapter]} of {TRIES})")
            continue
        if run([sys.executable, str(HERE / "verify.py"), project, chapter]):
            failures[chapter] = TRIES
            say(f"chapter {chapter}: rendered but its CHECK FAILED - left for a look")
            continue
        say(f"chapter {chapter}: rendered and checked")
    failed = sorted(failures, key=chapters.index)
    if failed:
        say(f"NOT JOINING - chapters needing a look: {', '.join(failed)}")
        print("EXIT 1", flush=True)
        sys.exit(1)
    code = 0
    if join:
        say("every chapter rendered - joining the long video")
        selection = args[1] if len(args) > 1 else "all"  # the long video is of the chapters asked for
        code = (run(["./run.sh", "long", "-p", project, "-c", selection])
                or run(["./run.sh", "upload", "-p", project])
                or run([sys.executable, str(HERE / "verify.py"), project, selection]))
    say("finished")
    print(f"EXIT {code}", flush=True)
    sys.exit(code)


if __name__ == "__main__":
    main()
