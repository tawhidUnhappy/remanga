#!/usr/bin/env python3
"""Keeps a long Claude Code job going across usage limits, closed editors and crashes.

Claude Code continues by itself when a usage limit resets (setting autoContinueAtUsageLimit, on unless
set false) - but only inside a session that stays open, and only for a reset less than 24 hours away.
This watchdog covers the rest. While the job's notes say STATE: RUNNING and no Claude session in WORKDIR
has written anything for --idle minutes, it starts Claude Code headless with a resume prompt. A run that
meets the usage limit is retried after the reset time it prints, plus --grace minutes, so that Claude
Code's own automatic continue gets the first chance.

    setsid nohup python3 continue_watchdog.py --notes /path/JOB_NOTES.md --workdir /mnt/datadisk \
        >> /path/watchdog.log 2>&1 < /dev/null &

The notes file is the contract (SKILL.md): a line `STATE: RUNNING | PAUSED | DONE`. DONE ends the
watchdog, anything but RUNNING makes it wait, and a file named STOP beside the notes stops it. It also
stops after --max-idle-runs finished runs in a row that left the notes unchanged, so a stuck job cannot
burn the usage. Headless runs log to headless-runs/ beside the notes; the one running now writes its PID
to .headless.pid there. Run with -I; standard library only."""
from __future__ import annotations

import argparse
import collections
import contextlib
import datetime as dt
import fcntl
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

STATE = re.compile(r"^\s*STATE:\s*([A-Za-z]+)", re.MULTILINE)
LIMIT = re.compile(r"usage limit|hit your limit|limit reached|out of usage|rate[ _-]?limit", re.IGNORECASE)
EPOCH = re.compile(r"(?:limit reached\||\"resets_?[aA]t\"\s*:\s*)(\d{10})")
ISO = re.compile(r"resets?\s+(?:at\s+)?(\d{4})-(\d{2})-(\d{2})[ T](\d{1,2}):(\d{2})\s*(UTC|Z)?", re.IGNORECASE)
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DATED = re.compile(r"resets?\s+(?:on\s+)?(" + "|".join(MONTHS) + r")[a-z]*\.?\s+(\d{1,2}),?\s*(?:at\s+)?"
                   r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b", re.IGNORECASE)
WEEKDAY = re.compile(r"resets?\s+(?:on\s+)?(" + "|".join(DAYS) + r")[a-z]*\.?,?\s*(?:at\s+)?"
                     r"(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m\b", re.IGNORECASE)
CLOCK = re.compile(r"resets?\s+(?:at\s+)?(\d{1,2})(?::(\d{2}))?\s*(?:([ap])\.?m\b)?", re.IGNORECASE)
UNKNOWN_WAIT = 60 * 60          # a limit whose reset time could not be read: look again in an hour
BETWEEN_RUNS = 60               # pause after a run that made progress

PROMPT = """You are continuing a long job on this machine that stopped - most likely a Claude usage limit that \
has now refilled, or a closed editor or a crash. Nobody is watching this session and nobody can answer \
a question, so do not ask any.

1. Read {notes} first, all of it. It says what is done, what comes next and which skills and tools to use.
2. If its STATE line is not RUNNING, stop at once without changing anything.
3. Carry on with the job exactly as the notes say, and keep the notes current after every finished step - \
they are how the next run picks up if this one is cut off too.
4. If something needs the user's decision, write it under "For the user" in the notes, set STATE: PAUSED \
and stop.
5. When the whole job is finished and checked, set STATE: DONE in the notes.

This run was started by the continue-after-limit watchdog ({skill})."""
RESUME = ("The usage limit has refilled. Continue the job from where you stopped; re-read {notes} first "
          "if you need to. Keep the notes current, and set STATE: DONE in them when everything is finished.")


def say(message: str) -> None:
    print(f"[{dt.datetime.now():%Y-%m-%d %I:%M:%S %p}] {message}", flush=True)


def clock(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch).strftime("%a %I:%M %p")


def find_claude(explicit: str | None) -> str:
    """--claude, else `claude` on PATH, else the newest binary an editor extension ships."""
    if explicit:
        return explicit
    on_path = shutil.which("claude")
    if on_path:
        return on_path
    home = Path.home()
    found = []
    for pattern in (".vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude",
                    ".vscode-server/extensions/anthropic.claude-code-*/resources/native-binary/claude",
                    ".local/bin/claude", ".claude/local/claude"):
        found += [str(p) for p in home.glob(pattern) if os.access(p, os.X_OK)]
    if not found:
        raise SystemExit("No Claude Code binary found - pass --claude PATH")

    def version(path: str) -> tuple[int, ...]:
        match = re.search(r"claude-code-(\d+(?:\.\d+)*)", path)
        return tuple(int(x) for x in match.group(1).split(".")) if match else (0,)
    return max(found, key=version)


def read_state(notes: Path) -> str:
    try:
        match = STATE.search(notes.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return "MISSING"
    return match.group(1).upper() if match else "NONE"


def transcripts_dir(workdir: Path) -> Path:
    """Where Claude Code keeps the session transcripts of a project directory."""
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(workdir))


def last_activity(workdir: Path, exclude: set[str]) -> float:
    """The newest write to any session transcript of this project (subagents' included), leaving out
    the sessions this watchdog ran itself - every Claude turn writes its transcript."""
    newest = 0.0
    root = transcripts_dir(workdir)
    if not root.is_dir():
        return newest
    for depth in ("*.jsonl", "*/*.jsonl", "*/*/*.jsonl"):
        for path in root.glob(depth):
            if not any(session in str(path) for session in exclude):
                with contextlib.suppress(OSError):
                    newest = max(newest, path.stat().st_mtime)
    return newest


def limit_reset(text: str, now: float) -> float | None:
    """When the usage limit reported in `text` resets (epoch seconds, local time for clock times), or
    None when `text` reports no usage limit."""
    if not LIMIT.search(text):
        return None
    if match := EPOCH.search(text):
        return float(match.group(1))
    if match := ISO.search(text):
        year, month, day, hour, minute = (int(match.group(i)) for i in range(1, 6))
        when = dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc if match.group(6) else None)
        return when.timestamp()
    today = dt.datetime.fromtimestamp(now)

    def hour24(hour: int, half: str | None) -> int:
        if half and half.lower() == "p" and hour != 12:
            return hour + 12
        if half and half.lower() == "a" and hour == 12:
            return 0
        return hour
    if match := DATED.search(text):
        month = MONTHS.index(match.group(1)[:3].lower()) + 1
        when = today.replace(month=month, day=int(match.group(2)), hour=hour24(int(match.group(3)), match.group(5)),
                             minute=int(match.group(4) or 0), second=0, microsecond=0)
        if when.timestamp() < now - 86400:
            when = when.replace(year=when.year + 1)
        return when.timestamp()
    if match := WEEKDAY.search(text):
        ahead = (DAYS.index(match.group(1)[:3].lower()) - today.weekday()) % 7
        when = (today + dt.timedelta(days=ahead)).replace(hour=hour24(int(match.group(2)), match.group(4)),
                                                          minute=int(match.group(3) or 0), second=0, microsecond=0)
        if when.timestamp() <= now:
            when += dt.timedelta(days=7)
        return when.timestamp()
    if match := CLOCK.search(text):
        hour, minute = hour24(int(match.group(1)), match.group(3)), int(match.group(2) or 0)
        if hour < 24 and minute < 60:
            when = today.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if when.timestamp() <= now:
                when += dt.timedelta(days=1)
            return when.timestamp()
    return now + UNKNOWN_WAIT


def outcome_text(lines: list[str]) -> str:
    """What decides how a run ended: its final result event (stream-json), else its last lines. Never the
    whole stream - a run that read about usage limits would look limited."""
    for line in reversed(lines):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            return f"{event.get('subtype', '')} {event.get('result', '')} {json.dumps(event.get('errors', ''))}"
    return "".join(lines[-20:])


def configured_mode(workdir: Path) -> str | None:
    """The permission mode the user set for this project (its settings, then theirs). A headless run does
    not apply `defaultMode` by itself - measured: it ran in "default", where nobody can approve a command."""
    for path in (workdir / ".claude" / "settings.local.json", workdir / ".claude" / "settings.json",
                 Path.home() / ".claude" / "settings.json"):
        try:
            mode = json.loads(path.read_text(encoding="utf-8")).get("permissions", {}).get("defaultMode")
        except (OSError, ValueError, AttributeError):
            continue
        if mode:
            return mode
    return None


def run_claude(claude: str, workdir: Path, prompt: str, resume: str | None, runs: Path,
               mode: str | None) -> tuple[int, str, str | None]:
    """One headless Claude Code run, streamed to headless-runs/; returns (exit code, outcome, session id)."""
    command = [claude, *(["--resume", resume] if resume else []), "-p", prompt, "--output-format", "stream-json",
               "--verbose", *(["--permission-mode", mode] if mode else [])]
    runs.mkdir(parents=True, exist_ok=True)
    log = runs / f"run-{dt.datetime.now():%Y%m%d-%H%M%S}.jsonl"
    tail: collections.deque[str] = collections.deque(maxlen=400)
    session = None
    with log.open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(command, cwd=workdir, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace", start_new_session=True)
        (runs / ".headless.pid").write_text(str(proc.pid))
        say(f"headless run pid {proc.pid}, log {log}")
        assert proc.stdout is not None
        for line in proc.stdout:
            out.write(line)
            out.flush()
            tail.append(line)
            if session is None and '"session_id"' in line:
                with contextlib.suppress(ValueError):
                    session = json.loads(line).get("session_id")
        code = proc.wait()
    (runs / ".headless.pid").unlink(missing_ok=True)
    return code, outcome_text(list(tail)), session


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--notes", required=True, help="the job's notes file (holds STATE: ...)")
    parser.add_argument("--workdir", default=str(Path.cwd()), help="where Claude Code runs (its project dir)")
    parser.add_argument("--idle", type=float, default=30, help="minutes of no Claude activity before a run")
    parser.add_argument("--grace", type=float, default=10,
                        help="minutes after a reset left to Claude Code's own continue")
    parser.add_argument("--max-idle-runs", type=int, default=3,
                        help="stop after this many runs in a row without progress")
    parser.add_argument("--claude", help="the Claude Code binary (default: found)")
    parser.add_argument("--permission-mode", help="for the headless runs (default: the project's defaultMode)")
    parser.add_argument("--poll", type=float, default=60, help="seconds between checks")
    args = parser.parse_args()

    notes, workdir = Path(args.notes).resolve(), Path(args.workdir).resolve()
    job, runs = notes.parent, notes.parent / "headless-runs"
    lock = (job / ".watchdog.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        say("another watchdog already watches this job - leaving it to that one")
        return
    claude = find_claude(args.claude)
    mode = args.permission_mode or configured_mode(workdir)
    skill = Path(__file__).resolve().parent / "SKILL.md"
    say(f"watching {notes}: Claude Code in {workdir} after {args.idle:g} idle min, permission mode "
        f"{mode or 'not set'} ({claude})")
    resume, mine, wait_until, idle_runs, told = None, set(), 0.0, 0, None
    while True:
        if (job / "STOP").exists():
            say("STOP file found - stopping")
            return
        state = read_state(notes)
        if state == "DONE":
            say("STATE: DONE - the job is finished, stopping")
            return
        if state != "RUNNING":
            if told != state:
                say(f"STATE: {state} - waiting until it says RUNNING")
                told = state
            time.sleep(args.poll)
            continue
        told = None
        now = time.time()
        if now < wait_until:
            time.sleep(min(args.poll, wait_until - now))
            continue
        idle = now - last_activity(workdir, mine)
        if idle < args.idle * 60:
            time.sleep(args.poll)
            continue
        quiet = f"no Claude activity for {idle / 60:.0f} min" if idle < now else "no Claude session found here"
        say(f"{quiet} and STATE: RUNNING - starting Claude Code headless"
            + (f" (resuming session {resume})" if resume else ""))
        before = notes.stat().st_mtime
        prompt = (RESUME if resume else PROMPT).format(notes=notes, skill=skill)
        code, outcome, session = run_claude(claude, workdir, prompt, resume, runs, mode)
        if session:
            resume = session
            mine.add(session)
        reset = limit_reset(outcome, time.time())
        if reset is not None:
            wait_until = reset + args.grace * 60
            say(f"usage limit (exit {code}): resets {clock(reset)} - next try {clock(wait_until)}, unless a "
                f"Claude session has carried on by then")
            continue
        progressed = notes.exists() and notes.stat().st_mtime != before
        idle_runs = 0 if progressed else idle_runs + 1
        say(f"run ended (exit {code}): {outcome.strip()[:160]!r}; notes {'updated' if progressed else 'unchanged'}")
        if idle_runs >= args.max_idle_runs:
            say(f"{idle_runs} runs in a row left the notes unchanged - stopping so the usage is not burned")
            return
        wait_until = time.time() + BETWEEN_RUNS


if __name__ == "__main__":
    main()
