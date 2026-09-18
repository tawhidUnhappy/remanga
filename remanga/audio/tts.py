"""One narration clip per panel, synthesized with Kokoro-82M, and
audio_timing.json laying them out.

Resumes: a panel whose clip is already on disk in the same voice is reused,
except the panels around where an earlier run stopped (see resume.py). A
changed voice re-synthesizes everything; a changed volume boost is applied as
the difference to the clips already there."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydub import AudioSegment

from remanga import activity
from remanga.audio.clips import apply_edge_fades, apply_gain, atomic_export, clamp_boost, is_audible_gain
from remanga.audio.narration_voice import narration_voice_identity, voice_changed_from
from remanga.audio.resample import load_audio
from remanga.audio.resume import clip_is_complete, clips_to_redo
from remanga.audio.synth import create_synthesizer
from remanga.audio.timing import panel_timing, write_timing
from remanga.config import AudioConfig, TTSConfig
from remanga.config.kokoro_voices import VOICE_BY_NAME
from remanga.console import console, escape
from remanga.json_io import read_json_or
from remanga.narration import StoryPanel
from remanga.paths import get_audio_dir, get_audio_timing_path


class TTSEngine:
    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.audio_config = audio_config
        self._synth = create_synthesizer(tts_config, audio_config)

    def generate_narration_audio(self, project_name: str, chapter_num: str, panels: list[StoryPanel],
                                 force: bool = False) -> Path:
        voice = self.tts_config.voice
        if voice not in VOICE_BY_NAME:
            raise ValueError(f"'{voice}' is not a Kokoro voice - pick one in Settings.")
        if not panels:
            raise ValueError(f"Chapter {chapter_num} has no panels to narrate.")

        audio_dir = get_audio_dir(project_name, chapter_num)
        for stray_tmp in audio_dir.glob("*.wav.tmp"):
            stray_tmp.unlink(missing_ok=True)

        console.print(f"[cyan]Narrating {len(panels)} panel(s) with {self._synth.display_name}[/] "
                      f"[dim](voice {escape(self.tts_config.voice_detail)}, speed {self.tts_config.speed}x)[/]")

        timing_path = get_audio_timing_path(project_name, chapter_num)
        previous_timing = read_json_or(timing_path, {})
        voice_identity = narration_voice_identity(voice, self.tts_config.speed)
        was = voice_changed_from(previous_timing, voice_identity)
        if was and not force:
            console.print(f"[yellow]This chapter's clips are in another voice or speed[/] "
                          f"[dim]({escape(was)}) - narrating every panel again.[/]")
            force = True

        boost_db = clamp_boost(self.tts_config.volume_boost_db)
        boost_delta_db = boost_db - clamp_boost(previous_timing.get("volume_boost_db", 0.0))
        clipped: list[str] = []

        def boosted(segment: AudioSegment, gain_db: float, panel_id: str) -> AudioSegment:
            out, did_clip = apply_gain(segment, gain_db)
            if did_clip:
                clipped.append(panel_id)
            return out

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
                    if is_audible_gain(boost_delta_db):
                        segment = boosted(segment, boost_delta_db, panel.panel_id)
                        atomic_export(segment, clip)
                    reused += 1
                else:
                    raw = audio_dir / f"{panel.panel_id}_raw.wav"
                    self._synth.synthesize(text=panel.text, voice=voice, output_wav=raw)
                    # Through resample.load_audio: pydub's own resampler folds
                    # imaging noise into the clip going from 24 kHz to 44.1 kHz.
                    segment = load_audio(raw, self.audio_config.sample_rate, channels=1)
                    segment = apply_edge_fades(segment, self.audio_config.edge_fade_ms)
                    segment = boosted(segment, boost_db, panel.panel_id)
                    atomic_export(segment, clip)
                    raw.unlink(missing_ok=True)
                timing.append(panel_timing(index, panel.panel_id, panel.text, clip.name, start_ms=timeline_ms,
                                          duration_ms=len(segment), pause_after_ms=pause_ms))
                timeline_ms += len(segment) + pause_ms
                bar.advance()

        write_timing(timing_path, chapter_num, timing, boost_db=boost_db, total_ms=timeline_ms, voice=voice_identity)

        # Clips of panels no longer narrated (a panel now skipped) are removed.
        wanted = {f"{page_id}.wav" for page_id in panel_ids}
        for old in audio_dir.glob("*.wav"):
            if old.name not in wanted:
                old.unlink(missing_ok=True)

        if clipped:
            console.print(f"[yellow]{len(clipped)} panel(s) clipped at {boost_db:+.1f} dB[/] "
                          f"[dim]({', '.join(clipped[:5])}) - lower the volume boost; only the difference is "
                          f"re-applied.[/]")
        if reused:
            console.print(f"[dim cyan](Reused {reused} panel clip(s) already synthesized)[/]")
        console.print(f"[bold green]✓ Narration synthesized for {len(panels)} panel(s)[/]")
        return timing_path
