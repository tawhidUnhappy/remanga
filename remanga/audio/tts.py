from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from pydub import AudioSegment
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn

from remanga import setup
from remanga.audio.synth import IndexTTSSynthesizer
from remanga.config import AudioConfig, RemangaConfig, TTSConfig
from remanga.json_io import read_json, write_json
from remanga.paths import get_chapter_dir

console = Console()


class TTSEngine:
    def __init__(self, tts_config: Optional[TTSConfig] = None, audio_config: Optional[AudioConfig] = None):
        self.tts_config = tts_config or TTSConfig()
        self.audio_config = audio_config or AudioConfig()
        self._synth = IndexTTSSynthesizer(self.tts_config, self.audio_config)

    def generate_narration_audio(
        self,
        project_name: str,
        chapter_num: str,
        voice_override: Optional[str] = None,
        interactive: bool = True,
        force: bool = False,
    ) -> Path:
        """
        Synthesizes narration audio per panel with IndexTTS-2.5.
        Resumes automatically by checking existing panel WAV clips.
        """
        full_config = RemangaConfig.load()
        if voice_override:
            full_config.tts.spk_audio_prompt = voice_override
            self.tts_config.spk_audio_prompt = voice_override

        spk_prompt_path = setup.ensure_valid_voice_prompt(full_config, interactive=interactive)
        self.tts_config.spk_audio_prompt = spk_prompt_path

        chapter_dir = get_chapter_dir(project_name, chapter_num)
        narration_path = chapter_dir / "narration.json"
        audio_dir = chapter_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        if not narration_path.exists():
            raise FileNotFoundError(
                f"Missing narration script: {narration_path}\n"
                f"Please provide your narration JSON file before generating speech."
            )

        data = read_json(narration_path)

        narration_entries = data.get("narration", [])
        if not narration_entries:
            raise ValueError(f"No narration entries found in {narration_path}")

        console.print(
            f"[cyan]Synthesizing consistent speech via IndexTTS-2.5[/] "
            f"[dim](Lang: {self.tts_config.lang}, Temp: {self.tts_config.temperature}, Reference Voice: {spk_prompt_path})[/]"
        )

        timing_data: List[Dict[str, Any]] = []
        current_timeline_ms = 0
        resumed_count = 0

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total} panels")
        ) as progress:
            task = progress.add_task("[yellow]Synthesizing vocal tracks...", total=len(narration_entries))

            for idx, entry in enumerate(narration_entries, start=1):
                panel_id = entry.get("panel_id") or f"panel_{idx:03d}"
                text = entry.get("text", "").strip()
                emotion = entry.get("emotion", "neutral")
                pause_after_ms = entry.get("pause_after_ms", self.audio_config.pause_between_panels_ms)

                raw_clip_path = audio_dir / f"{panel_id}_raw.wav"
                processed_clip_path = audio_dir / f"{panel_id}.wav"

                # RESUME GUARD: Reuse existing clean WAV if present and non-empty
                if not force and processed_clip_path.exists() and processed_clip_path.stat().st_size > 1000:
                    segment = AudioSegment.from_file(processed_clip_path)
                    duration_ms = len(segment)
                    resumed_count += 1
                else:
                    if text:
                        self._synth.synthesize(
                            text=text,
                            emotion_tag=emotion,
                            spk_prompt_path=spk_prompt_path,
                            output_wav=raw_clip_path,
                        )

                        segment = AudioSegment.from_file(raw_clip_path)
                        segment = segment.set_frame_rate(self.audio_config.sample_rate).set_channels(1)

                        if self.audio_config.edge_fade_ms > 0 and len(segment) > (self.audio_config.edge_fade_ms * 2):
                            segment = segment.fade_in(self.audio_config.edge_fade_ms).fade_out(self.audio_config.edge_fade_ms)

                        segment.export(processed_clip_path, format="wav")

                        if raw_clip_path.exists():
                            raw_clip_path.unlink()

                        duration_ms = len(segment)
                    else:
                        duration_ms = max(pause_after_ms, 500)
                        silence = AudioSegment.silent(duration=duration_ms, frame_rate=self.audio_config.sample_rate)
                        silence.export(processed_clip_path, format="wav")

                start_ms = current_timeline_ms
                end_ms = start_ms + duration_ms
                total_panel_slot_ms = duration_ms + pause_after_ms

                timing_data.append({
                    "index": idx,
                    "panel_id": panel_id,
                    "text": text,
                    "emotion": emotion,
                    "audio_file": processed_clip_path.name,
                    "start_time_ms": start_ms,
                    "end_time_ms": end_ms,
                    "duration_ms": duration_ms,
                    "pause_after_ms": pause_after_ms,
                    "total_slot_ms": total_panel_slot_ms,
                    "start_time_sec": round(start_ms / 1000.0, 3),
                    "end_time_sec": round(end_ms / 1000.0, 3),
                    "total_slot_sec": round(total_panel_slot_ms / 1000.0, 3),
                })

                current_timeline_ms += total_panel_slot_ms
                progress.advance(task)

        timing_manifest_path = chapter_dir / "audio_timing.json"
        write_json(timing_manifest_path, {
            "chapter": str(chapter_num),
            "total_timeline_ms": current_timeline_ms,
            "total_timeline_sec": round(current_timeline_ms / 1000.0, 3),
            "panels": timing_data
        })

        if resumed_count > 0:
            console.print(f"[dim cyan](Resumed {resumed_count} existing audio clips without re-generating)[/]")
        console.print(f"[bold green]✓ Voice audio synthesized and synchronized for {len(narration_entries)} panels![/]")
        return timing_manifest_path
