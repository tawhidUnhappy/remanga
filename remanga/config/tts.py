"""Text-to-speech engine settings - see remanga/audio/synth/."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class TTSEngineSpec:
    """Everything about a TTS engine that isn't code: what config.json calls
    it, what a human should see it called, one line on how it differs from
    the others, and whether it needs a transcript of the reference clip.

    This is the single description of an engine. The settings menu builds
    its engine picker from these specs (remanga/settings/engine.py) and
    remanga/audio/synth/ maps `name` to the Synthesizer class that drives
    it - so adding an engine can't leave a stale hand-written menu entry
    behind, and no screen anywhere spells an engine name out in a string
    literal."""

    name: str
    display_name: str
    summary: str
    needs_reference_text: bool = False


# Every TTS engine remanga can drive, each in its own isolated `.tools/venv-*`
# environment (see remanga/venvs.py) so their dependency pins - PyTorch,
# transformers, whatever else - never have to share a resolution. Adding a
# third engine later means: a new *Config class below, a spec here, a new
# worker script/Synthesizer subclass (remanga/audio/synth/), and a new
# isolated-venv provisioning block in bootstrap.sh - the same shape every
# existing engine already follows.
TTS_ENGINE_SPECS: Tuple[TTSEngineSpec, ...] = (
    TTSEngineSpec(
        "indextts-2.5", "IndexTTS-2.5",
        "Zero-shot cloning from a reference voice WAV alone",
    ),
    TTSEngineSpec(
        "audio8-tts-0.1b", "Audio8 TTS",
        "Also wants a text transcript of the reference voice clip",
        needs_reference_text=True,
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


class Audio8Config(BaseModel):
    """Settings specific to the audio8-tts-0.1b engine (see TTSConfig.engine) -
    Audio8/Audio8-TTS-Preview-0.1b on Hugging Face, a ~170M-parameter
    Falcon-H1-based zero-shot voice-cloning model with its own 44.1kHz codec
    decoder. Runs in its own isolated `.tools/venv-audio8` (transformers>=4.57,
    trust_remote_code=True - a different, sometimes incompatible pin from
    IndexTTS-2.5's own environment, hence the separate venv rather than
    sharing IndexTTS's)."""
    hf_repo_id: str = "Audio8/Audio8-TTS-Preview-0.1b"
    model_dir: str = "checkpoints/audio8_tts_0.1b"
    # Unlike IndexTTS-2.5 (a pure audio reference is enough for zero-shot
    # cloning), this model's processor also wants a transcription of
    # tts.spk_audio_prompt - accuracy of the transcript measurably affects
    # cloning quality per the model card, so this is asked for explicitly
    # rather than guessed/auto-transcribed.
    #
    # The transcript itself lives in its own text file, not inline here -
    # it's easy to fat-finger a long paragraph of free text while editing
    # config.json for something unrelated, and a broken transcript silently
    # degrades cloning quality rather than erroring. This field is just the
    # path to that file (read fresh by remanga/audio/synth/ at synth
    # start); default points at global/tts_reference.txt, alongside the
    # other shared assets (spk_audio_prompt, bgm_path) - see
    # remanga.settings.read_reference_text.
    reference_text_path: str = "global/tts_reference.txt"
    use_bf16: bool = True
    temperature: float = 0.7
    top_p: float = 0.9
    max_new_tokens: int = 512
    sample_rate: int = 44100


class TTSConfig(BaseModel):
    # Which engine actually synthesizes speech - one of TTS_ENGINES. Every
    # other top-level field below is IndexTTS-2.5's own settings (kept
    # unprefixed/unnested for backward compatibility with existing
    # config.json files); audio8-tts-0.1b's settings live in the nested
    # `audio8` block instead, since the two engines' knobs don't overlap
    # cleanly (different sample rate, different sampling defaults, a
    # reference transcript the other engine has no use for). Switch engines
    # by changing this one field - remanga/audio/synth/ picks the matching
    # Synthesizer, isolated venv, and model directory automatically.
    engine: str = "indextts-2.5"
    hf_repo_id: str = "IndexTeam/IndexTTS-2.5"
    model_dir: str = "checkpoints/indextts_2.5"
    cfg_path: str = "checkpoints/indextts_2.5/config.yaml"
    spk_audio_prompt: str = ""
    lang: str = "EN"
    use_bf16: bool = True
    speed: float = 1.0
    # IndexTTS-2.5's own defaults (indextts/infer_v2_5.py's infer_generator),
    # for natural-sounding prosody - a much lower temperature/top_p sounds
    # more "consistent" but trades away natural pitch/pacing variation for a
    # flatter, more robotic delivery. Emotion itself isn't configured here at
    # all: audio/synth/ sends no emo_vector, so IndexTTS-2.5 infers its own
    # emotion straight from each panel's text and punctuation (see
    # prompts/narration.md Rule 3) - temperature/top_p just control sampling
    # variety within whatever emotion that inference lands on.
    temperature: float = 0.8
    top_p: float = 0.8
    sample_rate: int = 22050
    # How long to wait for one panel's synthesize response before treating the
    # worker as hung and killing it (see audio/synth/base.py:synthesize). A single
    # 10-26 word panel normally finishes in well under a minute even on modest
    # hardware, so this is a generous ceiling, not a tight budget.
    synth_timeout_seconds: int = 180
    audio8: Audio8Config = Field(default_factory=Audio8Config)

    @property
    def spec(self) -> TTSEngineSpec:
        """This config's engine as a TTSEngineSpec - the display name,
        one-line summary and needs_reference_text flag every screen and
        synthesizer reads instead of re-testing `engine == "some-string"`."""
        return engine_spec(self.engine)

    @property
    def active_reference_text_path(self) -> Optional[str]:
        """Where the active engine's reference transcript lives, or None for
        an engine that doesn't use one - so callers ask this rather than
        reaching into `.audio8` and assuming which engine is selected."""
        return self.audio8.reference_text_path if self.spec.needs_reference_text else None
