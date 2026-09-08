"""The status report's vocabulary for "how far along is this step".

Every line of the panel answers the same question in one of a few ways -
done, blocked, not generated yet, switched off - and each of those used to
be spelled out as its own inline ternary inside the report's f-string, with
the literal markup repeated at every line. That made the report itself hard
to read as a report (the shape of each line was buried in its own colour
codes) and meant "done" was written out fresh a dozen times, free to drift.

Naming the states here keeps each line of the panel one short call, and
keeps the markup for a given state defined exactly once - so a green check
is the same green check everywhere it appears.

The distinction between `missing` and `pending` is deliberate and load
bearing: red means the pipeline is actually blocked here, dim yellow means
this step is switched on but simply hasn't run yet. `off` is neither - it's
a step this project doesn't want at all.
"""

from __future__ import annotations


def done(text: str) -> str:
    """A finished step."""
    return f"[green]✓ {text}[/]"


def missing(text: str = "Missing") -> str:
    """A required step that hasn't happened - the pipeline is blocked here."""
    return f"[red]✗ {text}[/]"


def absent(text: str = "Missing/Empty placeholder") -> str:
    """A hand-authored input that's still a blank placeholder. Not red: this
    is the normal state of a chapter nobody has written yet, and it's the
    user's move rather than a failure."""
    return f"[yellow]✗ {text}[/]"


def pending(text: str = "Not generated") -> str:
    """An optional step that's switched on for this project but hasn't run."""
    return f"[dim yellow]✗ {text}[/]"


def off(text: str = "off") -> str:
    """A step switched off in config - not a problem, just not happening."""
    return f"[dim]— {text}[/]"


def flagged(text: str) -> str:
    """Something waiting on a human or an LLM pass, rather than on a step."""
    return f"[yellow]⚑ {text}[/]"


def counted(count: int, noun: str, empty: str | None = None) -> str:
    """`done` with how many there are, or - when there are none - `empty`,
    which says whether zero is a blocker (the default, red `missing`) or
    just a step not run yet."""
    if count > 0:
        return done(f"Yes ({count} {noun})")
    return empty if empty is not None else missing()


def artifact(built: bool, active: bool) -> str:
    """One of the packaging outputs (panels_zip / pdf / sheets_zip), which
    has three states rather than two: built, still to build, or not wanted
    by this project's config at all."""
    if built:
        return done("Built")
    return pending() if active else off()
