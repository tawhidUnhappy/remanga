"""Which TTS engine speaks the narration, in which voice, and in what language.

Every screen is built from data that already exists elsewhere: the engine
list comes from config.TTS_ENGINE_SPECS (the same specs remanga/audio/synth/
maps to Synthesizer classes), and the voice list from the engine's own voice
catalogue (config/kokoro_voices.py) rather than from anything written out
again here."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.config.tts import TTS_ENGINE_SPECS
from remanga.console import console
from remanga.settings.assets import pick_voice
from remanga.settings.fields import set_field
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
        numbered=True,
        note="each engine runs in its own isolated environment; switching downloads its weights on first use",
    )
    if is_cancel(picked):
        return

    set_field(config, "tts.engine", picked)
    console.print(f"[green]✓ Engine:[/] {config.tts.spec.display_name}")

    # Which voice narrates is the engine's own setting, so say which one is
    # in effect after a switch - silently changing the narrator is the kind
    # of thing only noticed after a chapter has been synthesized - and offer
    # to set it here when that engine has none, since the alternative is
    # discovering it at synth time.
    if config.tts.active_voice:
        voice = config.tts.kokoro.spec
        console.print(
            f"[dim]{config.tts.spec.display_name} narrates as {voice.label} "
            f"({voice.name}, grade {voice.grade})[/]"
        )
    else:
        console.print(f"[yellow]{config.tts.spec.display_name} has no voice set yet[/]")
        if confirm(f"Pick {config.tts.spec.display_name}'s voice now?", default=True):
            pick_voice(config)


def configure_voice(config: RemangaConfig) -> None:
    """The narrator's voice, on its own settings row.

    A picker rather than a file browser: Kokoro ships fixed voices and
    clones nothing, so there is no clip to point at - see
    remanga/config/kokoro_voices.py."""
    pick_voice(config)


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
