"""System-wide settings: GPU/codec preference and logging."""

from __future__ import annotations

from remanga.config.base import ConfigModel
from remanga.hardware import detect_cached


class SystemConfig(ConfigModel):
    prefer_gpu: bool = True

    # "auto" asks remanga/hardware.py what this machine's hardware encoder
    # actually is - h264_nvenc on NVIDIA, h264_videotoolbox on a Mac,
    # h264_vaapi on AMD, and plain libx264 where there is no hardware
    # encoder at all. The old default was a bare "h264_nvenc", which is
    # simply wrong on any machine without an NVIDIA card: the render would
    # probe an encoder that could never exist there and fall back to CPU
    # having learned nothing. An explicit codec name still wins, so a config
    # that names one keeps working exactly as before, and anyone who wants
    # to force a specific encoder still can.
    gpu_codec: str = "auto"
    fallback_codec: str = "libx264"

    def resolve_gpu_codec(self) -> str:
        """The hardware encoder to actually attempt on this machine.

        Resolution happens here rather than at load time so a config file
        stays portable: the same config.json can be copied between an
        NVIDIA box and a Mac and ask for the right encoder on each."""
        if self.gpu_codec and self.gpu_codec != "auto":
            return self.gpu_codec
        return detect_cached().video_encoder
    threads: int = 4
    log_level: str = "INFO"

    # Path to a small JSON file holding {"token": "hf_..."} - used by every
    # model download (Kokoro-82M, MAGI v3, DeepSeek-OCR-2) to
    # raise Hugging Face Hub's unauthenticated rate limit/speed, if set. See
    # remanga/hf_token.py for the full contract. Defaults to global/hf_token.json
    # - remanga/paths/global_assets.py:ensure_hf_token_file() creates it with
    # a blank {"token": ""} the first time any model download runs, so
    # there's always a real place to drop a token in without editing
    # config.json first. A blank "token" value there is silently treated as
    # "not configured" (unauthenticated, today's behavior) - only a
    # malformed file or one missing the "token" key entirely warns.
    hf_token_path: str = "global/hf_token.json"
