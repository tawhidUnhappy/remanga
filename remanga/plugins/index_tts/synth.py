"""IndexTTS-2.5 - talks to `.tools/venv-index-tts`/index_tts_worker.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.config import AudioConfig, TTSConfig
from remanga.models import ModelManager
from remanga.plugins import get
from remanga.plugins.index_tts.config import IndexTTSConfig
from remanga.workers import spawn_script_worker

SPEC = get("tts", "index_tts")
SCRIPTS = Path(__file__).parent / "scripts"

# What proves the download finished: the three checkpoints config.yaml names,
# and BigVGAN - the last of the auxiliary models the download script fetches.
EXPECTED_FILES = ("gpt.pth", "s2mel.pth", "codec.pth", "hf_cache/bigvgan/bigvgan_generator.pt")


def model_manager(config: IndexTTSConfig) -> ModelManager:
    """IndexTTS's weights - what the synthesizer loads and setup.py fetches."""
    return ModelManager(
        config.model_dir, config.hf_repo_id,
        tool_name=SPEC.tool_name, download_script=SCRIPTS / "download_index_tts.py",
        expected_files=EXPECTED_FILES, display_name=SPEC.display_name,
    )


class IndexTTSSynthesizer(BaseWorkerSynthesizer):
    """IndexTTS-2.5 - talks to `.tools/venv-index-tts`/index_tts_worker.py."""

    tool_name = SPEC.tool_name
    display_name = SPEC.display_name

    # IndexTTS samples, so a take made again under another seed is a different
    # reading - what audio/batched.py asks for when a take comes back with a
    # hum in it.
    seed = 0

    # No chunking and no ceiling: IndexTTS splits whatever it is given into
    # sentence segments itself (max_text_tokens_per_segment), each with its
    # own mel budget, and every segment is conditioned on the same recording -
    # there is no budget for a take to run out of. The take length stays the
    # ordinary MAX_TAKE_SECONDS rather than Kokoro's whole chapter: unlike
    # Kokoro it is not deterministic, so a bad take is worth being short.

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.engine_config: IndexTTSConfig = tts_config.index_tts
        super().__init__(audio_config, model_manager(self.engine_config))

    @property
    def chars_per_second(self) -> float:
        """Measured at speed 1.0 cloning mangakaking12.wav, as joined panels
        of a real chapter on the 3060: 785 characters came back 36.8s and 877
        42.9s - 21.3 and 20.4 (a lone 146-character panel, 17.0, carries the
        model's lead-in silence). 19 sits under the batches, since guessing
        too fast is what makes an ordinary take look like a collapse. Other
        speeds scale it directly: duration_factor is the length itself."""
        return 19.0 * max(float(self.engine_config.speed), 0.5)

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        return spawn_script_worker(
            self.tool_name, "plugins/index_tts", "index_tts_worker.py",
            "--model_dir", str(model_dir.resolve()),
        )

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, output_wav: Path, voice: str | None = None) -> dict[str, Any]:
        """One take's request: the text, the recording it is read in, and the
        pace. `voice` names another recording for this call only (the voice
        sampler)."""
        config = self.engine_config
        reference = config.reference_path(voice)
        if reference is None or not reference.is_file():
            raise FileNotFoundError(
                f"IndexTTS-2.5 clones a recording, and there is none to clone"
                f"{f' ({reference})' if reference else ''}. Put a clean recording of one person in "
                f"global/voice/ and pick it under Settings -> Narrator voice.")
        request: dict[str, Any] = {
            "cmd": "synthesize",
            "text": text,
            "output_path": str(output_wav.resolve()),
            "ref_audio": str(reference.resolve()),
            "lang": config.language,
            # Duration, not speed: 2x as fast is half as long.
            "duration_factor": max(0.5, min(2.0, 1.0 / max(float(config.speed), 0.01))),
            "interval_silence": int(config.interval_silence_ms),
        }
        if self.seed:
            request["seed"] = self.seed
        return request
