"""Sizing a dialog to the window, so a small terminal can still scroll to all of it."""

from __future__ import annotations

from textual.screen import Screen


def _rows(widget) -> int:
    """How many rows this widget takes of its parent, margin included - none
    at all when it is hidden (the buttons, in a short window)."""
    if not widget.display:
        return 0
    return widget.outer_size.height + widget.styles.margin.height


# Rows the explanation keeps when the list needs the room - enough to see
# there is text, and to scroll it.
NOTE_MIN_ROWS = 3


def fit_to_window(screen: Screen, scrollable, note=None) -> None:
    """Caps the scrolling part so the whole dialog fits the window - a box
    taller than the terminal would otherwise be clipped with no way to reach
    the rest of it, which in a small window is most dialogs.

    With a `note` (the explanation above a list, in its own scroller) the two
    share what is left, and the LIST comes first: the choices are what the
    dialog is for, so they get every row they need, and the note keeps
    NOTE_MIN_ROWS (or less, if it is shorter) and scrolls the rest (user
    report: in a small window a long note pushed the list down to one row).

    Everything around the scrolling parts is measured rather than guessed:
    what sits outside the box (the bar, the footer), the box's own border and
    padding, and its title or buttons. Their heights are real ones, so this
    runs after a refresh - and never measures the box itself, whose height is
    what is being decided."""
    box = scrollable.parent
    if box is None:
        return
    # In a window this short the box's own frame costs more than it is worth:
    # its border and padding alone are four of the rows there are (.cramped
    # drops them - see the CSS in ui/app.py).
    box.set_class(screen.size.height < 14, "cramped")
    outside = sum(_rows(widget) for widget in screen.children if widget is not box)
    chrome = box.gutter.height + box.styles.margin.height
    chrome += sum(_rows(child) for child in box.children if child is not scrollable and child is not note)
    available = max(1, screen.size.height - outside - chrome)
    if note is None:
        scrollable.styles.max_height = available
    else:
        available = max(2, available - note.styles.margin.height)
        note_rows = note.virtual_size.height
        list_rows = scrollable.virtual_size.height
        listed = max(1, min(list_rows, available - min(note_rows, NOTE_MIN_ROWS)))
        scrollable.styles.max_height = listed
        note.styles.max_height = max(1, available - listed)
    # The box scrolls too, as a backstop - but once its content fits again it
    # must go back to the top, or it sits one line down and hides its title,
    # and its own scrollbar has to be recomputed against the new height.
    box.scroll_home(animate=False)
    box.refresh(layout=True)
