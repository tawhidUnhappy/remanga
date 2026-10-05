"""IndexTTS-2.5's settings block: the recording whose voice reads every panel,
and how fast it reads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from remanga.config.base import ConfigModel
from remanga.paths import GLOBAL_DIR

VOICE_DIR = GLOBAL_DIR / "voice"
VOICE_EXTS = (".wav", ".mp3", ".flac", ".m4a", ".ogg", ".opus")


def recordings() -> list[Path]:
    """The recordings in global/voice/ a voice can be cloned from. Skips what
    remanga wrote there itself: samples, and the trimmed copies Qwen makes of
    a long reference (".first", ".reference")."""
    if not VOICE_DIR.is_dir():
        return []
    return sorted(path for path in VOICE_DIR.iterdir()
                  if path.is_file() and path.suffix.lower() in VOICE_EXTS
                  and not path.stem.startswith("sample_")
                  and ".first" not in path.stem and ".reference" not in path.stem)


class IndexTTSConfig(ConfigModel):
    """IndexTTS-2.5 (bilibili, 0.8B) in `.tools/venv-index-tts`. Every voice is
    a clone: there are no presets, and no transcript is needed - the model
    takes the speaker from the first 15 seconds of the recording itself.

    Emotion is never asked for. IndexTTS can steer it (by vector, by a second
    recording, or read from the text by a Qwen model), but narration keeps one
    steady register, so the delivery is whatever the recording already has."""

    # A file in global/voice/ (a bare name), or a path. Empty: the first
    # recording there.
    reference: str = ""
    # Speaking rate (1.0 = the recording's own pace). Applied by the model as
    # its duration_factor, the inverse of this - so no ffmpeg pass afterwards.
    speed: float = 1.0
    # IndexTTS's language tag (EN, ZH, JA, ES, AR).
    language: str = "EN"
    # Silence the model leaves between the segments (~120 tokens, a few
    # sentences) it splits a take into, in ms; upstream's default is 200.
    # Sentences inside one segment keep the model's own pause - measured
    # 0.16-0.38s on a real chapter.
    interval_silence_ms: int = 450
    hf_repo_id: str = "IndexTeam/IndexTTS-2.5"
    model_dir: str = "checkpoints/index_tts_2_5"

    def voice_options(self) -> list[tuple[str, str]]:
        """Each recording in global/voice/ - see KokoroConfig.voice_options.
        A name here is what `reference` and a synthesize call's `voice` take."""
        return [(path.name, "a clone of this recording") for path in recordings()]

    def reference_path(self, voice: str | None = None) -> Path | None:
        """The recording that narrates: `voice` for one call, else the
        configured one, else the first in global/voice/."""
        name = voice or self.reference
        if not name:
            found = recordings()
            return found[0] if found else None
        path = Path(name)
        return path if path.is_absolute() or path.parent != Path() else VOICE_DIR / name

    @property
    def voice_label(self) -> str:
        path = self.reference_path()
        return f"clone of {path.name}" if path else "no recording in global/voice/"

    @property
    def voice_detail(self) -> str:
        path = self.reference_path()
        return f"cloned from {path}" if path else "no recording - put one in global/voice/"

    def identity(self) -> dict[str, Any]:
        path = self.reference_path()
        sample = {"sample": path.name, "sample_mtime_ns": path.stat().st_mtime_ns} \
            if path and path.is_file() else {"sample": ""}
        return {"engine": "index_tts", **sample, "speed": round(float(self.speed), 3),
                "language": self.language, "interval_silence_ms": self.interval_silence_ms}
