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


def setup(names: list[str] | None = None) -> None:
    """Each tool plug-in sets itself up (its setup.py): the environment, then
    the weights. Without names, what the first video needs - the configured
    narrator and MAGI v3; the other tools set themselves up when first used,
    so a tool nobody uses never costs a download."""
    from remanga import plugins
    from remanga.config import RemangaConfig
    from remanga.tool_envs import provision, tool_spec

    config = RemangaConfig.load()
    engine_tool = config.tts.spec.tool_name
    wanted = names or [engine_tool, "magi"]
    failed = set(provision(wanted, None))
    for name in wanted:
        spec = tool_spec(name)
        if spec is None or name in failed:
            continue
        if spec.weights:
            plugins.call(spec.weights, config)
        console.print(f"[bold green]✓ {spec.display_name} is set up.[/]")
    if engine_tool in failed:
        raise RuntimeError(f"Setting up {config.tts.spec.display_name} failed - see the messages above.")
    if "magi" in failed:
        console.print("[yellow]MAGI v3 did not set up - the Panel Marker still works, with the panels marked "
                      "by hand.[/]")
    if failed - {"magi"}:
        raise RuntimeError(f"Setup failed for: {', '.join(sorted(failed))} - see the messages above.")


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
