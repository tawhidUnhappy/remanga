"""Subtitle settings: reading a batch's word timings back off its audio.

Only needed when narration is batched (audio.batch_narration): a panel
synthesized on its own already knows how long it is, while a batch has to be
listened to."""

from __future__ import annotations

from remanga.config.base import ConfigModel


class SubtitlesConfig(ConfigModel):
    """faster-whisper in `.tools/venv-faster-whisper`, used for WHEN each
    word was said and never for what it was - the script is already known
    (see remanga/subtitles/align.py)."""

    # large-v3 rather than a distilled model: this runs once per batch at
    # about a tenth of real time (measured: 14s for a 142s take), so it is
    # nothing next to synthesis at 1.4x real time, and the accuracy is what
    # keeps proper nouns matching.
    hf_repo_id: str = "Systran/faster-whisper-large-v3"
    model_dir: str = "checkpoints/faster_whisper_large_v3"
    # The language the narration is in, given rather than detected: detection
    # on a long take can land on the wrong one and take the timings with it.
    language: str = "en"
    # float16 on a GPU; the worker falls back to int8 on a CPU, where float16
    # is unsupported rather than merely slow.
    compute_type: str = "float16"
