"""Whole-manga compilation: run every chapter's remaining pipeline steps
(TTS, mix, render), keeping each chapter's own final MP4 exactly as running
`render` on it one at a time would - then join all of them into ONE
continuous recap video rather than leaving 24 separate ones as the only
whole-manga option.

    discovery.py - which chapters a project has, in reading order
    timeline.py  - the one continuous cross-chapter audio/frame timeline
    compiler.py  - the two-phase compile and its final encode

Keeping each chapter's own MP4 is deliberate: TTS and frame compositing are
the expensive steps and are already cached, but so are the mix and the
per-chapter render now - re-running after only a BGM/volume change re-mixes
and re-encodes just the per-chapter video, never touching TTS or frame
compositing."""

from __future__ import annotations

from remanga.full_recap.compiler import FullRecapCompiler
from remanga.full_recap.discovery import chapter_sort_key, discover_chapters
from remanga.full_recap.timeline import assemble_combined_audio

__all__ = [
    "FullRecapCompiler",
    "assemble_combined_audio",
    "chapter_sort_key",
    "discover_chapters",
]
