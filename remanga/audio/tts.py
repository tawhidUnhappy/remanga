"""One narration clip per panel, synthesized by the configured engine, and
audio_timing.json laying them out.

Resumes: a panel whose clip is already on disk in the same voice is reused,
except the panels around where an earlier run stopped (see resume.py). A
changed voice re-synthesizes everything."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydub import AudioSegment

from remanga import activity
from remanga.audio.batched import narrate_in_batches
from remanga.audio.clips import atomic_export, speech_bounds
from remanga.audio.manifest import verify_audio_manifest, write_audio_manifest
from remanga.audio.narration_voice import voice_changed_from
from remanga.audio.reference_text import ensure_reference_text
from remanga.audio.resample import load_audio
from remanga.audio.resume import clip_is_complete, clips_to_redo
from remanga.audio.synth import create_synthesizer
from remanga.audio.timing import panel_timing, write_timing
from remanga.config import AudioConfig, SubtitlesConfig, TTSConfig
from remanga.console import console, escape
from remanga.json_io import read_json_or
from remanga.narration import StoryPanel
from remanga.paths import get_audio_dir, get_audio_timing_path


class TTSEngine:
    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig,
                 subtitles_config: SubtitlesConfig | None = None):
        self.tts_config = tts_config
        self.audio_config = audio_config
        # Only batched narration needs it, and only to read its own takes
        # back; a per-panel chapter never builds one.
        self.subtitles_config = subtitles_config or SubtitlesConfig()
        self._synth = create_synthesizer(tts_config, audio_config)

    def generate_narration_audio(self, project_name: str, chapter_num: str, panels: list[StoryPanel],
                                 force: bool = False) -> Path:
        if not panels:
            raise ValueError(f"Chapter {chapter_num} has no panels to narrate.")

        # Before the model loads: a cloned voice matches closer when it is
        # told what its reference recording says, and finding that out needs
        # a different tool holding the GPU (audio/reference_text.py). Cached
        # beside the recording, so this is one transcription ever.
        ensure_reference_text(self.tts_config, self.subtitles_config)

        if self.audio_config.batch_narration:
            # A different enough job to be its own module: the panels are
            # joined, the takes are read back to find them again, and nothing
            # of the panel-by-panel resume applies. audio_timing.json comes
            # out in the same shape either way, which is why nothing
            # downstream knows which path made it.
            return narrate_in_batches(
                self._synth, self.tts_config, self.audio_config, self.subtitles_config,
                project_name, chapter_num, panels, force=force,
            )

        audio_dir = get_audio_dir(project_name, chapter_num)
        for stray_tmp in audio_dir.glob("*.wav.tmp"):
            stray_tmp.unlink(missing_ok=True)

        console.print(f"[cyan]Narrating {len(panels)} panel(s) with {self._synth.display_name}[/] "
                      f"[dim]({escape(self.tts_config.voice_detail)})[/]")

        # Zero trust on what's actually in the folder before reusing any of
        # it: a clip the last run finished with but that is gone now is not
        # something to quietly resynthesize around - it means the folder was
        # touched by something other than remanga, and the safe answer is to
        # stop and say so, not guess which files still mean what they did.
        if not force:
            verify_audio_manifest(audio_dir, chapter_num)

        timing_path = get_audio_timing_path(project_name, chapter_num)
        previous_timing = read_json_or(timing_path, {})
        voice_identity = self.tts_config.identity()
        was = voice_changed_from(previous_timing, voice_identity)
        if was and not force:
            console.print(f"[yellow]This chapter's clips are in another voice[/] "
                          f"[dim]({escape(was)}) - narrating every panel again.[/]")
            force = True

        panel_ids = [panel.panel_id for panel in panels]
        redo = set() if force else clips_to_redo(audio_dir, panel_ids)

        def reusable(panel_id: str) -> bool:
            return not force and panel_id not in redo and clip_is_complete(audio_dir, panel_id)

        # The model loads before the progress bar opens, so its loading spinner
        # and the bar never fight over the same terminal lines.
        if any(not reusable(panel_id) for panel_id in panel_ids):
            self._synth.ensure_ready()

        pause_ms = self.audio_config.pause_between_panels_ms
        timeline_ms, reused = 0, 0
        timing: list[dict[str, Any]] = []
        with activity.progress("Narrating panels", total=len(panels), unit="panels") as bar:
            for index, panel in enumerate(panels, start=1):
                clip = audio_dir / f"{panel.panel_id}.wav"
                if reusable(panel.panel_id):
                    segment = AudioSegment.from_file(clip)
                    reused += 1
                else:
                    raw = audio_dir / f"{panel.panel_id}_raw.wav"
                    self._synth.synthesize(text=panel.text, output_wav=raw)
                    # Through resample.load_audio: pydub's own resampler folds
                    # imaging noise into the clip going from 24 kHz to 44.1 kHz.
                    segment = load_audio(raw, self.audio_config.sample_rate, channels=1)
                    atomic_export(segment, clip)
                    raw.unlink(missing_ok=True)
                # Measured here because the clip is already in hand, whether
                # it was just synthesized or reused - so re-deciding the gap
                # costs a pass over the clips on disk, never the model.
                clip_start_ms, clip_end_ms = speech_bounds(segment)
                duration_ms = clip_end_ms - clip_start_ms
                timing.append(panel_timing(index, panel.panel_id, panel.text, clip.name, start_ms=timeline_ms,
                                          duration_ms=duration_ms, pause_after_ms=pause_ms,
                                          clip_start_ms=clip_start_ms))
                timeline_ms += duration_ms + pause_ms
                bar.advance()

        write_timing(timing_path, chapter_num, timing, total_ms=timeline_ms, voice=voice_identity)

        # Clips of panels no longer narrated (a panel now skipped) are removed.
        wanted = {f"{page_id}.wav" for page_id in panel_ids}
        for old in audio_dir.glob("*.wav"):
            if old.name not in wanted:
                old.unlink(missing_ok=True)

        # Written last, once every clip this run needed is actually on disk -
        # a manifest is only ever a record of a complete, finished set.
        write_audio_manifest(audio_dir, chapter_num, sorted(wanted))

        if reused:
            console.print(f"[dim cyan](Reused {reused} panel clip(s) already synthesized)[/]")
        console.print(f"[bold green]✓ Narration synthesized for {len(panels)} panel(s)[/]")
        return timing_path
