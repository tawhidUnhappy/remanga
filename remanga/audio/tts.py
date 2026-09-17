"""One narration clip per story page, synthesized with Chatterbox Turbo, and
audio_timing.json laying them out.

The clips are what the model returns - no speed change, gain or fades (user
request) - only converted to the project's sample rate for the mix.

Resumes: a page whose clip is already on disk in the same voice is reused,
except the pages around where an earlier run stopped (see resume.py). A
different recording to clone re-synthesizes everything."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydub import AudioSegment

from remanga import activity
from remanga.audio.clips import atomic_export
from remanga.audio.narration_voice import narration_voice_identity, voice_changed_from
from remanga.audio.resample import load_audio
from remanga.audio.resume import clip_is_complete, clips_to_redo
from remanga.audio.synth import create_synthesizer
from remanga.audio.timing import page_timing, write_timing
from remanga.config import AudioConfig, TTSConfig
from remanga.console import console, escape
from remanga.json_io import read_json_or
from remanga.narration import StoryPage
from remanga.paths import get_audio_dir, get_audio_timing_path

# Chatterbox Turbo refuses a reference recording this short or shorter.
MIN_VOICE_SECONDS = 5.0


def check_voice(tts_config: TTSConfig) -> Path:
    """The recording to clone, checked before any model loads."""
    path = tts_config.voice_path
    if not path.is_file():
        raise ValueError(f"The voice recording '{tts_config.voice}' doesn't exist - put one in global/voice/ "
                         f"and pick it in Settings.")
    seconds = len(AudioSegment.from_file(path)) / 1000
    if seconds <= MIN_VOICE_SECONDS:
        raise ValueError(f"The voice recording '{tts_config.voice}' is {seconds:.1f}s long - Chatterbox needs more "
                         f"than {MIN_VOICE_SECONDS:g} seconds of one person speaking.")
    return path


class TTSEngine:
    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.audio_config = audio_config
        self._synth = create_synthesizer(tts_config, audio_config)

    def generate_narration_audio(self, project_name: str, chapter_num: str, pages: list[StoryPage],
                                 force: bool = False) -> Path:
        if not pages:
            raise ValueError(f"Chapter {chapter_num} has no story pages to narrate.")
        voice = check_voice(self.tts_config)

        audio_dir = get_audio_dir(project_name, chapter_num)
        for stray_tmp in audio_dir.glob("*.wav.tmp"):
            stray_tmp.unlink(missing_ok=True)

        console.print(f"[cyan]Narrating {len(pages)} page(s) with {self._synth.display_name}[/] "
                      f"[dim]({escape(self.tts_config.voice_detail)})[/]")

        timing_path = get_audio_timing_path(project_name, chapter_num)
        previous_timing = read_json_or(timing_path, {})
        voice_identity = narration_voice_identity(voice)
        was = voice_changed_from(previous_timing, voice_identity)
        if was and not force:
            console.print(f"[yellow]This chapter's clips are in another voice[/] [dim]({escape(was)}) - narrating "
                          f"every page again.[/]")
            force = True

        page_ids = [page.page_id for page in pages]
        redo = set() if force else clips_to_redo(audio_dir, page_ids)

        def reusable(page_id: str) -> bool:
            return not force and page_id not in redo and clip_is_complete(audio_dir, page_id)

        # The model loads before the progress bar opens, so its loading spinner
        # and the bar never fight over the same terminal lines.
        if any(not reusable(page_id) for page_id in page_ids):
            self._synth.ensure_ready()

        pause_ms = self.audio_config.pause_between_pages_ms
        timeline_ms, reused = 0, 0
        timing: list[dict[str, Any]] = []
        with activity.progress("Narrating pages", total=len(pages), unit="pages") as bar:
            for index, page in enumerate(pages, start=1):
                clip = audio_dir / f"{page.page_id}.wav"
                if reusable(page.page_id):
                    segment = AudioSegment.from_file(clip)
                    reused += 1
                else:
                    raw = audio_dir / f"{page.page_id}_raw.wav"
                    self._synth.synthesize(text=page.text, voice=str(voice), output_wav=raw)
                    # Through resample.load_audio: pydub's own resampler folds
                    # imaging noise into the clip going from 24 kHz to 44.1 kHz.
                    segment = load_audio(raw, self.audio_config.sample_rate, channels=1)
                    atomic_export(segment, clip)
                    raw.unlink(missing_ok=True)
                timing.append(page_timing(index, page.page_id, page.text, clip.name, start_ms=timeline_ms,
                                          duration_ms=len(segment), pause_after_ms=pause_ms))
                timeline_ms += len(segment) + pause_ms
                bar.advance()

        write_timing(timing_path, chapter_num, timing, total_ms=timeline_ms, voice=voice_identity)

        # Clips of pages no longer narrated (a page now skipped) are removed.
        wanted = {f"{page_id}.wav" for page_id in page_ids}
        for old in audio_dir.glob("*.wav"):
            if old.name not in wanted:
                old.unlink(missing_ok=True)

        if reused:
            console.print(f"[dim cyan](Reused {reused} page clip(s) already synthesized)[/]")
        console.print(f"[bold green]✓ Narration synthesized for {len(pages)} page(s)[/]")
        return timing_path
