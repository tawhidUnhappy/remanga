"""The menus' look (user request, 2026-10-14): "android-dark" and
"android-light" are the Android 17 look (Material 3 Expressive), the palette
of the web pages' default look (webui/static_shared/css/theme-android.css);
"terminal" is Textual's own dark theme with outlined boxes, as the menus were.

A terminal draws no curves or shadows, so the Android look is told by what a
terminal can draw: tonal surfaces in place of hairline boxes, a tonal top bar,
the highlighted row on a secondary-container fill, buttons as one-line pills
on a tonal fill (the default one filled in primary). Its shape rules live in
ANDROID_CSS, scoped to the app's "android" class, so the terminal look is
untouched by them."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.theme import Theme

if TYPE_CHECKING:
    from textual.app import App

LOOKS = (("android-dark", "Android, dark", "Material 3 colours, tonal surfaces - the web pages' look"),
         ("android-light", "Android, light", "the same on a light background"),
         ("terminal", "Terminal", "the dark colours and outlined boxes the menus had before"))

ANDROID_DARK = Theme(
    name="android-dark",
    primary="#D0BCFF", secondary="#CCC2DC", accent="#EFB8C8",
    foreground="#E6E0E9", background="#141218", surface="#211F26", panel="#2B2930", boost="#36343B",
    success="#9ED383", warning="#F6BD58", error="#F2B8B5",
    dark=True,
    variables={
        "block-cursor-background": "#4A4458", "block-cursor-foreground": "#E8DEF8",
        "block-cursor-text-style": "bold",
        "block-cursor-blurred-background": "#36343B", "block-cursor-blurred-foreground": "#E6E0E9",
        "block-hover-background": "#36343B",
        "footer-background": "#211F26", "footer-key-foreground": "#D0BCFF",
        "footer-description-foreground": "#CAC4D0",
        "input-selection-background": "#4A4458",
        "scrollbar": "#49454F", "scrollbar-hover": "#938F99", "scrollbar-active": "#D0BCFF",
        "scrollbar-background": "#211F26", "scrollbar-background-hover": "#211F26",
        "scrollbar-background-active": "#211F26", "scrollbar-corner-color": "#211F26",
        "border": "#D0BCFF", "border-blurred": "#49454F",
        "text-muted": "#CAC4D0",
    },
)

ANDROID_LIGHT = Theme(
    name="android-light",
    primary="#6750A4", secondary="#625B71", accent="#7D5260",
    foreground="#1D1B20", background="#FEF7FF", surface="#F3EDF7", panel="#ECE6F0", boost="#E6E0E9",
    success="#386A20", warning="#7D5700", error="#B3261E",
    dark=False,
    variables={
        "block-cursor-background": "#E8DEF8", "block-cursor-foreground": "#1D192B",
        "block-cursor-text-style": "bold",
        "block-cursor-blurred-background": "#E6E0E9", "block-cursor-blurred-foreground": "#1D1B20",
        "block-hover-background": "#E6E0E9",
        "footer-background": "#F3EDF7", "footer-key-foreground": "#6750A4",
        "footer-description-foreground": "#49454F",
        "input-selection-background": "#E8DEF8",
        "scrollbar": "#CAC4D0", "scrollbar-hover": "#79747E", "scrollbar-active": "#6750A4",
        "scrollbar-background": "#F3EDF7", "scrollbar-background-hover": "#F3EDF7",
        "scrollbar-background-active": "#F3EDF7", "scrollbar-corner-color": "#F3EDF7",
        "border": "#6750A4", "border-blurred": "#CAC4D0",
        "text-muted": "#49454F",
    },
)

ANDROID_CSS = """
/* Bars: one tonal surface, no hairline. */
.android TopBar { background: $surface; border-bottom: none; height: auto; margin-bottom: 1; }
.android KeyBar { background: $surface; }
.android RowDetail { background: $surface; border-top: none; }
.android DataTable { background: $background; }
.android DataTable > .datatable--header { background: $background; color: $primary; text-style: bold; }

/* Dialogs: a tonal card (surface container high), no outline; how it ended
   shows in the title's colour instead of the frame's. */
.android Result, .android Choice, .android Ask { background: $background 60%; }
.android .dialog, .android .dialog.ok, .android .dialog.failed {
    border: none; background: $panel; padding: 1 3;
}
.android .dialog.cramped, .android .dialog.wide.cramped { padding: 0 1; }
.android .dialog-title { color: $primary; }
.android .dialog.ok .dialog-title { color: $success; }
.android .dialog.failed .dialog-title { color: $error; }
.android #result-text, .android .note-scroll, .android .dialog SafeOptionList { background: $panel; }
.android .dialog SafeOptionList > .option-list--option-highlighted {
    background: $block-cursor-background; color: $block-cursor-foreground;
}
.android .dialog SafeOptionList:focus > .option-list--option-highlighted {
    background: $block-cursor-background; color: $block-cursor-foreground;
}
.android .dialog Input { border: none; background: $boost; padding: 0 2; height: 1; }
.android .dialog Input:focus { background: $block-cursor-background; }

/* Buttons: one-line pills - tonal (secondary container), the default one
   filled in primary; the focused one is filled in the tertiary colour. */
.android Button {
    border: none; height: 1; min-width: 10; padding: 0 3;
    background: $block-cursor-background; color: $block-cursor-foreground; text-style: bold;
}
.android Button.-primary { background: $primary; color: $background; }
.android Button:hover, .android Button.-primary:hover { background: $primary-lighten-1; color: $background; }
.android Button:focus, .android Button.-primary:focus { background: $accent; color: $background;
                                                        text-style: bold; }
.android .buttons { margin-top: 1; }

/* Work in progress: the same tonal card. */
.android .task { border: none; background: $surface; padding: 1 3; }
.android #output { border: none; background: $background; padding: 0 1; }
.android ProgressBar Bar > .bar--bar { color: $primary; background: $boost; }
.android ProgressBar Bar > .bar--complete { color: $success; }
"""


def register(app: App) -> None:
    app.register_theme(ANDROID_DARK)
    app.register_theme(ANDROID_LIGHT)


def apply(app: App, look: str) -> None:
    """Switches the app to `look` (one of LOOKS) - live, nothing restarts."""
    android = look.startswith("android")
    app.theme = look if android else "textual-dark"
    app.set_class(android, "android")


def label(look: str) -> str:
    return next((name for key, name, _ in LOOKS if key == look), look)
