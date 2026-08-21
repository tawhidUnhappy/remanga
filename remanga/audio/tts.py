from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydub import AudioSegment
from rich.console import Console
from rich.progress import BarColumn, Progress, TextColumn

from remanga import setup
from remanga.config import AudioConfig, RemangaConfig, TTSConfig
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json, write_json
from remanga.models import ModelManager
from remanga.paths import get_chapter_dir

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
            try:
                from indextts.infer_v2 import IndexTTS2  # type: ignore

                console.print("[cyan]Initializing IndexTTS-2 model engine...[/]")
                self._model_instance = IndexTTS2(
                    cfg_path=str(cfg_path.resolve()),
                    model_dir=str(model_dir.resolve()),
                )
                console.print("[bold green]✓ IndexTTS-2 engine loaded successfully![/]")
                return self._model_instance
            except Exception:
                return None
        except Exception as e:
            console.print(f"[yellow]Direct IndexTTS-2.5 import warning: {e}. Falling back to CLI bridge.[/]")
            return None

    def _get_emotion_vector(self, emotion_tag: str) -> List[float]:
        """
        Always returns a flat 8-dimensional zero vector [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0].
        This completely eliminates emotional fluctuations, screams, shock spikes, and vocal strain,
        ensuring uniform, objective, and consistent documentary-style narration across all panels.
        """
        return [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    def _adjust_audio_speed(self, wav_path: Path, speed: float) -> None:
        """Adjusts speaking tempo using pitch-preserving FFmpeg atempo filter."""
        if abs(speed - 1.0) < 0.02 or not wav_path.exists():
            return
        temp_wav = wav_path.with_name(f"{wav_path.stem}_speedtmp.wav")
        wav_path.rename(temp_wav)
        tempo = max(0.5, min(2.0, speed))
        cmd = [
            "ffmpeg", "-y",
            "-i", str(temp_wav),
            "-filter:a", f"atempo={tempo}",
            "-ar", str(self.audio_config.sample_rate),
            str(wav_path)
        ]
        try:
            run_ffmpeg(cmd, check=True)
            if temp_wav.exists():
                temp_wav.unlink()
        except Exception:
            if temp_wav.exists() and not wav_path.exists():
                temp_wav.rename(wav_path)

    def _synthesize_indextts(self, text: str, emotion_tag: str, spk_prompt_path: str, output_wav: Path) -> None:
        """
        Synthesizes speech using IndexTTS-2.5.
        Uses flat zero emotion vector and low temperature/top_p to ensure consistent vocal delivery.
        """
        model = self._get_model()
        emotion_vec = self._get_emotion_vector(emotion_tag)
        target_lang = (self.tts_config.lang or "EN").strip().upper()

        if model is not None:
            sig = inspect.signature(model.infer)
            params = sig.parameters

            call_kwargs: Dict[str, Any] = {
                "spk_audio_prompt": spk_prompt_path,
                "text": text,
                "lang": target_lang,
                "output_path": str(output_wav.resolve()),
            }

            if "emo_vector" in params:
                call_kwargs["emo_vector"] = emotion_vec
            elif "emotion_vector" in params:
                call_kwargs["emotion_vector"] = emotion_vec

            if "duration_factor" in params and abs(self.tts_config.speed - 1.0) >= 0.02:
                call_kwargs["duration_factor"] = round(1.0 / self.tts_config.speed, 3)

            # Pass low temperature and top_p for consistent cadence
            if "temperature" in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
                temp_val = float(self.tts_config.temperature if self.tts_config.temperature is not None else 0.2)
                call_kwargs["temperature"] = temp_val
            if "top_p" in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
                top_p_val = float(self.tts_config.top_p if self.tts_config.top_p is not None else 0.7)
                call_kwargs["top_p"] = top_p_val

            model.infer(**call_kwargs)

            if "duration_factor" not in params and abs(self.tts_config.speed - 1.0) >= 0.02:
                self._adjust_audio_speed(output_wav, self.tts_config.speed)
        else:
            cmd = [
                "python", "-m", "indextts.infer_v2_5",
                "--cfg_path", str(Path(self.tts_config.cfg_path).resolve()),
                "--model_dir", str(Path(self.tts_config.model_dir).resolve()),
                "--spk_audio_prompt", spk_prompt_path,
                "--text", text,
                "--lang", target_lang,
                "--output_path", str(output_wav.resolve()),
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                if abs(self.tts_config.speed - 1.0) >= 0.02:
                    self._adjust_audio_speed(output_wav, self.tts_config.speed)
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