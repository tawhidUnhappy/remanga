"""Which TTS engine speaks the narration, and in what language.

Both screens are built from data that already exists elsewhere: the engine
list comes from config.TTS_ENGINE_SPECS (the same specs remanga/audio/synth/
maps to Synthesizer classes), and whether a transcript is needed comes from
the chosen spec rather than from a name comparison written out again here."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.config.tts import TTS_ENGINE_SPECS
from remanga.console import console
from remanga.settings.assets import ASSET_BY_KEY, edit_asset
from remanga.settings.fields import set_field
from remanga.settings.files import read_reference_text
from remanga.settings.presets import CUSTOM, language_choices
from remanga.tui import Choice, ask_text, confirm, is_cancel, select


def configure_engine(config: RemangaConfig) -> None:
    picked = select(
        "TTS engine",
        [
            Choice(label=spec.display_name, hint=spec.name, detail=spec.summary, value=spec.name,
                   badge="current" if spec.name == config.tts.engine else "")
            for spec in TTS_ENGINE_SPECS
        ],
        default=config.tts.engine,
        note="each engine runs in its own isolated environment; switching downloads its weights on first use",
    )
    if is_cancel(picked):
        return

    set_field(config, "tts.engine", picked)
    console.print(f"[green]✓ Engine:[/] {config.tts.spec.display_name}")

    # An engine that clones from audio alone needs nothing more. One that
    # also wants the reference clip's transcript is asked for it here, but
    # only when there isn't one already - the file is shared across engines
    # and usually already filled in.
    if config.tts.spec.needs_reference_text and not read_reference_text(config.tts.audio8.reference_text_path):
        console.print(f"[dim]{config.tts.spec.display_name} also wants a transcript of the reference clip.[/]")
        if confirm("Add the reference transcript now?", default=True):
            edit_asset(config, ASSET_BY_KEY["transcript"])


def configure_language(config: RemangaConfig) -> None:
    picked = select(
        "Narration language", language_choices(config), default=(config.tts.lang or "EN").upper(),
        note="passed straight through to the TTS engine",
    )
    if is_cancel(picked):
        return
    if picked == CUSTOM:
        picked = ask_text("Language code (e.g. PT, IT, RU)", default=config.tts.lang,
                          allow_empty=False).upper()
    set_field(config, "tts.lang", picked)
    console.print(f"[green]✓ Narration language:[/] {picked}")
