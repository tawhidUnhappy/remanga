"""Low-level IndexTTS-2.5 speech synthesis: model loading, single-utterance inference, and tempo adjustment."""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path
from typing import Any, Dict, List
from pydub import AudioSegment
from rich.console import Console

from remanga.config import AudioConfig, TTSConfig
from remanga.ffmpeg_io import run_ffmpeg
from remanga.models import ModelManager

console = Console()


class IndexTTSSynthesizer:
    """Loads the IndexTTS-2.5 model once and synthesizes individual narration clips with it."""

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.audio_config = audio_config
        self._model_instance = None
        self.model_manager = ModelManager(tts_config.model_dir, tts_config.hf_repo_id)

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

    def synthesize(self, text: str, emotion_tag: str, spk_prompt_path: str, output_wav: Path) -> None:
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
