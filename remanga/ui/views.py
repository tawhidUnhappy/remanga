"""What the screens look like - pure functions from state to Rich renderables.

Every screen is the same frame: a header line (where you are, and a short
fact on the right), the body, and a footer that lists the keys. Dialogs are
drawn centred in the body; the task view and results are drawn the same way.
Nothing here reads keys or touches the terminal."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rich.align import Align
from rich.console import Group, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

ACCENT = "cyan"
MUTED = "grey62"
CURSOR_STYLE = "bold white on grey23"
OK, WARN, BAD = "green", "yellow", "red"


def keys_line(hints: Sequence[tuple[str, str]]) -> Text:
    """ `↑↓ move   Enter open   Esc back` - keys bright, their meaning dim."""
    line = Text(" ")
    for i, (key, label) in enumerate(hints):
        if i:
            line.append("   ")
        line.append(key, style=f"bold {ACCENT}")
        line.append(f" {label}", style=MUTED)
    return line


def frame(path: Sequence[str], info: str, body: RenderableType, hints: Sequence[tuple[str, str]]) -> Layout:
    """The screen: header, body, footer - the body takes whatever height is left."""
    title = Text(" ")
    for i, part in enumerate(path):
        if i:
            title.append("  ›  ", style=MUTED)
        title.append(part, style="bold" if i == len(path) - 1 else MUTED)
    header = Table.grid(expand=True)
    header.add_column(ratio=1, no_wrap=True, overflow="ellipsis")
    header.add_column(justify="right", no_wrap=True)
    header.add_row(title, Text(info + " ", style=MUTED))

    layout = Layout()
    layout.split_column(
        Layout(Group(header, Rule(style="grey30")), size=2),
        Layout(body, name="body"),
        Layout(Group(Rule(style="grey30"), keys_line(hints)), size=2),
    )
    return layout


def body_height(screen_height: int) -> int:
    return max(3, screen_height - 4)


def centered(renderable: RenderableType) -> Align:
    return Align.center(renderable, vertical="middle")


@dataclass
class Column:
    header: str
    width: int | None = None
    ratio: int | None = None
    justify: str = "left"


def table(columns: Sequence[Column], rows: Sequence[Sequence[str | Text]], *, cursor: int | None, top: int,
          height: int, marks: set[int] | None = None, empty: str = "Nothing here yet.") -> RenderableType:
    """A list as a table, showing rows[top:top+height-1] under a header row.
    The cursor row is highlighted and pointed at; `marks` (for picking several)
    adds a ● column."""
    if not rows:
        return centered(Text(empty, style=MUTED))
    grid = Table(expand=True, box=None, show_edge=False, pad_edge=False, header_style=f"bold {MUTED}",
                 padding=(0, 1))
    grid.add_column("", width=1, no_wrap=True)
    if marks is not None:
        grid.add_column("", width=1, no_wrap=True)
    for col in columns:
        grid.add_column(col.header, width=col.width, ratio=col.ratio, justify=col.justify, no_wrap=True,
                        overflow="ellipsis")
    visible = max(1, height - 1)
    for index in range(top, min(len(rows), top + visible)):
        here = index == cursor
        cells = [Text("❯", style=f"bold {ACCENT}") if here else Text(" ")]
        if marks is not None:
            cells.append(Text("●", style=f"bold {ACCENT}") if index in marks else Text("·", style="grey35"))
        cells += [cell if isinstance(cell, Text) else Text(str(cell)) for cell in rows[index]]
        grid.add_row(*cells, style=CURSOR_STYLE if here else None)
    more = []
    if top > 0:
        more.append(f"↑ {top} more")
    below = len(rows) - (top + visible)
    if below > 0:
        more.append(f"↓ {below} more")
    if more:
        return Group(grid, Text("  " + "   ".join(more), style=MUTED))
    return grid


def dialog(title: str, content: RenderableType, *, style: str = ACCENT, width: int = 64) -> Align:
    return centered(Panel(content, title=f"[bold]{title}[/]", title_align="left", border_style=style,
                          width=width, padding=(1, 2)))


def option_list(options: Sequence[tuple[str, str]], cursor: int | None, *, danger: set[int] = frozenset()) -> Table:
    """Rows of (label, hint) for a dialog, the cursor row highlighted."""
    grid = Table.grid(expand=True, padding=(0, 2))
    grid.add_column(width=1)
    grid.add_column(no_wrap=True)
    grid.add_column(style=MUTED, overflow="fold", ratio=1)
    for i, (label, hint) in enumerate(options):
        here = i == cursor
        label_style = ("bold " if here else "") + (BAD if i in danger else "")
        grid.add_row(Text("❯", style=f"bold {ACCENT}") if here else Text(" "), Text(label, style=label_style.strip()),
                     hint, style=CURSOR_STYLE if here else None)
    return grid


def text_box(label: str, value: str, note: str = "", error: str = "") -> Group:
    field = Text(value, style="bold") + Text("▏", style=f"blink {ACCENT}")
    parts: list[RenderableType] = [Text(label, style=MUTED), Panel(field, border_style="grey50", padding=(0, 1))]
    if error:
        parts.append(Text(error, style=BAD))
    elif note:
        parts.append(Text(note, style=MUTED))
    return Group(*parts)


# --- tasks --------------------------------------------------------------------

_ICONS = {"pending": ("·", "grey42"), "done": ("✓", OK), "failed": ("✗", BAD), "skipped": ("–", MUTED)}


@dataclass
class StepView:
    label: str
    state: str = "pending"  # pending / running / done / failed / skipped
    note: str = ""


def task_view(title: str, steps: Sequence[StepView], bar: tuple[str, float | None, float, str] | None,
              recent: Sequence[str]) -> Group:
    """Steps with their state, the running step's progress bar, and the last
    few things the work said."""
    grid = Table.grid(padding=(0, 1))
    grid.add_column(width=2)
    grid.add_column(no_wrap=True)
    grid.add_column(style=MUTED, no_wrap=True, overflow="ellipsis")
    for step in steps:
        if step.state == "running":
            icon: RenderableType = Spinner("dots", style=ACCENT)
            label = Text(step.label, style="bold")
        else:
            char, style = _ICONS[step.state]
            icon = Text(char, style=style)
            label = Text(step.label, style=MUTED if step.state == "pending" else "")
        grid.add_row(icon, label, step.note)

    parts: list[RenderableType] = [grid]
    if bar is not None:
        description, total, completed, detail = bar
        line = Table.grid(padding=(0, 1))
        line.add_column(no_wrap=True)
        line.add_column(width=40)
        line.add_column(style=MUTED, no_wrap=True)
        count = f"{completed:.0f}/{total:.0f}" if total else ""
        line.add_row(Text(description, style=MUTED),
                     ProgressBar(total=total or 100, completed=completed if total else 0, pulse=not total,
                                 style="grey30", complete_style=ACCENT, finished_style=OK),
                     " ".join(x for x in (count, detail) if x))
        parts += [Text(""), line]
    if recent:
        parts += [Text(""), *[Text(line, style="grey50", no_wrap=True, overflow="ellipsis") for line in recent]]
    return Group(*parts)


def result_panel(title: str, lines: Sequence[str | Text], *, ok: bool, warnings: Sequence[str] = ()) -> Align:
    body: list[RenderableType] = [line if isinstance(line, Text) else Text(line) for line in lines]
    if warnings:
        if body:
            body.append(Text(""))
        body += [Text(f"! {w}", style=WARN) for w in warnings]
    icon = "✓" if ok else "✗"
    return dialog(f"{icon} {title}", Group(*body) if body else Text(""), style=OK if ok else BAD, width=90)
