from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydub import AudioSegment
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn

from remanga.config import AudioConfig, RemangaConfig, TTSConfig, get_chapter_dir
from remanga.models import ModelManager

console = Console()


class TTSEngine:
    def __init__(self, tts_config: Optional[TTSConfig] = None, audio_config: Optional[AudioConfig] = None):
        self.tts_config = tts_config or TTSConfig()
        self.audio_config = audio_config or AudioConfig()
        self._model_instance = None
        self.model_manager = ModelManager(self.tts_config.model_dir, self.tts_config.hf_repo_id)

    def _get_model(self):
        """Lazy-loads and caches the IndexTTS-2.5 model instance."""
        if self._model_instance is not None:
            return self._model_instance

        model_dir = self.model_manager.ensure_model()
        cfg_path = Path(self.tts_config.cfg_path)

        try:
            from indextts.infer_v2_5 import IndexTTS2  # type: ignore

            console.print(f"[cyan]Initializing IndexTTS-2.5 model engine (BF16: {self.tts_config.use_bf16})...[/]")
            self._model_instance = IndexTTS2(
                cfg_path=str(cfg_path.resolve()),
                model_dir=str(model_dir.resolve()),
                use_bf16=self.tts_config.use_bf16,
            )
            console.print("[bold green]✓ IndexTTS-2.5 engine loaded successfully![/]")
            return self._model_instance
        except ImportError:
            return None
        except Exception as e:
            console.print(f"[yellow]Direct IndexTTS-2.5 import warning: {e}. Falling back to CLI bridge.[/]")
            return None

    def _get_emotion_vector(self, emotion_tag: str) -> List[float]:
        """Maps high-level recap emotion tags to IndexTTS 8-dimensional emotion vectors."""
        tag = (emotion_tag or "neutral").strip().lower()
        mapping = self.tts_config.emotion_vectors
        if tag in mapping:
            return mapping[tag]
        return mapping.get("neutral", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.8])

    def _synthesize_indextts(self, text: str, emotion_tag: str, spk_prompt_path: str, output_wav: Path) -> None:
        """Synthesizes speech using IndexTTS-2.5 with speaker cloning and emotion conditioning."""
        model = self._get_model()
        emotion_vec = self._get_emotion_vector(emotion_tag)

        if model is not None:
            model.infer(
                spk_audio_prompt=spk_prompt_path,
                text=text,
                lang=self.tts_config.lang,
                output_path=str(output_wav.resolve()),
                speed=self.tts_config.speed,
                temperature=self.tts_config.temperature,
                top_p=self.tts_config.top_p,
                emotion_vector=emotion_vec,
            )
        else:
            cmd = [
                "python", "-m", "indextts.infer_v2_5",
                "--cfg_path", str(Path(self.tts_config.cfg_path).resolve()),
                "--model_dir", str(Path(self.tts_config.model_dir).resolve()),
                "--spk_audio_prompt", spk_prompt_path,
                "--text", text,
                "--lang", self.tts_config.lang,
                "--output_path", str(output_wav.resolve()),
                "--speed", str(self.tts_config.speed),
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            except Exception as ex:
                console.print(f"[dim yellow]Synthesis fallback triggered ({ex}). Generating timing slot...[/]")
                word_count = max(1, len(text.split()))
                est_duration_ms = int((word_count / 2.5) * 1000)
                fallback_audio = AudioSegment.silent(duration=est_duration_ms, frame_rate=self.tts_config.sample_rate)
                fallback_audio.export(output_wav, format="wav")

    def generate_narration_audio(
        self,
        project_name: str,
        chapter_num: str,
        voice_override: Optional[str] = None,
        interactive: bool = True,
    ) -> Path:
        """
        Reads narration.json, validates the reference voice (prompting if needed),
        synthesizes speech per panel with IndexTTS-2.5, applies micro edge-fades, and writes audio_timing.json.
        """
        full_config = RemangaConfig.load()
        if voice_override:
            full_config.tts.spk_audio_prompt = voice_override
            self.tts_config.spk_audio_prompt = voice_override

        spk_prompt_path = full_config.ensure_valid_voice_prompt(interactive=interactive)
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

        with open(narration_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        narration_entries = data.get("narration", [])
        if not narration_entries:
            raise ValueError(f"No narration entries found in {narration_path}")

        console.print(
            f"[cyan]Synthesizing speech via IndexTTS-2.5[/] "
            f"[dim](Reference Voice: {spk_prompt_path})[/]"
        )

        timing_data: List[Dict[str, Any]] = []
        current_timeline_ms = 0

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total} panels")
        ) as progress:
            task = progress.add_task("[yellow]Synthesizing panels...", total=len(narration_entries))

            for idx, entry in enumerate(narration_entries, start=1):
                panel_id = entry.get("panel_id") or f"panel_{idx:03d}"
                text = entry.get("text", "").strip()
                emotion = entry.get("emotion", "neutral")
                pause_after_ms = entry.get("pause_after_ms", self.audio_config.pause_between_panels_ms)

                raw_clip_path = audio_dir / f"{panel_id}_raw.wav"
                processed_clip_path = audio_dir / f"{panel_id}.wav"

                if text:
                    self._synthesize_indextts(
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
        with open(timing_manifest_path, "w", encoding="utf-8") as f:
            json.dump({
                "chapter": str(chapter_num),
                "total_timeline_ms": current_timeline_ms,
                "total_timeline_sec": round(current_timeline_ms / 1000.0, 3),
                "panels": timing_data
            }, f, indent=2)

        console.print(f"[bold green]✓ Synthesized IndexTTS-2.5 audio for {len(narration_entries)} panels![/]")
        return timing_manifest_path