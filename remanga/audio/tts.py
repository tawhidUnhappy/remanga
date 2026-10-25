"""A chapter's narration, synthesized by the configured engine in as long
takes as it reads well (audio/batched.py), and audio_timing.json laying the
panels out over them."""

from __future__ import annotations

from pathlib import Path

from remanga import plugins
from remanga.audio.batched import narrate_in_batches
from remanga.audio.synth import create_synthesizer
from remanga.config import AudioConfig, SubtitlesConfig, TTSConfig
from remanga.narration import StoryPanel


class TTSEngine:
    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig,
                 subtitles_config: SubtitlesConfig | None = None):
        self.tts_config = tts_config
        self.audio_config = audio_config
        # To read the takes back: where each panel falls inside one.
        self.subtitles_config = subtitles_config or SubtitlesConfig()
        self._synth = create_synthesizer(tts_config, audio_config)

    def generate_narration_audio(self, project_name: str, chapter_num: str, panels: list[StoryPanel],
                                 force: bool = False) -> Path:
        if not panels:
            raise ValueError(f"Chapter {chapter_num} has no panels to narrate.")

        # Before the model loads: whatever the engine needs done first with
        # the GPU still free (Qwen reads its reference recording with
        # faster-whisper - plugins/qwen_tts/reference_text.py).
        if self.tts_config.spec.prepare:
            plugins.call(self.tts_config.spec.prepare, self.tts_config, self.subtitles_config)

        # The panels are joined into takes, the takes are read back to find
        # each panel again (audio/batched.py); audio_timing.json comes out
        # with one row per panel all the same.
        return narrate_in_batches(
            self._synth, self.tts_config, self.audio_config, self.subtitles_config,
            project_name, chapter_num, panels, force=force,
        )
