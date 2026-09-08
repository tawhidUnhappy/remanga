"""Which TTS engines exist, and what each one is called.

Separated from the settings models in config/tts.py because these two
things change for different reasons and are read by different callers: this
is the catalogue (what engines there are, what config.json names them, how
they differ), while tts.py is the shape of what a user has *chosen*. The
synthesizers, the wizard menu and the command help all want the catalogue
and nothing else - see audio/synth/ and commands/setup_rows.py.

Re-exported from remanga.config.tts, so existing imports keep working."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TTSEngineSpec:
    """Everything about a TTS engine that isn't code: what config.json calls
    it, what a human should see it called, one line on how it differs from
    the others, which TTSConfig block holds its settings, and whether it
    needs a transcript of the reference clip.

    This is the single description of an engine. The settings menu builds
    its engine picker from these specs (remanga/settings/engine.py) and
    remanga/audio/synth/ maps `name` to the Synthesizer class that drives
    it - so adding an engine can't leave a stale hand-written menu entry
    behind, and no screen anywhere spells an engine name out in a string
    literal.

    `config_attr` is what lets that stay true for the per-engine blocks
    too: TTSConfig.engine_block resolves it instead of branching on the
    engine name, so "which block holds the active engine's voice" is
    answered by the same spec that answers everything else about it."""

    name: str
    display_name: str
    summary: str
    config_attr: str
    needs_reference_text: bool = False


# Every TTS engine remanga can drive, each in its own isolated `.tools/venv-*`
# environment (see remanga/venvs.py) so their dependency pins - PyTorch,
# transformers, whatever else - never have to share a resolution. Adding a
# third engine later means: a new *Config class below, a spec here, a new
# worker script/Synthesizer subclass (remanga/audio/synth/), and a new
# isolated-venv provisioning block in bootstrap.sh - the same shape every
# existing engine already follows.
TTS_ENGINE_SPECS: tuple[TTSEngineSpec, ...] = (
    TTSEngineSpec(
        "indextts-2.5", "IndexTTS-2.5",
        "Zero-shot cloning from a reference voice WAV alone",
        config_attr="indextts",
    ),
    TTSEngineSpec(
        "audio8-tts-0.1b", "Audio8 TTS",
        "Also wants a text transcript of the reference voice clip",
        config_attr="audio8", needs_reference_text=True,
    ),
)

TTS_ENGINES = tuple(spec.name for spec in TTS_ENGINE_SPECS)


def engine_spec(name: str) -> TTSEngineSpec:
    """The spec for `name`, falling back to the first engine for an
    unrecognized value - config.json is hand-editable, and a typo there
    should degrade to the default engine (which is what
    remanga.audio.synth already does), not crash a settings screen."""
    lowered = (name or "").strip().lower()
    for spec in TTS_ENGINE_SPECS:
        if spec.name == lowered:
            return spec
    return TTS_ENGINE_SPECS[0]


def voice_field_for(engine: str) -> str:
    """Dotted config path of ONE engine's reference voice, by engine name -
    for the callers that need an engine other than the active one:
    `remanga tts --engine X` runs a single chapter on a different engine
    without redefining what config.json says, and the voice it validates
    and asks for has to be that engine's, not the configured engine's."""
    return f"tts.{engine_spec(engine).config_attr}.spk_audio_prompt"
