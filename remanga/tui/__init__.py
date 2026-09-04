"""remanga's interactive terminal toolkit - arrow-key menus, checklists,
confirmations and validated text/path prompts.

Why this exists: every interactive screen in remanga used to be hand-rolled
from `console.print` loops plus `rich.prompt.Prompt`, which meant the user
typed a number for a category, typed another number for a command, typed a
comma-separated list for pipeline steps, typed exact filenames for a wipe's
keep-list, and answered eight fixed questions in a fixed order to change one
video setting. Each of those screens also invented its own layout and its
own idea of what "0" meant. Now every one of them is a Choice list handed to
`select`/`multiselect`/`confirm`: arrow keys move, typing filters, space
toggles, Enter accepts the pre-highlighted current value, Esc backs out -
the same everywhere, with the *content* being the only thing each caller
writes.

Non-tty terminals (piped stdin, CI, an editor's output pane) keep working:
every prompt checks `is_interactive()` and routes to the numbered-prompt
equivalents in `remanga.tui.fallback`, which are the same prompts remanga
has always had.

    from remanga.tui import Choice, confirm, multiselect, select, is_cancel

    engine = select("TTS engine", [Choice("indextts-2.5", hint="voice-only cloning")],
                    default=config.tts.engine)
    if is_cancel(engine):
        return
"""

from __future__ import annotations

from remanga.tui.checklist import multiselect
from remanga.tui.choices import Choice, Toggle, index_of_value, to_choices
from remanga.tui.confirm import confirm
from remanga.tui.fallback import ask_index
from remanga.tui.keys import is_interactive
from remanga.tui.result import CANCEL, EXIT, PromptExit, is_cancel
from remanga.tui.select import select
from remanga.tui.text import ask_number, ask_path, ask_text

__all__ = [
    "CANCEL",
    "EXIT",
    "PromptExit",
    "Choice",
    "Toggle",
    "ask_index",
    "ask_number",
    "ask_path",
    "ask_text",
    "confirm",
    "index_of_value",
    "is_cancel",
    "is_interactive",
    "multiselect",
    "select",
    "to_choices",
]
