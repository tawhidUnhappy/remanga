from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
from pydub import AudioSegment
from rich.progress import BarColumn, Progress, TextColumn

from remanga import setup
from remanga.audio.synth import IndexTTSSynthesizer
from remanga.config import AudioConfig, RemangaConfig, TTSConfig
from remanga.console import console
from remanga.json_io import read_json, write_json
from remanga.paths import get_chapter_dir


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
            f"[cyan]Synthesizing consistent speech via IndexTTS-2.5[/] "
            f"[dim](Lang: {self.tts_config.lang}, Temp: {self.tts_config.temperature}, Reference Voice: {spk_prompt_path})[/]"
        )

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

        def atomic_export(segment: AudioSegment, final_path: Path) -> None:
            """Exports to a temp file alongside `final_path`, then atomically renames
            it into place, so a process killed mid-export (Ctrl+C, OOM-kill, crash)
            never leaves a truncated file sitting at `final_path` looking finished -
            is_cached_complete() only ever sees either the complete previous file or
            nothing there at all."""
            tmp_path = final_path.with_name(final_path.name + ".tmp")
            segment.export(tmp_path, format="wav")
            tmp_path.replace(final_path)

        timing_data: List[Dict[str, Any]] = []
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

            # narration.json entries only ever carry `panel_id` and `text` now
            # (see prompts/narration.md) - there's no per-panel emotion or
            # pause field in that schema. Emotion isn't set here at all:
            # IndexTTSSynthesizer.synthesize() sends no emo_vector, so
            # IndexTTS-2.5 infers its own natural emotion/prosody straight from
            # each panel's `text` (its wording and punctuation) instead of a
            # forced tag. Pausing uses the one configured gap
            # (AudioConfig.pause_between_panels_ms) for every panel instead of
            # a per-panel override.
            pause_after_ms = self.audio_config.pause_between_panels_ms
            for idx, entry in enumerate(narration_entries, start=1):
                panel_id = panel_ids[idx - 1]
                text = entry.get("text", "").strip()

                raw_clip_path = audio_dir / f"{panel_id}_raw.wav"
                processed_clip_path = audio_dir / f"{panel_id}.wav"

                # RESUME GUARD: Reuse existing clean WAV if present and non-empty
                if is_resumable(panel_id):
                    segment = AudioSegment.from_file(processed_clip_path)
                    duration_ms = len(segment)
                    resumed_count += 1
                else:
                    if text:
                        self._synth.synthesize(
                            text=text,
                            spk_prompt_path=spk_prompt_path,
                            output_wav=raw_clip_path,
                        )

                        segment = AudioSegment.from_file(raw_clip_path)
                        segment = segment.set_frame_rate(self.audio_config.sample_rate).set_channels(1)

                        if self.audio_config.edge_fade_ms > 0 and len(segment) > (self.audio_config.edge_fade_ms * 2):
                            segment = segment.fade_in(self.audio_config.edge_fade_ms).fade_out(self.audio_config.edge_fade_ms)

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
