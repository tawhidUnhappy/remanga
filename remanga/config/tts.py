"""Narration settings - Chatterbox Turbo, see remanga/audio/synth/chatterbox.py.

ResembleAI/chatterbox-turbo (350M, MIT) runs in its own isolated
`.tools/venv-chatterbox`. It has no built-in voices: it clones whoever speaks
in `voice`, a recording. It runs at the model's own defaults - no speed
change, no gain, no post-processing of the clips (user request)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import field_validator, model_validator

from remanga.config.base import ConfigModel
from remanga.paths import REPO_ROOT

DISPLAY_NAME = "Chatterbox Turbo"
DEFAULT_VOICE = "global/voice/narrator.wav"
VOICE_EXTS = (".wav", ".mp3", ".flac", ".m4a", ".ogg", ".opus")


class TTSConfig(ConfigModel):
    # The recording to clone: one speaker, no music, longer than 5 seconds
    # (Turbo refuses shorter). Its first 10-15 seconds are what the delivery is
    # imitated from. Relative paths are from the remanga folder.
    voice: str = DEFAULT_VOICE
    # How long one synthesize call may take before the worker is treated as hung.
    synth_timeout_seconds: int = 180
    hf_repo_id: str = "ResembleAI/chatterbox-turbo"
    model_dir: str = "checkpoints/chatterbox_turbo"

    @model_validator(mode="before")
    @classmethod
    def _from_older_versions(cls, data: Any) -> Any:
        """Kokoro's settings (a voice NAME, speed, gain, its model) mean nothing
        to Chatterbox and are dropped; a `chatterbox` block from the
        multi-engine version is lifted up.

        Every field this model HAS is kept, whatever it holds: this also runs
        on assignment (validate_assignment), where dropping a field for not
        being in a shortlist left the model without it - and saving the
        settings then died on the missing attribute."""
        if not isinstance(data, dict):
            return data
        kept = {key: value for key, value in data.items() if key in cls.model_fields}
        block = data.get("chatterbox")
        if isinstance(block, dict) and block.get("voice"):
            kept["voice"] = block["voice"]
        # Kokoro's model and repo: back to this engine's own defaults.
        for field_name in ("hf_repo_id", "model_dir"):
            if "chatterbox" not in str(kept.get(field_name, "chatterbox")).lower():
                kept.pop(field_name, None)
        return kept

    @field_validator("voice")
    @classmethod
    def _voice_is_a_recording(cls, value: str) -> str:
        """A Kokoro voice name ("af_heart") left in an older config is not a
        recording - fall back to the default clip rather than fail later."""
        return value if Path(str(value)).suffix.lower() in VOICE_EXTS else DEFAULT_VOICE

    @property
    def voice_path(self) -> Path:
        path = Path(self.voice).expanduser()
        return path if path.is_absolute() else REPO_ROOT / path

    @property
    def voice_label(self) -> str:
        return Path(self.voice).name

    @property
    def voice_detail(self) -> str:
        return f"clone of {self.voice}"
