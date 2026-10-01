"""Qwen3-TTS: preset narrators, a recording to clone, or a voice designed from
a description - slower, much more expressive.

    config.py          its settings block (tts.qwen in config.json)
    synth.py           the Synthesizer, and designing a voice
    reference.py       the clip a cloned voice is built from
    reference_text.py  what that clip says, read once with faster-whisper
    rows.py            its rows on the Settings screen
    scripts/           the worker and the weight download, run in .tools/venv-qwen-tts"""

from remanga.plugins import TTSEngine, register
from remanga.tool_envs.spec import InstallStep, ToolSpec

register("tool", ToolSpec(
    "qwen-tts", "Qwen3-TTS", "TTS engine - voices designed from a description, and preset narrators",
    steps=(
        # qwen-tts pulls transformers and its own tokenizer stack; torch
        # comes from this machine's wheel index (see hardware.py), which
        # is why it is named first rather than left to the dependency
        # resolver. flash-attn is deliberately left out: it builds from
        # source for many minutes and only saves some VRAM.
        InstallStep(("torch", "torchaudio", "qwen-tts", "soundfile", "huggingface-hub")),
    ),
))

# config.json has always called this engine "qwen", so that stays its name.
register("tts", TTSEngine(
    "qwen", "Qwen3-TTS",
    "Preset narrators, or a voice you design by describing it - slower, much more expressive",
    tool_name="qwen-tts",
    config="remanga.plugins.qwen_tts.config:QwenConfig",
    synthesizer="remanga.plugins.qwen_tts.synth:QwenSynthesizer",
    settings_rows="remanga.plugins.qwen_tts.rows:qwen_rows",
    # A cloned voice matches closer when told what its recording says, and
    # finding that out needs faster-whisper on the GPU before Qwen loads.
    prepare="remanga.plugins.qwen_tts.reference_text:ensure_reference_text",
    clones_voice=True,
    order=20,
))
