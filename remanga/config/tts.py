"""Text-to-speech engine settings - see remanga/audio/synth/.

Shape: the handful of settings that mean the same thing whichever engine is
driving (which engine that is, the speaking rate, how long to wait on a
worker) sit at the top of TTSConfig, and everything that belongs to ONE
engine - its model, its sampling knobs, its voice - lives in that engine's
own block. There is one engine today; the split is kept because it is what
makes adding or removing one a contained change (see tts_engines.py).

The big change from the IndexTTS-2.5 / Audio8 era: Kokoro does not clone a
voice from a reference clip. It ships fixed, named voices, so the narrator
is chosen from a list (config/kokoro_voices.py) rather than pointed at a
WAV. Everything those engines needed and Kokoro does not - the reference
clip, its transcript, per-engine sampling temperature - is gone rather than
carried forward, and old config.json files are migrated on load by
TTSConfig._migrate_retired_engines below."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from remanga.config.kokoro_voices import (
    DEFAULT_VOICE,
    KOKORO_VOICES,
    KokoroVoice,
    lang_code_for,
    voice_spec,
)
from remanga.config.tts_engines import (
    TTS_ENGINE_SPECS,
    TTS_ENGINES,
    TTSEngineSpec,
    engine_spec,
    voice_field_for,
)

# Re-exported so `from remanga.config.tts import engine_spec, TTS_ENGINES`
# keeps working - see tts_engines.py for where these now live.
__all__ = [
    "KOKORO_VOICES",
    "TTS_ENGINES",
    "TTS_ENGINE_SPECS",
    "KokoroConfig",
    "KokoroVoice",
    "TTSConfig",
    "TTSEngineSpec",
    "engine_spec",
    "voice_field_for",
]


class KokoroConfig(BaseModel):
    """Settings specific to the kokoro engine - hexgrad/Kokoro-82M on
    Hugging Face, an 82M-parameter StyleTTS 2 / iSTFTNet model with fixed
    built-in voices. Runs in its own isolated `.tools/venv-kokoro`.

    No reference clip and no cloning: `voice` names one of the model's own
    voices (see config/kokoro_voices.py). That is the point of it - the
    engines it replaced derived the narrator's whole delivery from a clip,
    which made the clip the single largest source of quality problems."""

    hf_repo_id: str = "hexgrad/Kokoro-82M"
    model_dir: str = "checkpoints/kokoro_82m"
    # Which of Kokoro's built-in voices narrates. Defaults to its
    # highest-graded voice; see kokoro_voices.DEFAULT_VOICE for why that is
    # the default rather than the closest match to any particular narrator.
    voice: str = DEFAULT_VOICE
    # Gain applied to synthesized narration clips, in decibels (0.0 =
    # untouched, positive = louder).
    #
    # Applied to each panel's clip as it is written (audio/tts.py), so the
    # WAVs on disk really are louder - not a flag read at mix time. The
    # audible result in the finished video is mostly VOICE-VS-MUSIC balance
    # rather than a louder file: audio/mix.py's EBU R128 loudnorm pass
    # normalizes the whole master to a fixed target afterwards, so boosting
    # the narration pushes the BGM down under it rather than raising the
    # final output level. Turn off audio.enable_loudnorm if you want the
    # boost to survive into the master's absolute level too.
    #
    # Changing this does NOT require re-synthesizing: audio_timing.json
    # records the gain baked into the clips it describes, and the next tts
    # run applies only the difference to clips it would otherwise reuse -
    # see audio/tts.py. Boosting far enough to clip is possible (pydub
    # saturates rather than wraps); a run that clips says so.
    volume_boost_db: float = 0.0
    # Kokoro's native output rate. Not a resampling knob - it is what the
    # model emits, and the pipeline resamples from here (audio/resample.py).
    sample_rate: int = 24000

    @property
    def spec(self) -> KokoroVoice:
        """The active voice's catalogue entry - its label, grade and accent."""
        return voice_spec(self.voice)

    @property
    def lang_code(self) -> str:
        """Kokoro's one-character accent code for the active voice.

        Derived rather than configured: Kokoro takes this separately from
        the voice name, and a mismatch makes a voice speak through the wrong
        accent's phonemes instead of raising anything."""
        return lang_code_for(self.voice)


# Settings that belonged to the retired IndexTTS-2.5 / Audio8 blocks and
# have no meaning under Kokoro. Named explicitly so migration can drop them
# quietly rather than leaving them to fail validation on load.
RETIRED_ENGINE_BLOCKS = ("indextts", "audio8")
RETIRED_TOP_LEVEL_FIELDS = (
    "hf_repo_id", "model_dir", "cfg_path", "use_bf16", "temperature", "top_p",
    "sample_rate", "spk_audio_prompt",
)


class TTSConfig(BaseModel):
    # Which engine actually synthesizes speech - one of TTS_ENGINES.
    engine: str = "kokoro"
    # Settings below this line are engine-independent.
    lang: str = "EN"
    speed: float = 1.0
    # How long to wait for one panel's synthesize response before treating the
    # worker as hung and killing it (see audio/synth/base.py:synthesize). Kokoro
    # synthesizes a panel in well under a second on any GPU and a few seconds on
    # CPU, so this is a generous ceiling, not a tight budget.
    synth_timeout_seconds: int = 180
    kokoro: KokoroConfig = Field(default_factory=KokoroConfig)

    @model_validator(mode="before")
    @classmethod
    def _migrate_retired_engines(cls, data: Any) -> Any:
        """Reads a config.json written for IndexTTS-2.5 or Audio8.

        Those engines cloned from a reference WAV; Kokoro has fixed voices,
        so there is nothing in their settings worth carrying forward - a
        `spk_audio_prompt` path is not a Kokoro voice name, and a
        temperature it has no sampler for is noise. Pydantic ignores unknown
        keys, so the practical job here is narrower than the old migration's:
        drop the retired blocks and the older flat keys, and force `engine`
        onto a name that still exists, so an upgraded install starts in a
        valid state instead of failing validation or selecting an engine
        whose code was deleted."""
        if not isinstance(data, dict):
            return data

        migrated: dict[str, Any] = dict(data)
        for block in RETIRED_ENGINE_BLOCKS:
            migrated.pop(block, None)
        for field_name in RETIRED_TOP_LEVEL_FIELDS:
            migrated.pop(field_name, None)

        if str(migrated.get("engine", "")).strip().lower() not in TTS_ENGINES:
            migrated["engine"] = TTS_ENGINES[0]
        return migrated

    @property
    def spec(self) -> TTSEngineSpec:
        """This config's engine as a TTSEngineSpec - the display name,
        one-line summary and settings block every screen reads instead of
        re-testing `engine == "some-string"`."""
        return engine_spec(self.engine)

    @property
    def engine_block(self) -> BaseModel:
        """The active engine's own settings block, resolved through its spec
        rather than by branching on the engine name. Returns the live
        sub-model, not a copy, so a caller applying a one-off override (see
        audio/tts.py's voice_override) can assign straight through it."""
        return getattr(self, self.spec.config_attr)

    @property
    def active_voice(self) -> str:
        """The voice the ACTIVE engine narrates in. Every caller that just
        wants "the voice being used" asks this instead of reaching into a
        block and assuming which engine is selected."""
        return getattr(self.engine_block, "voice", "") or ""

    @property
    def active_voice_field(self) -> str:
        """Dotted config path of the active engine's voice, for the settings
        screens that edit a field by name (see remanga.settings.fields) and
        for error messages that tell someone where to fix it."""
        return voice_field_for(self.engine)
