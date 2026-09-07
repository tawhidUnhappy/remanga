"""Text-to-speech engine settings - see remanga/audio/synth/.

Shape: the handful of settings that mean the same thing whichever engine is
driving (which engine that is, the narration language, the speaking rate,
how long to wait on a worker) sit at the top of TTSConfig, and everything
that belongs to ONE engine - its model, its sampling knobs, and its own
reference voice - lives in that engine's own block. So `tts.indextts` and
`tts.audio8` are two parallel blocks, each self-contained, and switching
engines switches which voice, which checkpoint and which sampling settings
are in play without either engine's answers overwriting the other's.

That symmetry is also why each engine has its OWN spk_audio_prompt rather
than sharing one: the two models clone from a reference clip differently
(audio8-tts-0.1b also wants a transcript of it, indextts-2.5 doesn't), so
the clip that sounds best under one is routinely not the clip that sounds
best under the other, and having to re-point a single shared field at a
different WAV every time you switch engines is how you end up synthesizing
a whole chapter in the wrong voice.

Older config.json files - which had indextts-2.5's settings unnested at the
`tts` top level and one shared `spk_audio_prompt` - are migrated on load by
TTSConfig._migrate_flat_engine_block below, so upgrading changes nothing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, Field, model_validator


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
TTS_ENGINE_SPECS: Tuple[TTSEngineSpec, ...] = (
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


class IndexTTSConfig(BaseModel):
    """Settings specific to the indextts-2.5 engine (see TTSConfig.engine) -
    IndexTeam/IndexTTS-2.5 on Hugging Face, zero-shot voice cloning from a
    reference WAV alone, no transcript needed. Runs in its own isolated
    `.tools/venv-indextts`.

    Every field here used to sit unnested at the `tts` top level; it moved
    into a block of its own so this engine and audio8-tts-0.1b are described
    the same way and can hold different answers - above all a different
    spk_audio_prompt. Existing config.json files are migrated automatically
    (TTSConfig._migrate_flat_engine_block)."""

    hf_repo_id: str = "IndexTeam/IndexTTS-2.5"
    model_dir: str = "checkpoints/indextts_2.5"
    cfg_path: str = "checkpoints/indextts_2.5/config.yaml"
    # The reference clip THIS engine clones from - see the module docstring
    # for why it isn't shared with audio8's.
    spk_audio_prompt: str = ""
    use_bf16: bool = True
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
    # Gain applied to THIS engine's synthesized narration clips, in decibels
    # (0.0 = untouched, positive = louder). Per engine because that is where
    # the problem is: the two models return audio at noticeably different
    # levels, so one narrator sits under the music while the other sits over
    # it, and a single shared number would just move the problem to whichever
    # engine wasn't being used that day.
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
    # The reference clip THIS engine clones from, independent of
    # indextts.spk_audio_prompt - see the module docstring. reference_text_path
    # below must be the transcript of THIS file, not of the other engine's.
    spk_audio_prompt: str = ""
    # Unlike IndexTTS-2.5 (a pure audio reference is enough for zero-shot
    # cloning), this model's processor also wants a transcription of this
    # engine's own spk_audio_prompt - accuracy of the transcript measurably
    # affects cloning quality per the model card, so this is asked for
    # explicitly rather than guessed/auto-transcribed.
    #
    # The transcript itself lives in its own text file, not inline here -
    # it's easy to fat-finger a long paragraph of free text while editing
    # config.json for something unrelated, and a broken transcript silently
    # degrades cloning quality rather than erroring. This field is just the
    # path to that file (read fresh by remanga/audio/synth/ at synth
    # start); default points at global/tts_reference.txt, alongside the
    # other shared assets (bgm_path) - see remanga.settings.read_reference_text.
    reference_text_path: str = "global/tts_reference.txt"
    use_bf16: bool = True
    temperature: float = 0.7
    top_p: float = 0.9
    max_new_tokens: int = 512
    sample_rate: int = 44100
    # Gain applied to THIS engine's synthesized narration clips, in decibels
    # (0.0 = untouched, positive = louder). Per engine because that is where
    # the problem is: the two models return audio at noticeably different
    # levels, so one narrator sits under the music while the other sits over
    # it, and a single shared number would just move the problem to whichever
    # engine wasn't being used that day.
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
    # This model generates a fixed budget of audio codec tokens per call
    # (max_new_tokens above) - text needing more than that budget's worth
    # of speech just gets cut off mid-generation, silently, with no error.
    # Any narration line longer than this many characters gets split on
    # sentence boundaries into several bounded calls instead (see
    # Audio8Synthesizer.chunk_max_chars / base.py's chunking path) and the
    # resulting clips re-joined - the rest of the pipeline never sees the
    # difference, it's still one WAV per panel. 220 chars is a conservative
    # empirical fit under 512 tokens for this model/tokenizer; lower it if
    # a chunk still gets truncated, raise it if chunks feel choppier than
    # they need to be.
    chunk_max_chars: int = 220


# The fields that used to live unnested at the `tts` top level, all of them
# indextts-2.5's own. Named here rather than inferred from IndexTTSConfig's
# field list so that a NEW field added to that block later isn't
# retroactively treated as something an old config.json might have had at
# the top level.
LEGACY_INDEXTTS_FIELDS = (
    "hf_repo_id", "model_dir", "cfg_path", "use_bf16", "temperature", "top_p", "sample_rate",
)


class TTSConfig(BaseModel):
    # Which engine actually synthesizes speech - one of TTS_ENGINES. Switch
    # engines by changing this one field: remanga/audio/synth/ picks the
    # matching Synthesizer, isolated venv, model directory and settings
    # block automatically.
    engine: str = "indextts-2.5"
    # Settings below this line are engine-independent - they mean the same
    # thing whichever engine is selected, which is exactly why they are not
    # in either block. `lang` is the narration language, `speed` is applied
    # by every engine (model-side where supported, ffmpeg atempo where not -
    # see audio/synth/), and the timeout guards any engine's worker process.
    lang: str = "EN"
    speed: float = 1.0
    # How long to wait for one panel's synthesize response before treating the
    # worker as hung and killing it (see audio/synth/base.py:synthesize). A single
    # 10-26 word panel normally finishes in well under a minute even on modest
    # hardware, so this is a generous ceiling, not a tight budget.
    synth_timeout_seconds: int = 180
    # One block per engine, each holding that engine's model, its sampling
    # settings and its own reference voice. See the module docstring.
    indextts: IndexTTSConfig = Field(default_factory=IndexTTSConfig)
    audio8: Audio8Config = Field(default_factory=Audio8Config)

    @model_validator(mode="before")
    @classmethod
    def _migrate_flat_engine_block(cls, data: Any) -> Any:
        """Reads a config.json written before the per-engine blocks existed.

        Back then indextts-2.5's settings sat unnested at the `tts` top
        level and `tts.spk_audio_prompt` was one voice shared by both
        engines. Pydantic ignores unknown keys, so without this an upgrade
        would silently drop a customized model_dir, a tuned temperature, or
        - worst of all - the reference voice, and fall back to defaults
        with nothing said. Here each legacy key is folded into the
        `indextts` block instead, and the shared voice seeds BOTH engines,
        so the first run after an upgrade sounds exactly like the last run
        before it and the two voices only diverge once someone changes one.

        setdefault throughout, never overwrite: a config.json that already
        has a real `indextts`/`audio8` block has been written by this
        version or edited by hand, and its explicit answer outranks
        whatever legacy key happens to be sitting next to it."""
        if not isinstance(data, dict):
            return data

        migrated: Dict[str, Any] = dict(data)
        indextts: Dict[str, Any] = dict(migrated.get("indextts") or {})
        for field_name in LEGACY_INDEXTTS_FIELDS:
            if field_name in migrated:
                indextts.setdefault(field_name, migrated.pop(field_name))

        legacy_voice = migrated.pop("spk_audio_prompt", None)
        if legacy_voice is not None:
            indextts.setdefault("spk_audio_prompt", legacy_voice)
            audio8: Dict[str, Any] = dict(migrated.get("audio8") or {})
            audio8.setdefault("spk_audio_prompt", legacy_voice)
            migrated["audio8"] = audio8

        if indextts:
            migrated["indextts"] = indextts
        return migrated

    @property
    def spec(self) -> TTSEngineSpec:
        """This config's engine as a TTSEngineSpec - the display name,
        one-line summary, settings block and needs_reference_text flag every
        screen and synthesizer reads instead of re-testing
        `engine == "some-string"`."""
        return engine_spec(self.engine)

    @property
    def engine_block(self) -> BaseModel:
        """The active engine's own settings block - `indextts` or `audio8`,
        resolved through its spec rather than by branching on the engine
        name. Returns the live sub-model, not a copy, so a caller applying a
        one-off override (see audio/tts.py's voice_override) can assign
        straight through it."""
        return getattr(self, self.spec.config_attr)

    @property
    def active_spk_audio_prompt(self) -> str:
        """The reference voice the ACTIVE engine clones from. Every caller
        that just wants "the voice being used" asks this instead of reaching
        into a block and assuming which engine is selected."""
        return getattr(self.engine_block, "spk_audio_prompt", "") or ""

    @property
    def active_voice_field(self) -> str:
        """Dotted config path of the active engine's voice, for the settings
        screens that edit a field by name (see remanga.settings.fields) and
        for error messages that tell someone where to fix it."""
        return voice_field_for(self.engine)

    @property
    def active_reference_text_path(self) -> Optional[str]:
        """Where the active engine's reference transcript lives, or None for
        an engine that doesn't use one - so callers ask this rather than
        reaching into `.audio8` and assuming which engine is selected."""
        return self.audio8.reference_text_path if self.spec.needs_reference_text else None
