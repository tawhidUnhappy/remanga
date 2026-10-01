"""The narrator's rows on the settings screen, per engine.

Each engine takes a voice in its own way - a name from a catalogue, a preset
plus a note on delivery, a description to design from - so each engine
plug-in brings its own rows (its `settings_rows`, e.g.
plugins/kokoro/rows.py). The settings screen itself only knows about `Row`,
so adding an engine changes nothing here.

The rows are built fresh each time the screen loads, so a row can appear only
when it applies (the sample line of a designed voice, say)."""

from __future__ import annotations

from remanga import plugins
from remanga.config import RemangaConfig
from remanga.ui.dialogs import Choice
from remanga.ui.voice_rows import Row, wait_for


async def _pick_engine(screen, config: RemangaConfig) -> None:
    engine = await wait_for(screen)(Choice(
        "Narrator engine", [(spec.display_name, spec.summary, spec.name) for spec in plugins.items("tts")],
        current=config.tts.engine,
        note="Each engine keeps its own voice, so switching back and forth changes nothing else. "
             "A chapter narrated by the other engine is narrated again."))
    if engine:
        config.tts.engine = engine


async def _hear_voices(screen, config: RemangaConfig) -> None:
    """One line read in every voice this engine has, to listen to and choose
    from - the model loads once for the whole set."""
    from remanga import workflow

    ok = await screen.run_work("Sampling the voices", f"{config.tts.spec.display_name}: one line per voice",
                               lambda: workflow.sample_voices(config))
    if ok:
        screen.notify(f"The samples are in {workflow.samples_dir(config.tts.spec.name)}/ - listen, then pick "
                      f"the voice here.", timeout=10)


def narrator_rows(config: RemangaConfig) -> list[Row]:
    """The engine, then whatever that engine's voice needs."""
    rows = [Row("Narrator engine", config.tts.spec.display_name, _pick_engine,
                "the text-to-speech system", keys=("tts.engine",))]
    if config.tts.spec.settings_rows:
        rows += plugins.call(config.tts.spec.settings_rows, config)
    if config.tts.engine_block.voice_options():
        rows.append(Row("Hear the voices", "make samples", _hear_voices,
                        "one sample line per voice, to compare"))
    for row in rows:
        row.group = "Narration"
    return rows
