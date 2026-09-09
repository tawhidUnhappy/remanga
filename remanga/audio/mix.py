from __future__ import annotations

from pathlib import Path
from typing import Any

from pydub import AudioSegment

from remanga import settings
from remanga.audio.ducking import carve_speech_band, duck_under_speech, merge_spans
from remanga.audio.resample import load_audio
from remanga.audio.voice import enhance_voice
from remanga.config import AudioConfig, RemangaConfig
from remanga.console import console, escape as _esc
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json, read_json_or, write_json
from remanga.paths import get_audio_dir, get_audio_timing_path, get_master_audio_path


class AudioProcessor:
    def __init__(self, config: AudioConfig | None = None):
        self.config = config or AudioConfig()

    @staticmethod
    def _fingerprint(timing_path: Path, config: AudioConfig) -> dict[str, Any]:
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
        bgm_override: str | None = None,
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
        if (not force and master_final_path.exists() and master_final_path.stat().st_size > 1000
                and read_json_or(fingerprint_path, None) == fingerprint):
            console.print(
                f"[dim]✓ master_audio.wav for chapter {chapter_num} is already up to date - skipping remix.[/]"
            )
            return master_final_path

        panels = timing_info.get("panels", [])
        console.print(f"[cyan]Assembling master audio stream for chapter {chapter_num}...[/]")

        # 1. Assemble narration track
        #
        # speech_spans records where each panel's audio actually sits on the
        # finished timeline, so the ducking pass below works from exact
        # boundaries instead of inferring them from the signal. Collected
        # here because this loop is the only place that knows them.
        if self.config.voice_enhance:
            console.print(
                f"[dim]Voice chain per panel: high-pass {self.config.voice_highpass_hz}Hz, "
                f"warmth {self.config.voice_warmth_db:+.1f}dB, "
                f"presence {self.config.voice_presence_db:+.1f}dB"
                + (f", compressed {self.config.voice_compress_ratio:g}:1"
                   if self.config.voice_compress else "") + ".[/]"
            )
        combined_voice = AudioSegment.empty()
        speech_spans: list[tuple[int, int]] = []
        for p in panels:
            clip_file = audio_dir / p["audio_file"]
            if clip_file.exists():
                segment = AudioSegment.from_file(clip_file)
                if self.config.voice_enhance:
                    segment = enhance_voice(
                        segment,
                        highpass_hz=self.config.voice_highpass_hz,
                        warmth_db=self.config.voice_warmth_db,
                        presence_db=self.config.voice_presence_db,
                        compress=self.config.voice_compress,
                        compress_threshold_db=self.config.voice_compress_threshold_db,
                        compress_ratio=self.config.voice_compress_ratio,
                    )
            else:
                segment = AudioSegment.silent(duration=p["duration_ms"], frame_rate=self.config.sample_rate)

            span_start = len(combined_voice)
            combined_voice += segment
            if clip_file.exists() and len(segment) > 0:
                speech_spans.append((span_start, span_start + len(segment)))

            # Append inter-panel silence pause
            pause_ms = p.get("pause_after_ms", 0)
            if pause_ms > 0:
                combined_voice += AudioSegment.silent(duration=pause_ms, frame_rate=self.config.sample_rate)

        # Convert to 2-channel stereo for master output
        master_audio = combined_voice.set_channels(2).set_frame_rate(self.config.sample_rate)

        # 2. Mix Background Music (BGM) if enabled
        if self.config.bgm_enabled and self.config.bgm_path and Path(self.config.bgm_path).exists():
            console.print(f"[cyan]Overlaying background music:[/] {_esc(str(self.config.bgm_path))}")
            # Through resample.load_audio for the same reason the narration
            # clips are (see audio/resample.py): BGM is rarely already at the
            # project rate - the bundled track is 48 kHz against a 44.1 kHz
            # project - and pydub's resampler would fold imaging noise across
            # the whole music bed on the way down.
            bgm_track = load_audio(Path(self.config.bgm_path), self.config.sample_rate, channels=2)
            bgm_track = bgm_track + self.config.bgm_volume_db  # Adjust volume gain

            # Loop BGM to match voice track length + tail
            total_duration_ms = len(master_audio)
            # Carve the SOURCE track, before it is looped out to the length of
            # the narration. The carve is a time-invariant filter, so carving
            # then looping is the same audio as looping then carving - but the
            # source is a few minutes and the loop is the whole recap. Doing it
            # the other way round is what put a 56-minute full-manga bed through
            # a three-copy band reconstruction and invoked the OOM killer
            # (measured: anon-rss 13.5GB on a 14GB machine).
            #
            # The level duck below CANNOT move here: it depends on where the
            # speech falls, so it has to see the full timeline.
            if self.config.duck_music_under_narration:
                bgm_track = carve_speech_band(bgm_track, self.config.duck_carve_db)
            loop_count = (total_duration_ms // max(1, len(bgm_track))) + 1
            bgm_loop = (bgm_track * loop_count)[:total_duration_ms]

            # Duck the music under each speech passage, if asked. Before the
            # entry/exit fades, so those still shape the very start and end of
            # the track rather than fighting a dip that lands on top of them.
            if self.config.duck_music_under_narration and speech_spans:
                passages = merge_spans(speech_spans)
                bgm_loop = duck_under_speech(
                    bgm_loop, speech_spans,
                    depth_db=self.config.duck_depth_db, fade_ms=self.config.duck_fade_ms,
                )
                console.print(
                    f"[dim]Ducking music {self.config.duck_depth_db:+.1f}dB under "
                    f"{len(passages)} speech passage(s).[/]"
                )

            # Smooth BGM entry & exit fades
            bgm_loop = bgm_loop.fade_in(1500).fade_out(2000)

            # Overlay voice over BGM
            master_audio = bgm_loop.overlay(master_audio)
        elif self.config.bgm_enabled:
            console.print(
                f"[yellow]BGM is enabled in config, but file was not found at: {_esc(str(self.config.bgm_path))}. "
                f"Continuing without BGM.[/]"
            )

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
                console.print(
                    f"[yellow]Loudnorm filter warning: {_esc(str(e))}. Falling back to standard raw master audio.[/]"
                )
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
