"""VideoRenderer: a chapter's frames composited and encoded into its picture
stream, cached apart from the final MP4, then muxed with the mixed sound.
Which ffmpeg and codec it encodes with is encoder_probe.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from remanga.config import SystemConfig, VideoConfig
from remanga.console import console, escape as _escape_path
from remanga.ffmpeg_io import run_ffmpeg
from remanga.json_io import read_json, read_json_or, write_json
from remanga.paths import (
    get_audio_timing_path,
    get_final_video_path,
    get_master_audio_path,
    get_video_concat_path,
    get_video_frames_dir,
    get_video_picture_path,
    get_video_work_dir,
)
from remanga.video.compose import FrameCache
from remanga.video.encoder_probe import EncoderChoiceMixin
from remanga.video.encoding import (
    AUDIO_CODEC_ARGS,
    MUX_ARGS,
    PICTURE_FORMAT_VERSION,
    picture_codec_args,
    picture_filter_args,
)
from remanga.video.frame_timeline import FrameTimeline, build_frame_timeline
from remanga.video.intro import chosen_intro, intro_identity, join as join_intro, leader as intro_leader


class VideoRenderer(EncoderChoiceMixin):
    def __init__(self, system_config: SystemConfig | None = None, video_config: VideoConfig | None = None):
        self.system_config = system_config or SystemConfig()
        self.video_config = video_config or VideoConfig()
        self.compositor = FrameCache(self.video_config)
        self._encoder_choice: tuple[str, str, bool, str] | None = None

    def frame_timeline(self, project_name: str, chapter_num: str) -> FrameTimeline:
        """This chapter's panels on the configured frame grid (video/frame_timeline.py)."""
        panels = read_json(get_audio_timing_path(project_name, chapter_num)).get("panels", [])
        return build_frame_timeline(panels, self.video_config.fps)

    # --- the picture stream: video only, cached apart from the final MP4 ---

    @staticmethod
    def _picture_fingerprint_path(picture: Path) -> Path:
        return picture.with_name(f"{picture.stem}_fingerprint.json")

    def _picture_fingerprint(self, project_name: str, chapter_num: str, timeline: FrameTimeline) -> dict[str, Any]:
        """Everything that decides what picture.mp4 contains: the timing it
        was laid out from (audio_timing.json is only rewritten when its
        content changes - see audio/tts.py), every video setting, the encoder,
        and the encode recipe itself."""
        return {
            "format": PICTURE_FORMAT_VERSION,
            "timing_mtime": get_audio_timing_path(project_name, chapter_num).stat().st_mtime,
            "codec": self.encoder()[1],
            "total_frames": timeline.total_frames,
            # The intro is joined after the picture, so it never makes one stale.
            "video": self.video_config.model_dump(exclude={"intro_enabled", "intro_path"}),
        }

    def _picture_is_fresh(self, project_name: str, chapter_num: str, timeline: FrameTimeline) -> bool:
        picture = get_video_picture_path(project_name, chapter_num)
        if not picture.exists() or picture.stat().st_size <= 1000:
            return False
        recorded = read_json_or(self._picture_fingerprint_path(picture), None)
        if recorded != self._picture_fingerprint(project_name, chapter_num, timeline):
            return False
        # A frame composited since - deleted and rebuilt - is a different
        # picture even under identical settings.
        built = picture.stat().st_mtime
        frames = get_video_frames_dir(project_name, chapter_num).glob("frame_*.png")
        return not any(frame.stat().st_mtime > built for frame in frames)

    def ensure_picture(self, project_name: str, chapter_num: str, force: bool = False) -> tuple[Path, FrameTimeline]:
        """This chapter's encoded picture stream, encoded only if it's missing
        or stale, so a change to the sound alone never re-encodes a frame."""
        timeline = self.frame_timeline(project_name, chapter_num)
        if force or not self._picture_is_fresh(project_name, chapter_num, timeline):
            self._encode_picture(project_name, chapter_num, timeline, force=force)
        return get_video_picture_path(project_name, chapter_num), timeline

    def _encode_picture(
        self, project_name: str, chapter_num: str, timeline: FrameTimeline, *,
        force: bool = False, sound: tuple[Path, Path] | None = None,
    ) -> None:
        """Composites any missing frames and encodes picture.mp4 from them.

        `sound`, as (mixed WAV, AAC to write), encodes the chapter's audio in
        the same ffmpeg run. ffmpeg gives each encoder a thread of its own, so
        a fresh render waits for the slower of the two, not both in turn."""
        if not timeline.total_frames:
            raise RuntimeError(f"audio_timing.json for chapter {chapter_num} lists no panels - nothing to render.")

        # 1. Composite frames to canvas
        self.compositor.prepare_composited_frames(project_name, chapter_num,
                                                  [slot.panel_id for slot in timeline.slots], force=force)

        # 2. Concat script: one entry per page, snapped to the frame grid
        concat_file = get_video_concat_path(project_name, chapter_num)
        timeline.write_concat_list(concat_file, get_video_frames_dir(project_name, chapter_num))

        # 3. Encoder (GPU NVENC vs CPU libx264) and the ffmpeg binary that has
        # a working GPU encoder on this machine right now (see
        # encoder_probe.py - not necessarily the bundled one).
        ffmpeg_bin, codec, use_gpu, note = self.encoder()
        console.print(
            f"[cyan]Rendering video using codec:[/] [bold]{codec}[/] "
            f"[dim]({'Hardware GPU' if use_gpu else 'CPU fallback'}, "
            f"{timeline.total_frames} frames at {timeline.fps}fps)[/]"
        )
        if note:
            console.print(f"[dim]({note})[/]")

        # 4. Encode. Written beside the target and renamed into place, so a
        # killed run never leaves a truncated picture that looks finished.
        picture = get_video_picture_path(project_name, chapter_num)
        partial = picture.with_name(f"{picture.stem}.part.mp4")
        cmd = [ffmpeg_bin, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file)]
        if sound:
            cmd += ["-i", str(sound[0])]
        cmd += ["-map", "0:v:0", *picture_filter_args(timeline),
                *picture_codec_args(codec, use_gpu, self.system_config.threads), str(partial)]
        if sound:
            cmd += ["-map", "1:a:0", *AUDIO_CODEC_ARGS, str(sound[1])]

        # The picture's length is known exactly - it's the timeline it was
        # laid out from - so the bar shows a real percentage.
        result = run_ffmpeg(cmd, capture=True, show_progress=True, total_seconds=timeline.duration_sec,
                            description=f"Encoding {self.video_config.height}p video")
        if result.returncode != 0:
            partial.unlink(missing_ok=True)
            console.print(f"[red]FFmpeg Error Details:\n{_escape_path(result.stderr)}[/]")
            raise RuntimeError("FFmpeg rendering failed.")
        partial.replace(picture)
        # Last: a picture with no fingerprint beside it (a run killed right
        # here) reads as stale and is simply encoded again.
        write_json(self._picture_fingerprint_path(picture),
                   self._picture_fingerprint(project_name, chapter_num, timeline))

    def render_video(self, project_name: str, chapter_num: str, force: bool = False) -> Path:
        """
        Composites frames, synchronizes with master audio,
        and renders final MP4 with GPU acceleration (or fallback CPU encoder).

        The picture (ensure_picture) and the sound are encoded apart and
        stream-copied together at the end, so when only the mix changed the
        cached picture is reused and the render is one audio encode.
        """
        master_audio = get_master_audio_path(project_name, chapter_num)
        # Final MP4 lives at {manga}/video/chapter_N/ - see remanga.paths.
        final_video = get_final_video_path(project_name, chapter_num)

        # Rebuild if missing/forced, OR if master_audio.wav is newer than the
        # last render - the case that matters most: the user only changed
        # BGM/volume and re-ran `mix`, so the video needs a fresh encode of
        # its sound even though nobody passed --force. TTS, frame compositing
        # and the picture encode are untouched either way - see
        # _picture_is_fresh below.
        stale_audio = (
            final_video.exists() and master_audio.exists()
            and master_audio.stat().st_mtime > final_video.stat().st_mtime
        )
        # The same for the picture: a changed video setting (size, background,
        # fps) changes the picture's fingerprint, and the finished MP4 must not
        # be accepted just because it exists - that is what left a re-render
        # after changing the video size doing nothing at all.
        timeline = self.frame_timeline(project_name, chapter_num)
        stale_picture = not self._picture_is_fresh(project_name, chapter_num, timeline)
        # The intro in front (video/intro.py): switching it, or turning it
        # off, re-joins - a stream copy, not a re-encode.
        intro_stamp = get_video_work_dir(project_name, chapter_num) / "final_intro.json"
        wanted_intro = intro_identity(self.video_config)
        stale_intro = final_video.exists() and read_json_or(intro_stamp, {}).get("intro") != wanted_intro
        if (not force and final_video.exists() and final_video.stat().st_size > 1000
                and not stale_audio and not stale_picture and not stale_intro):
            console.print(f"[bold green]✓ Recap video already rendered:[/] {_escape_path(str(final_video))}")
            return final_video
        if stale_audio:
            console.print(
                "[dim]master_audio.wav is newer than the last render (BGM/volume likely changed) - rebuilding the "
                "video around it.[/]"
            )

        if stale_intro and not stale_audio and not stale_picture:
            console.print("[dim]the intro setting changed since the last render - joining it again.[/]")
        if stale_picture and final_video.exists() and not force:
            console.print("[dim]the video settings changed since the last render - building the picture again.[/]")

        if not master_audio.exists():
            raise FileNotFoundError(f"Master audio not found: {master_audio}")

        picture = get_video_picture_path(project_name, chapter_num)
        work_dir = get_video_work_dir(project_name, chapter_num)
        partial = work_dir / f"{final_video.stem}.part.mp4"

        if not force and self._picture_is_fresh(project_name, chapter_num, timeline):
            console.print("[dim](picture unchanged since the last render - reusing it, encoding only the sound)[/]")
            cmd = [
                "ffmpeg", "-y", "-i", str(picture), "-i", str(master_audio),
                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", *AUDIO_CODEC_ARGS, *MUX_ARGS, str(partial),
            ]
            result = run_ffmpeg(cmd, capture=True, show_progress=True, total_seconds=timeline.duration_sec,
                                description="Encoding audio")
        else:
            sound = work_dir / "sound.part.m4a"
            try:
                self._encode_picture(project_name, chapter_num, timeline, force=force, sound=(master_audio, sound))
                cmd = [
                    "ffmpeg", "-y", "-i", str(picture), "-i", str(sound),
                    "-map", "0:v:0", "-map", "1:a:0", "-c", "copy", *MUX_ARGS, str(partial),
                ]
                result = run_ffmpeg(cmd, capture=True)
            finally:
                sound.unlink(missing_ok=True)

        if result.returncode != 0:
            partial.unlink(missing_ok=True)
            console.print(f"[red]FFmpeg Error Details:\n{_escape_path(result.stderr)}[/]")
            raise RuntimeError("FFmpeg rendering failed.")
        intro = chosen_intro(self.video_config)
        if intro is not None:
            joined = work_dir / f"{final_video.stem}.joined.part.mp4"
            join_intro(self, intro_leader(self, intro, partial, work_dir), partial, joined)
            partial.unlink(missing_ok=True)
            joined.replace(final_video)
            console.print(f"[cyan]Intro added:[/] {_escape_path(intro.name)}")
        else:
            partial.replace(final_video)
        write_json(intro_stamp, {"intro": wanted_intro})

        console.print("[bold green]✓ Recap video generated successfully![/]")
        console.print(f"[bold green]Location:[/] {_escape_path(str(final_video))}")
        return final_video
