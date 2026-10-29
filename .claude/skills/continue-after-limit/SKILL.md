---
name: continue-after-limit
description: Keep a long job going when Claude's usage limit runs out - it carries on by itself once the limit refills, and after a closed editor or a crash. Use at the start of any job that runs for hours (a whole-manga long recap, a batch of renders), when the user asks to "continue after the credits refill", when you are a run the watchdog started, and before working on a job whose notes have a headless run going.
---

# Continue after the usage limit refills

The user (2026-10-29, mid way through a 48-chapter long recap): "make a skill that will let you continue
even when all credit run out and it refill and you continue after the refill" - Claude's own usage limit.

## Two layers

1. **Claude Code's own.** Version 2.1.312 has the setting `autoContinueAtUsageLimit` ("Continue
   automatically at usage limit" in /config); unset means on. When a claude.ai usage limit stops a
   session, it waits for the reset and continues the task in that same session ("Usage limit reached ·
   continuing automatically ..."). What the binary says about its limits: it works only while that
   session stays open; not for a reset more than 24 hours away (a weekly limit is "too far out to wait
   for"); only a couple of re-arms; and its gate may be the terminal REPL only - not verified in the VS
   Code extension. Never set it to false.
2. **The watchdog** - `continue_watchdog.py` in this folder (standard library only) - covers the rest.
   While the job's notes say `STATE: RUNNING` and no Claude session of the project has written its
   transcript for `--idle` minutes (default 30), it starts Claude Code headless (`claude -p`, in the
   project's own permission mode) with a prompt that points at the notes. A run that meets the usage
   limit is tried again at the reset time it printed plus `--grace` (10 min), so layer 1 goes first; if a
   session has carried on by then, the watchdog stands down. Later runs resume the same headless session
   (`--resume`).

## The contract: a notes file

A job that should survive needs a notes file on /mnt/datadisk (never /tmp - a power-off wipes it) with:
- a line `STATE: RUNNING`, `PAUSED` or `DONE`. The watchdog acts only on RUNNING, and DONE stops it;
- what is done, what comes next and how - commands, skills, tools, paths - written for a fresh session
  that remembers nothing of the conversation, because that is exactly who reads it;
- a log line after every finished step, so the next run knows where the last one was cut off.

Set `STATE: PAUSED` before ending a turn that waits for the user (a question, "for now stop here"),
`RUNNING` again when they say continue, and `DONE` once everything is finished and checked.

## Start it, with the job

    setsid nohup python3 -I /mnt/datadisk/remanga/.claude/skills/continue-after-limit/continue_watchdog.py \
        --notes NOTES --workdir /mnt/datadisk >> NOTES_DIR/watchdog.log 2>&1 < /dev/null &

`--workdir` is where the user's Claude Code sessions run: their settings, memory, permission mode and
transcripts belong to it. One watchdog per job (a lock); starting a second one does nothing. Read
`NOTES_DIR/watchdog.log` to see what it decided. A power-off ends it - start it again with the job.

## When you are the resumed run

The prompt says it all: read the notes first, stop if STATE is not RUNNING, carry on as they say, keep
them current, nobody can answer a question (write it under "For the user" and set PAUSED), DONE at the end.
Check that the job's background workers (a render queue) are running before starting them - never two.

## When the user comes back while a headless run works

`NOTES_DIR/headless-runs/.headless.pid` holds the PID of the headless Claude at work. If that process is
alive, do no job work alongside it - two Claudes would write the same files. Tell the user it is running
(its log is the newest file in `headless-runs/`), and if they want to take over: `touch NOTES_DIR/STOP`,
`kill PID`, then carry on in their session and set STATE as above.

## Stop it

`touch NOTES_DIR/STOP`, or set STATE to DONE. It also stops by itself after 3 finished runs in a row
that left the notes unchanged, so a stuck job cannot burn the usage.

## Measured (2026-10-29)

- A fake `claude` that answered "Usage limit reached · resets 5:23pm": the watchdog waited until 5:23 PM,
  resumed the same session with `--resume`, saw STATE: DONE and stopped.
- With a live VS Code session writing its transcript, it never launched anything.
- Real headless runs: 14 s for a file task ($0.20); a Bash task (nvidia-smi, python) ran with no denials
  ($0.36) once the mode was passed. **A headless run does not apply the project's `defaultMode` by
  itself** - it ran in "default", where nobody can approve a command - so the watchdog passes the
  configured mode with `--permission-mode` (never a looser one).
- Reset times it reads: `...limit reached|<epoch>`, `resets 7pm`, `resets at 11:30 PM`, `resets 3am
  (Asia/Dhaka)`, `resets Nov 3, 9am`, `resets Mon 9am`, `resets 2026-08-08 00:00 UTC`. Anything else: it
  looks again in an hour (a run refused at the limit costs nothing). Only the run's final result event is
  read, never the whole stream - a run that merely read about usage limits must not look limited.
