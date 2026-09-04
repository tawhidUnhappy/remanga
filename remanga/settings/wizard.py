"""`remanga setup-config` - the settings screen.

Was a fixed eight-question march (engine, voice, transcript, vision, language,
BGM, resolution, background, GPU) that had to be answered end to end to change
any one of them. It's now a menu over remanga.settings.sections: every row
shows what that setting is right now, opening one changes just that one, and
"Walk through every section" runs the same list top to bottom for a first-time
setup - the original walkthrough, kept as an option instead of as the only
path."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.settings.assets import ASSETS, asset_relevant, asset_status
from remanga.settings.sections import SECTIONS, SECTION_BY_KEY
from remanga.settings.summary import settings_summary
from remanga.tui import Choice, is_cancel, select

_WALKTHROUGH = "__walkthrough__"
_SUMMARY = "__summary__"


def _unconfigured(config: RemangaConfig) -> list:
    """Assets the pipeline actually needs that aren't usable yet - the one
    thing worth pointing at before the user picks anything."""
    missing = []
    for spec in ASSETS:
        if not asset_relevant(config, spec):
            continue
        ok, _, _ = asset_status(config, spec)
        if not ok:
            missing.append(spec.label)
    return missing


def run_setup_wizard(config: RemangaConfig) -> RemangaConfig:
    """Interactive settings menu. Returns the same config object, saved -
    every section persists its own change immediately, so backing out never
    loses an answer already given."""
    while True:
        missing = _unconfigured(config)
        rows = [
            Choice(label=section.title, hint=str(section.describe(config)),
                   detail=section.detail, value=section.key)
            for section in SECTIONS
        ]
        rows.append(Choice(label="Walk through every section", value=_WALKTHROUGH,
                           hint="first-time setup, in order"))
        rows.append(Choice(label="Show full summary", value=_SUMMARY,
                           hint="everything config.json holds"))

        note = "changes save immediately"
        if missing:
            note = f"not configured yet: {', '.join(missing)}"
        # Opened from inside a project, the voice/music/video answers are that
        # manga's; the machine-wide ones still aren't (see
        # RemangaConfig.save). Worth one clause, since the same screen does
        # both depending on where you opened it from.
        title = "Settings"
        if config.project:
            title = f"Settings — {config.project}"
            note += " · for this manga; GPU/web-UI settings stay machine-wide"

        picked = select(title, rows, note=note, back_label="Done")
        if is_cancel(picked):
            return config

        if picked == _WALKTHROUGH:
            _walkthrough(config)
        elif picked == _SUMMARY:
            console.print(settings_summary(config))
        else:
            SECTION_BY_KEY[picked].run(config)


def _walkthrough(config: RemangaConfig) -> None:
    for i, section in enumerate(SECTIONS, start=1):
        console.print(f"\n[bold]{i}/{len(SECTIONS)} — {section.title}[/]")
        section.run(config)
    console.print(settings_summary(config))
