from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
from pydub import AudioSegment

from remanga import settings
from remanga.config import AudioConfig, RemangaConfig
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json, read_json_or, write_json
from remanga.paths import get_audio_dir, get_audio_timing_path, get_master_audio_path


class AudioProcessor:
    def __init__(self, config: Optional[AudioConfig] = None):
        self.config = config or AudioConfig()

    @staticmethod
    def _fingerprint(timing_path: Path, config: AudioConfig) -> Dict[str, Any]:
        """Everything that determines mix_master_audio's output for a given
        audio_timing.json: the timing file's own mtime (a reliable "did the
        synthesized audio change" signal now that tts.py only rewrites it
        when its content actually changes) plus every mix-affecting config
        field. Two calls with an identical fingerprint are guaranteed to
        produce the same master_audio.wav."""
        return {
            "timing_mtime": timing_path.stat().st_mtime,
            "bgm_enabled": config.bgm_enabled,
            "bgm_path": config.bgm_path,
            "bgm_volume_db": config.bgm_volume_db,
            "sample_rate": config.sample_rate,
            "enable_loudnorm": config.enable_loudnorm,
        }

    def mix_master_audio(
        self,
        project_name: str,
        chapter_num: str,
        bgm_override: Optional[str] = None,
        interactive: bool = True,
        force: bool = False,
    ) -> Path:
        """
        Combines narration segments, adds inter-panel pauses, overlays background music (if enabled),
        and applies EBU R128 loudness normalization.

        Skips the whole rebuild (force=False, the default) if master_audio.wav
        already exists and nothing that would change its output has changed
        since: the synthesized audio timeline (audio_timing.json - see
        tts.py, which itself only rewrites that file when its content
        actually changes) and the BGM/loudnorm settings this call would use.
        Without this, every call would unconditionally rebuild and touch
        master_audio.wav's mtime - which video/render.py treats as "the mix
        changed, re-encode the video" - so a plain resume (nothing actually
        changed) would silently re-mix and re-render every chapter it
        touches, every single time, for no reason.
        """
        # Scoped to the project: the validator below reads the BGM out of this
        # config, and it has to be the one this manga uses.
        full_config = RemangaConfig.load().for_project(project_name)
        if bgm_override:
            full_config.audio.bgm_path = bgm_override
            full_config.audio.bgm_enabled = True
            self.config.bgm_path = bgm_override
            self.config.bgm_enabled = True

        valid_bgm = settings.ensure_valid_bgm(full_config, interactive=interactive)
        if valid_bgm:
            self.config.bgm_path = valid_bgm
            self.config.bgm_enabled = True

        timing_path = get_audio_timing_path(project_name, chapter_num)
        audio_dir = get_audio_dir(project_name, chapter_num)
        master_final_path = get_master_audio_path(project_name, chapter_num)
        master_raw_path = master_final_path.with_name("master_audio_raw.wav")
        fingerprint_path = master_final_path.with_name("master_audio_fingerprint.json")

        if not timing_path.exists():
            raise FileNotFoundError(f"Missing audio timing metadata at: {timing_path}")

        timing_info = read_json(timing_path)

        fingerprint = self._fingerprint(timing_path, self.config)
        if not force and master_final_path.exists() and master_final_path.stat().st_size > 1000:
            if read_json_or(fingerprint_path, None) == fingerprint:
                console.print(f"[dim]✓ master_audio.wav for chapter {chapter_num} is already up to date - skipping remix.[/]")
                return master_final_path

        panels = timing_info.get("panels", [])
        console.print(f"[cyan]Assembling master audio stream for chapter {chapter_num}...[/]")

        # 1. Assemble narration track
        combined_voice = AudioSegment.empty()
        for p in panels:
            clip_file = audio_dir / p["audio_file"]
            if clip_file.exists():
                segment = AudioSegment.from_file(clip_file)
            else:
                segment = AudioSegment.silent(duration=p["duration_ms"], frame_rate=self.config.sample_rate)

            combined_voice += segment

            # Append inter-panel silence pause
            pause_ms = p.get("pause_after_ms", 0)
            if pause_ms > 0:
                combined_voice += AudioSegment.silent(duration=pause_ms, frame_rate=self.config.sample_rate)

        # Convert to 2-channel stereo for master output
        master_audio = combined_voice.set_channels(2).set_frame_rate(self.config.sample_rate)

        # 2. Mix Background Music (BGM) if enabled
        if self.config.bgm_enabled and self.config.bgm_path and Path(self.config.bgm_path).exists():
            console.print(f"[cyan]Overlaying background music:[/] {_esc(str(self.config.bgm_path))}")
            bgm_track = AudioSegment.from_file(self.config.bgm_path)
            bgm_track = bgm_track.set_channels(2).set_frame_rate(self.config.sample_rate)
            bgm_track = bgm_track + self.config.bgm_volume_db  # Adjust volume gain

            # Loop BGM to match voice track length + tail
            total_duration_ms = len(master_audio)
            loop_count = (total_duration_ms // max(1, len(bgm_track))) + 1
            bgm_loop = (bgm_track * loop_count)[:total_duration_ms]

            # Smooth BGM entry & exit fades
            bgm_loop = bgm_loop.fade_in(1500).fade_out(2000)

            # Overlay voice over BGM
            master_audio = bgm_loop.overlay(master_audio)
        elif self.config.bgm_enabled:
            console.print(f"[yellow]BGM is enabled in config, but file was not found at: {_esc(str(self.config.bgm_path))}. Continuing without BGM.[/]")

        # 3. Export Raw Master Track
        master_audio.export(master_raw_path, format="wav")

        # 4. Loudness Normalization via FFmpeg (EBU R128)
        if self.config.enable_loudnorm:
            console.print("[cyan]Applying EBU R128 audio normalization...[/]")
            cmd = [
                "ffmpeg", "-y",
                "-i", str(master_raw_path),
                "-af", "loudnorm=I=-16:LRA=11:TP=-1.5",
                "-ar", str(self.config.sample_rate),
                str(master_final_path)
            ]
            try:
                run_ffmpeg(cmd, check=True, capture=True)
                if master_raw_path.exists():
                    master_raw_path.unlink()
            except Exception as e:
                console.print(f"[yellow]Loudnorm filter warning: {_esc(str(e))}. Falling back to standard raw master audio.[/]")
                master_raw_path.rename(master_final_path)
        else:
            master_raw_path.rename(master_final_path)

        # Recomputed rather than reusing the pre-mix `fingerprint` above:
        # timing_path's mtime could theoretically be touched again by a
        # concurrent process during a long mix - cheap to just re-read it
        # fresh right before recording what actually went into this file.
        write_json(fingerprint_path, self._fingerprint(timing_path, self.config))

        console.print(f"[bold green]✓ Master audio track generated successfully:[/] {_esc(str(master_final_path))}")
        return master_final_path