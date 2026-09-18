"""Which narrators remanga can use, and what each one is called.

The catalogue is separate from the settings (config/tts.py) because the two
change for different reasons: this says what engines EXIST, that says what has
been CHOSEN. Every screen and every command reads the engine's name and label
from here rather than spelling it out, so adding an engine can't leave a stale
menu entry behind.

Adding an engine is four small pieces and nothing else:
    1. a *Config block in config/tts.py (its voice, and whatever only it has)
    2. a TTSEngineSpec here, naming that block
    3. a Synthesizer in audio/synth/ + its worker script in audio/scripts/
    4. its environment in tool_envs/catalog.py
The settings screen picks up the engine by itself; anything it needs beyond a
voice list comes from the block's own `rows`/`edit` in ui/voice_settings.py."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TTSEngineSpec:
    """One engine: what config.json calls it, what a person should see it
    called, one line on how it differs, and which settings block is its own.

    `tool_name` is its isolated environment (`.tools/venv-<tool_name>`), and
    `clones_voice` says what its voice IS - a name from its own catalogue, or
    a recording/description it builds a voice from. Mixing those two up is how
    a correctly set voice once read as "Missing" on every screen."""

    name: str
    display_name: str
    summary: str
    config_attr: str
    tool_name: str
    clones_voice: bool = False


# Kokoro comes first, which makes it the default and the fallback for a name
# config.json doesn't know.
TTS_ENGINE_SPECS: tuple[TTSEngineSpec, ...] = (
    TTSEngineSpec(
        "kokoro", "Kokoro-82M",
        "Fixed studio voices - fast, and the same every time",
        config_attr="kokoro", tool_name="kokoro",
    ),
    TTSEngineSpec(
        "qwen", "Qwen3-TTS",
        "Preset narrators, or a voice you design by describing it - slower, much more expressive",
        config_attr="qwen", tool_name="qwen-tts", clones_voice=True,
    ),
)

TTS_ENGINES = tuple(spec.name for spec in TTS_ENGINE_SPECS)


def engine_spec(name: str) -> TTSEngineSpec:
    """The spec for `name`, falling back to the first engine for a name that
    isn't one - config.json is hand-editable, and a typo there should degrade
    to the default engine, not crash a settings screen."""
    lowered = (name or "").strip().lower()
    for spec in TTS_ENGINE_SPECS:
        if spec.name == lowered:
            return spec
    return TTS_ENGINE_SPECS[0]
