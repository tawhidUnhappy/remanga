from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import edge_tts
from pydub import AudioSegment
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn

from remanga.config import AudioConfig, TTSConfig, get_chapter_dir

console = Console()


class TTSEngine:
    def __init__(self, tts_config: Optional[TTSConfig] = None, audio_config: Optional[AudioConfig] = None):
        self.tts_config = tts_config or TTSConfig()
        self.audio_config = audio_config or AudioConfig()

    async def _synthesize_text_edge(self, text: str, output_file: Path) -> None:
        """Asynchronously call edge-tts to generate voice audio."""
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.tts_config.voice,
            rate=self.tts_config.rate,
            pitch=self.tts_config.pitch,
            volume=self.tts_config.volume,
        )
        await communicate.save(str(output_file))

    def generate_narration_audio(self, project_name: str, chapter_num: str) -> Path:
        """
        Reads `narration.json`, generates individual audio speech clips for each panel,
        and saves timing metadata into `audio_timing.json`.
        """
        chapter_dir = get_chapter_dir(project_name, chapter_num)
        narration_path = chapter_dir / "narration.json"
        audio_dir = chapter_dir / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        if not narration_path.exists():
            raise FileNotFoundError(
                f"Missing narration script: {narration_path}\n"
                f"Please provide your narration JSON file before generating speech."
            )

        with open(narration_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        narration_entries = data.get("narration", [])
        if not narration_entries:
            raise ValueError(f"No narration entries found in {narration_path}")

        console.print(f"[cyan]Generating TTS audio using voice:[/] [bold]{self.tts_config.voice}[/]")

        timing_data: List[Dict[str, Any]] = []
        current_timeline_ms = 0

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total} panels")
        ) as progress:
            task = progress.add_task("[yellow]Synthesizing narration...", total=len(narration_entries))

            for idx, entry in enumerate(narration_entries, start=1):
                panel_id = entry.get("panel_id") or f"panel_{idx:03d}"
                text = entry.get("text", "").strip()
                pause_after_ms = entry.get("pause_after_ms", self.audio_config.pause_between_panels_ms)
                
                raw_clip_path = audio_dir / f"{panel_id}_raw.mp3"
                processed_clip_path = audio_dir / f"{panel_id}.wav"

                if text:
                    # Synthesize speech
                    asyncio.run(self._synthesize_text_edge(text, raw_clip_path))
                    segment = AudioSegment.from_file(raw_clip_path)
                    
                    # Convert to target sample rate and mono for consistent mixing
                    segment = segment.set_frame_rate(self.audio_config.sample_rate).set_channels(1)
                    
                    # Apply micro edge-fades to eliminate digital clicks
                    if self.audio_config.edge_fade_ms > 0 and len(segment) > (self.audio_config.edge_fade_ms * 2):
                        segment = segment.fade_in(self.audio_config.edge_fade_ms).fade_out(self.audio_config.edge_fade_ms)
                    
                    segment.export(processed_clip_path, format="wav")
                    
                    if raw_clip_path.exists():
                        raw_clip_path.unlink()
                        
                    duration_ms = len(segment)
                else:
                    # Silent pause panel
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
                    "emotion": entry.get("emotion", "neutral"),
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

        # Save timing manifest
        timing_manifest_path = chapter_dir / "audio_timing.json"
        with open(timing_manifest_path, "w", encoding="utf-8") as f:
            json.dump({
                "chapter": str(chapter_num),
                "total_timeline_ms": current_timeline_ms,
                "total_timeline_sec": round(current_timeline_ms / 1000.0, 3),
                "panels": timing_data
            }, f, indent=2)

        console.print(f"[bold green]✓ Synthesized audio for {len(narration_entries)} panels![/]")
        return timing_manifest_path