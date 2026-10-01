"""The command line's commands that are not a pipeline step: the job queue
(list it, run it), setup and the plug-in list. cli.py parses and dispatches."""

from __future__ import annotations

from remanga.console import console, err_console, escape as _esc


def show_queue() -> None:
    from remanga.workflow.queue import load_queue

    jobs = load_queue()
    if not jobs:
        console.print("[yellow]The queue is empty - add jobs from a chapter's menu (Add to queue).[/]")
    for number, job in enumerate(jobs, 1):
        note = f"  [red]{_esc(job.error.splitlines()[0])}[/]" if job.error else ""
        console.print(f"  {number:>3}  {job.state:<8} {_esc(job.title)}{note}")


def run_queue(machine) -> None:
    """Every job not done yet, in order. A failing job is recorded and the
    next one starts; the exit status is 1 if any failed."""
    from remanga.workflow.queue import load_queue, record, run_job, to_run

    jobs = to_run(load_queue())
    if not jobs:
        console.print("[green]Nothing to run - every job in the queue is done.[/]")
        return
    failed = 0
    for number, job in enumerate(jobs, 1):
        console.print(f"\n[bold cyan]Job {number}/{len(jobs)}: {_esc(job.title)}[/]")
        try:
            run_job(job, machine)
        except Exception as error:
            record(job, str(error) or type(error).__name__)
            err_console.print(f"[bold red]Failed:[/] {_esc(str(error))}")
            failed += 1
            continue
        record(job, None)
    if failed:
        raise RuntimeError(f"{failed} of {len(jobs)} job(s) failed - see above; `remanga queue` lists them.")
    console.print(f"[bold green]✓ All {len(jobs)} job(s) done.[/]")


def setup() -> None:
    """What the first video needs: MAGI v3 for finding panels, and the
    configured narrator's own environment and weights. The other engines are
    installed when they are first chosen, not here - an engine nobody uses
    should not cost a download."""
    from remanga.audio.synth import create_synthesizer
    from remanga.config import RemangaConfig
    from remanga.plugins.magi.assist import ensure_weights_downloaded
    from remanga.tool_envs import provision

    config = RemangaConfig.load()
    engine = config.tts.spec
    failed = provision([engine.tool_name, "magi"], None)
    if engine.tool_name in failed:
        raise RuntimeError(f"Installing {engine.display_name}'s environment failed - see the messages above.")
    create_synthesizer(config.tts, config.audio).model_manager.ensure_model()
    console.print(f"[bold green]✓ {engine.display_name} is installed and ready.[/]")
    if "magi" in failed:
        console.print("[yellow]MAGI v3's environment failed to install - the Panel Marker still works, with the "
                      "panels marked by hand.[/]")
        return
    ensure_weights_downloaded(config.marker)


def show_plugins() -> None:
    """Every plug-in remanga loaded, by kind, and where each came from - and
    any that could not load, with why."""
    from remanga import plugins

    for kind in plugins.KINDS:
        console.print(f"[bold]{kind}[/]")
        for item in plugins.items(kind):
            label = getattr(item, "display_name", None) or getattr(item, "label", "")
            console.print(f"  {item.name:<16} {_esc(label):<28} [dim]{_esc(plugins.origin(kind, item.name))}[/]")
    failed = plugins.failures()
    if failed:   # each one was already reported, with why, as it failed to load
        err_console.print(f"[red]✗ {len(failed)} plug-in(s) could not load - see above.[/]")
