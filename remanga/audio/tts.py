from __future__ import annotations

from pathlib import Path
from typing import Any

from pydub import AudioSegment
from rich.progress import BarColumn, Progress, TextColumn

from remanga import settings
from remanga.audio.clips import apply_edge_fades, apply_gain, atomic_export, clamp_boost, is_audible_gain
from remanga.audio.resample import load_audio
from remanga.audio.synth import create_synthesizer
from remanga.config import AudioConfig, RemangaConfig, TTSConfig
from remanga.console import console
from remanga.json_io import read_json, read_json_or, write_json
from remanga.paths import get_audio_dir, get_audio_timing_path, get_chapter_dir
from remanga.settings.fields import set_field
from remanga.verify import ensure_panels_match_narration


class TTSEngine:
    def __init__(self, tts_config: TTSConfig | None = None, audio_config: AudioConfig | None = None):
        self.tts_config = tts_config or TTSConfig()
        self.audio_config = audio_config or AudioConfig()
        self._synth = create_synthesizer(self.tts_config, self.audio_config)

    def generate_narration_audio(
        self,
        project_name: str,
        chapter_num: str,
        voice_override: str | None = None,
        interactive: bool = True,
        force: bool = False,
    ) -> Path:
        """
        Synthesizes narration audio per panel with Kokoro-82M.
        Resumes automatically by checking existing panel WAV clips.
        """
        # Refuse to produce output that would be silently degraded - see
        # verify/gate.py. Here rather than in pipeline.py so full-recap,
        # which does not go through the wizard's steps, is covered too.
        ensure_panels_match_narration(project_name, chapter_num, stage="text-to-speech")

        # Scoped to the project: the validator below reads the voice out of this
        # config, and it has to be the one this manga uses.
        full_config = RemangaConfig.load().for_project(project_name)
        # Per-ENGINE (see config/tts.py): a --voice one-off means "narrate in
        # this voice on the engine actually running", and the validator is
        # told which engine that is, since self.tts_config may be a one-off
        # `--engine` copy naming a different one than config.json does.
        # Writing through engine_block rather than a fixed field is what
        # keeps the override on the right engine's block.
        if voice_override:
            self.tts_config.engine_block.voice = voice_override
            set_field(full_config, self.tts_config.active_voice_field, voice_override, save=False)

        voice = settings.ensure_valid_voice(
            full_config, interactive=interactive, engine=self.tts_config.engine,
        )
        self.tts_config.engine_block.voice = voice

        chapter_dir = get_chapter_dir(project_name, chapter_num)
        narration_path = chapter_dir / "narration.json"
        audio_dir = get_audio_dir(project_name, chapter_num)

        # Debris from an atomic_export() that was itself interrupted before its
        # rename-into-place (a kill exactly mid-write) - harmless leftovers, never
        # mistaken for a finished clip since is_cached_complete() only looks at the
        # real ".wav" path, but worth sweeping so they don't just accumulate.
        for stray_tmp in audio_dir.glob("*.wav.tmp"):
            stray_tmp.unlink(missing_ok=True)

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
            f"[cyan]Synthesizing consistent speech via {self._synth.display_name}[/] "
            f"[dim](Lang: {self.tts_config.lang}, "
            f"Voice: {self.tts_config.kokoro.spec.label} [{voice}], "
            f"Speed: {self.tts_config.speed}x)[/]"
        )

        # This engine's own gain (see config/tts.py), and how much of it the
        # clips on disk are still missing. audio_timing.json records what was
        # baked in last time, so raising the boost from +3 to +6 costs one
        # +3 dB pass over the cached clips rather than a whole re-synthesis -
        # a volume knob nobody can afford to turn is not a volume knob.
        timing_manifest_path = get_audio_timing_path(project_name, chapter_num)
        boost_db = clamp_boost(getattr(self.tts_config.engine_block, "volume_boost_db", 0.0))
        previous_boost_db = clamp_boost(
            read_json_or(timing_manifest_path, {}).get("volume_boost_db", 0.0)
        )
        boost_delta_db = boost_db - previous_boost_db
        if boost_db:
            console.print(
                f"[dim]Volume boost for {self._synth.display_name}: {boost_db:+.1f} dB"
                + (f" (cached clips get the {boost_delta_db:+.1f} dB difference)"
                   if is_audible_gain(boost_delta_db) and not force else "")
                + "[/]"
            )
            # The one combination where this knob is a no-op, said out loud
            # rather than left to be discovered by listening to an unchanged
            # video: loudnorm normalizes the finished master to a fixed
            # loudness, so with nothing else in the mix to be balanced
            # against, boosting the narration and then normalizing it lands
            # back exactly where it started. With BGM on it still does the
            # useful thing - the music ends up further under the voice.
            if self.audio_config.enable_loudnorm and not self.audio_config.bgm_enabled:
                console.print(
                    "[yellow]Heads up: audio.enable_loudnorm is on and there's no BGM, so this "
                    "boost won't change the finished audio at all[/] [dim]- the mix normalizes "
                    "the master back to its target loudness. The boost is real in the clips "
                    "themselves; it only shows up in the video once there's music to sit over, "
                    "or with audio.enable_loudnorm off.[/]"
                )
        clipped_panels: list[str] = []

        def apply_boost(segment: AudioSegment, gain_db: float, panel_id: str) -> AudioSegment:
            """clips.apply_gain, plus a note of which panel it was - the
            report at the end names the panels, so the "did this clip"
            answer has to be tied back to a panel id here rather than
            inside the gain helper itself."""
            boosted, clipped = apply_gain(segment, gain_db)
            if clipped:
                clipped_panels.append(panel_id)
            return boosted

        def is_cached_complete(panel_id: str) -> bool:
            clip = audio_dir / f"{panel_id}.wav"
            return clip.exists() and clip.stat().st_size > 1000

        panel_ids = [entry.get("panel_id") or f"panel_{i:03d}" for i, entry in enumerate(narration_entries, start=1)]

        # Where the previous run actually left off: the first panel, in sequence,
        # with no complete cached clip. Exports are atomic now (see atomic_export
        # below) so a kill mid-write can no longer leave a truncated file sitting
        # at the final path looking "done" - but a clip written by an *older* run,
        # from before that fix, still could be. Rather than trust the last couple
        # of clips right at the resume point, force them (and the actual resume
        # point itself) to regenerate - the two panels either side of a Ctrl+C are
        # exactly the ones a corrupt-but-present WAV would hide in.
        force_regen_ids: set = set()
        if not force:
            resume_at = next((i for i, pid in enumerate(panel_ids) if not is_cached_complete(pid)), len(panel_ids))
            if 0 < resume_at < len(panel_ids):
                force_regen_ids = set(panel_ids[max(0, resume_at - 2):resume_at + 1])
                console.print(
                    f"[dim cyan](Resuming - re-generating the {len(force_regen_ids)} panel(s) around the previous "
                    f"run's stopping point instead of trusting them, in case that run was interrupted mid-write: "
                    f"{', '.join(sorted(force_regen_ids))})[/]"
                )

        def is_resumable(panel_id: str) -> bool:
            """True if a clean WAV from a previous run can be reused for this panel."""
            return not force and panel_id not in force_regen_ids and is_cached_complete(panel_id)

        timing_data: list[dict[str, Any]] = []
        current_timeline_ms = 0
        resumed_count = 0

        # Load the model / spawn the worker (if a fresh load is even needed) BEFORE
        # opening the Progress bar below. ensure_ready() shows its own status
        # spinner while the model loads; starting that spinner while the panel-loop
        # Progress bar is already live on screen is two Rich Live displays fighting
        # over the same terminal lines at once - the "two progress bars" glitch.
        # Doing it up front keeps the two phases (load, then synthesize) as two
        # clean, sequential pieces of output instead.
        needs_synthesis = any(
            entry.get("text", "").strip() and not is_resumable(panel_ids[idx])
            for idx, entry in enumerate(narration_entries)
        )
        if needs_synthesis:
            self._synth.ensure_ready()

        # refresh_per_second=4: see downloader/mangadex.py's Progress() for
        # why - this is the longest-running bar in the whole pipeline (one
        # tick per synthesized panel, easily tens of minutes for a full
        # chapter), so it's the most likely place a locked-screen terminal
        # that isn't draining its pty buffer would actually fill it up.
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total} panels"),
            refresh_per_second=4,
        ) as progress:
            task = progress.add_task("[yellow]Synthesizing vocal tracks...", total=len(narration_entries))

            # narration.json entries only ever carry `panel_id` and `text`
            # (see prompts/narration.md) - there's no per-panel emotion or
            # pause field in that schema, and nothing here sets one: Kokoro
            # reads every panel in the configured voice's own register, which
            # is what keeps a recap sounding like one narrator telling the
            # story rather than reacting to it. Pausing uses the one
            # configured gap (AudioConfig.pause_between_panels_ms) for every
            # panel instead of a per-panel override.
            pause_after_ms = self.audio_config.pause_between_panels_ms
            for idx, entry in enumerate(narration_entries, start=1):
                panel_id = panel_ids[idx - 1]
                text = entry.get("text", "").strip()

                raw_clip_path = audio_dir / f"{panel_id}_raw.wav"
                processed_clip_path = audio_dir / f"{panel_id}.wav"

                # RESUME GUARD: Reuse existing clean WAV if present and non-empty
                if is_resumable(panel_id):
                    segment = AudioSegment.from_file(processed_clip_path)
                    # Re-exported ONLY when the configured gain actually
                    # moved: rewriting every cached clip on every run would
                    # churn a chapter's worth of files (and their mtimes)
                    # for nothing.
                    if is_audible_gain(boost_delta_db):
                        segment = apply_boost(segment, boost_delta_db, panel_id)
                        atomic_export(segment, processed_clip_path)
                    duration_ms = len(segment)
                    resumed_count += 1
                else:
                    if text:
                        self._synth.synthesize(
                            text=text,
                            voice=voice,
                            output_wav=raw_clip_path,
                        )

                        # Through resample.load_audio, not set_frame_rate: the
                        # engines synthesize at their own rate (Kokoro at
                        # 24 kHz) and pydub's resampler would fold a mirror
                        # image of the whole clip in above 12 kHz on the way to
                        # 44.1 kHz. See audio/resample.py for the measurement.
                        segment = load_audio(raw_clip_path, self.audio_config.sample_rate, channels=1)

                        # Over the clip's own silence, never over its speech
                        # - these de-click the edges, they aren't a volume
                        # envelope. See clips.apply_edge_fades.
                        segment = apply_edge_fades(segment, self.audio_config.edge_fade_ms)

                        # After the fades, so the boost can't be partly faded
                        # back out at each edge, and before the export, so the
                        # clip on disk is the boosted one.
                        segment = apply_boost(segment, boost_db, panel_id)

                        atomic_export(segment, processed_clip_path)

                        if raw_clip_path.exists():
                            raw_clip_path.unlink()

                        duration_ms = len(segment)
                    else:
                        duration_ms = max(pause_after_ms, 500)
                        silence = AudioSegment.silent(duration=duration_ms, frame_rate=self.audio_config.sample_rate)
                        atomic_export(silence, processed_clip_path)

                start_ms = current_timeline_ms
                end_ms = start_ms + duration_ms
                total_panel_slot_ms = duration_ms + pause_after_ms

                timing_data.append({
                    "index": idx,
                    "panel_id": panel_id,
                    "text": text,
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

        # Idempotent write: skip touching the file at all if the content is
        # identical to what's already there. This isn't just tidiness -
        # audio/mix.py treats this file's mtime as "did the synthesized
        # audio actually change" to decide whether it needs to re-mix (and
        # video/render.py, in turn, treats master_audio.wav's mtime the same
        # way to decide whether to re-encode). Rewriting this file on every
        # single TTS call - even a fully-resumed one where nothing was
        # regenerated - would make that staleness check permanently useless:
        # every downstream step would think something changed every time,
        # forever re-mixing and re-encoding chapters that are actually
        # already done.
        new_timing = {
            "chapter": str(chapter_num),
            # What is actually baked into the clips this file describes - read
            # back at the top of the next run to work out the difference. It
            # also earns its keep in the staleness chain described below: a
            # changed boost changes this file, so mix and render both notice
            # and redo themselves, which is what makes turning the knob
            # reach the finished video without any extra flag.
            "volume_boost_db": boost_db,
            "total_timeline_ms": current_timeline_ms,
            "total_timeline_sec": round(current_timeline_ms / 1000.0, 3),
            "panels": timing_data
        }
        if read_json_or(timing_manifest_path, None) != new_timing:
            write_json(timing_manifest_path, new_timing)

        if clipped_panels:
            shown = ", ".join(clipped_panels[:5]) + (" ..." if len(clipped_panels) > 5 else "")
            console.print(
                f"[yellow]{len(clipped_panels)} panel(s) clipped at {boost_db:+.1f} dB[/] "
                f"[dim]({shown}) - the loudest parts are squared off rather than louder. "
                f"Lower volume_boost_db for this engine and re-run; the difference is "
                f"re-applied to the existing clips, nothing is re-synthesized.[/]"
            )
        if resumed_count > 0:
            console.print(f"[dim cyan](Resumed {resumed_count} existing audio clips without re-generating)[/]")
        console.print(f"[bold green]✓ Voice audio synthesized and synchronized for {len(narration_entries)} panels![/]")
        return timing_manifest_path
