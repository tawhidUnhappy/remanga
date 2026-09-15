"""The deletes full-recap's rebuild modes start with, one per mode: every
generated file (regenerate all), everything made from the narration (sound
and video), everything remanga can rebuild (from source). Each lists what it
is about to delete before deleting it, and counts what actually went."""

from __future__ import annotations

from pathlib import Path

from remanga.console import console, display_path
from remanga.reset import (
    KEEP_ON_SOURCES_REBUILD,
    PROJECT_KEEP,
    derived_wipe_candidates,
    project_wipe_candidates,
    sources_wipe_candidates,
    wipe_derived_audio_and_video,
    wipe_project,
    wipe_to_sources,
)


def describe_size(path: Path) -> str:
    """"how big is this" for a delete listing, as a human reads it.

    A path on its own does not tell anyone whether they are about to lose
    four megabytes or an hour of synthesis. Walks the tree because these
    are directories; errors are swallowed rather than raised because a
    file vanishing mid-walk must not turn a listing into a crash."""
    try:
        total = path.stat().st_size if path.is_file() else sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    except OSError:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if total < 1024 or unit == "GB":
            return f"{total:.0f}{unit}" if unit == "B" else f"{total:.1f}{unit}"
        total /= 1024
    return ""


def wipe_generated_listed(project_name: str) -> None:
    """The regenerate-all delete: every generated artifact in the
    project, in one sweep, listed BEFORE it happens and counted after.

    Listed first for the same reason remanga.reset.entries exists: this
    deletes a whole project's worth of output, and "here is what went"
    printed afterwards is not something anyone can object to in time.
    The list is printed from project_wipe_candidates and the deletion
    re-derives it, exactly as the interactive wipe commands do (see
    commands/handlers/cleanup.py), so the two can't describe different
    sets - and the count reported at the end is what was actually
    removed, not what was predicted."""
    candidates = project_wipe_candidates(project_name)
    if not candidates:
        console.print(
            f"[dim]Nothing generated to delete for '{project_name}' - "
            f"starting from an already-clean project.[/]"
        )
        return

    console.print(
        f"[bold red]Regenerating from scratch - permanently deleting every generated "
        f"file in '{project_name}':[/]"
    )
    for item in candidates:
        size = describe_size(item)
        console.print(f"  [dim]- {display_path(item)}{f'  ({size})' if size else ''}[/]")
    console.print(f"[dim]Kept: {', '.join(PROJECT_KEEP)}.[/]")
    console.print(
        "[dim]This re-runs text-to-speech on every panel - the slow part. "
        "Use 'Sound and video' instead when only the sound or look is changing.[/]"
    )

    removed = wipe_project(project_name)
    console.print(f"[bold green]✓ Deleted {len(removed)} item(s) - rebuilding from source.[/]")


def wipe_derived_listed(project_name: str) -> None:
    """The regenerate-effects delete: everything made FROM the narration,
    listed before it happens, with the narration itself untouched.

    Same contract as wipe_generated_listed - print the candidates, then let
    the action re-derive them - but a deliberately smaller set. `audio/` is
    the expensive artifact (a TTS pass per panel); audio_modified/ and
    video/ are derived from it and cost seconds. Keeping that distinction
    on the delete side is what makes iterating on how a recap SOUNDS
    affordable, rather than something that costs a full re-synthesis
    every time a dB moves."""
    candidates = derived_wipe_candidates(project_name)
    if not candidates:
        console.print(
            f"[dim]No processed audio or video to delete for '{project_name}' - "
            f"building them fresh.[/]"
        )
        return

    console.print(
        f"[bold yellow]Rebuilding effects and video for '{project_name}' - deleting:[/]"
    )
    for item in candidates:
        size = describe_size(item)
        console.print(f"  [dim]- {display_path(item)}{f'  ({size})' if size else ''}[/]")
    console.print("[dim]Kept: the synthesized narration in audio/ - nothing is re-narrated.[/]")

    removed = wipe_derived_audio_and_video(project_name)
    console.print(
        f"[bold green]✓ Deleted {len(removed)} item(s) - rebuilding from the existing narration.[/]"
    )


def wipe_to_sources_listed(project_name: str) -> None:
    """The deepest delete: everything remanga can rebuild, listed first.

    Same contract as the other two wipes. What makes this one different
    is that it reaches INSIDE chapters/ - taking panels/ as well - so the
    listing spells out what survives, because at this depth "keeps
    chapters/" would be actively misleading."""
    candidates = sources_wipe_candidates(project_name)
    if not candidates:
        console.print(
            f"[dim]Nothing to delete for '{project_name}' - already down to its source files.[/]"
        )
        return

    console.print(
        f"[bold red]Rebuilding '{project_name}' from source - permanently deleting:[/]"
    )
    for item in candidates:
        size = describe_size(item)
        console.print(f"  [dim]- {display_path(item)}{f'  ({size})' if size else ''}[/]")
    console.print(
        f"[dim]Kept, because remanga cannot rebuild them: "
        f"{', '.join(sorted(KEEP_ON_SOURCES_REBUILD))} in every chapter, "
        f"plus {', '.join(sorted(n for n in PROJECT_KEEP if n.endswith('.json')))}.[/]"
    )
    console.print(
        "[dim]Pages are kept and re-verified per chapter - anything that does not belong is "
        "removed and only missing images are re-fetched.[/]"
    )

    removed = wipe_to_sources(project_name)
    console.print(f"[bold green]✓ Deleted {len(removed)} item(s) - rebuilding from source.[/]")
