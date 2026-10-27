"""Kokoro-82M's rows on the Settings screen: the voice, and another voice mixed
into it (2026-10-27). Read at its own pace - no speed row since 2026-10-27, the
user wants every voice raw, never sped up. See
ui/voice_settings.py for the rows every engine shares and how a row works."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.plugins.kokoro.voices import KOKORO_VOICES, marked_label
from remanga.ui.dialogs import Ask, Choice, number_check
from remanga.ui.voice_rows import Row, wait_for


async def _pick_kokoro_voice(screen, config: RemangaConfig) -> None:
    voice = await wait_for(screen)(Choice(
        "Narrator voice", [(marked_label(v), f"grade {v.grade} · {v.accent}", v.name) for v in KOKORO_VOICES],
        current=config.tts.kokoro.voice,
        note="Kokoro-82M's own voices, best graded first - ★ marks the best one. A new voice narrates chapters again."))
    if voice:
        config.tts.kokoro.voice = voice


MIX_SHARES = ((10, "a hint of it"), (20, "a little"), (30, "clearly blended - a good start"),
              (40, "a lot"), (50, "half and half"))


async def _pick_mix_voice(screen, config: RemangaConfig) -> None:
    kokoro = config.tts.kokoro
    options = [("No mix", "the narrator voice alone", "")] + [
        (marked_label(v), f"grade {v.grade} · {v.accent}", v.name) for v in KOKORO_VOICES if v.name != kokoro.voice]
    picked = await wait_for(screen)(Choice(
        "Mix with", options, current=kokoro.mix.name if kokoro.mix else "",
        note="A second voice blended into the narrator voice - together they make a voice of their own. "
             "The accent stays the narrator voice's. A new mix narrates chapters again."))
    if picked is not None:
        kokoro.mix_voice = picked


async def _set_mix_share(screen, config: RemangaConfig) -> None:
    kokoro = config.tts.kokoro
    options = [(f"{percent}%", hint, percent) for percent, hint in MIX_SHARES]
    if kokoro.mix_percent not in [p for p, _ in MIX_SHARES]:
        options.append((f"{kokoro.mix_percent}%", "your own share", kokoro.mix_percent))
    options.append(("Custom...", "type a share from 1 to 99", "custom"))
    note = (f"How much of {kokoro.mix.label if kokoro.mix else 'the second voice'} is in the mix. "
            f"Past about half it is more that voice than the narrator's.")
    percent = await wait_for(screen)(Choice("Mix share", options, current=kokoro.mix_percent, note=note))
    if percent == "custom":
        percent = await wait_for(screen)(Ask("Mix share", "Percent of the second voice (1-99)",
                                             value=str(kokoro.mix_percent), check=number_check(1, 99), note=note))
    if percent is not None:
        kokoro.mix_share = round(float(percent)) / 100


def kokoro_rows(config: RemangaConfig) -> list[Row]:
    kokoro = config.tts.kokoro
    rows = [
        Row("Narrator voice", marked_label(kokoro.spec), _pick_kokoro_voice, "the voice that reads every panel",
            keys=("tts.kokoro.voice",)),
        Row("Mix with", kokoro.mix.label if kokoro.mix else "no mix", _pick_mix_voice,
            "blend a second voice in: a voice of its own", keys=("tts.kokoro.mix_voice",)),
    ]
    if kokoro.mix:  # the share only means something with a voice to mix
        rows.append(Row("Mix share", f"{kokoro.mix_percent}%", _set_mix_share, "how much of the second voice",
                        keys=("tts.kokoro.mix_share",)))
    return rows
