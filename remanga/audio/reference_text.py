"""Working out what a reference recording says, once.

A voice cloned from a recording sounds closer when the model is told what the
recording says - it can then use the audio in context rather than leaning on
the speaker embedding alone. remanga knows the words when it designed the
sample itself; for a recording the user supplied, nothing does, and until
faster-whisper was here for the batched narration there was no way to find
out. There is now, and it costs one transcription ever: the result is cached
beside the recording (audio/synth/qwen.py:reference_text_path).

Never fatal. A machine that cannot run whisper, or a recording it makes
nothing of, leaves the transcript empty and the clone falls back to the
speaker embedding - which is exactly what it did before any of this."""

from __future__ import annotations

import json
from pathlib import Path

from remanga.audio.synth.qwen import reference_text_path
from remanga.config import SubtitlesConfig, TTSConfig
from remanga.console import console, escape as _esc


def ensure_reference_text(tts_config: TTSConfig, subtitles_config: SubtitlesConfig) -> str:
    """The transcript of the configured reference recording, read and cached
    if this is the first time anything has asked. "" when there is no
    recording, when its words are already known, or when reading them
    failed."""
    qwen = tts_config.qwen
    if tts_config.spec.name != "qwen" or not qwen.designed or qwen.designed_text.strip():
        return qwen.designed_text.strip()

    sample = Path(qwen.designed_sample)
    cached = reference_text_path(sample)
    if cached.exists():
        return cached.read_text(encoding="utf-8").strip()
    if not sample.exists():
        return ""

    # Imported here: the TTS path has no business depending on the subtitles
    # tool when the transcript is already known, which is every run but one.
    from remanga.audio.synth.qwen import _reference_clip
    from remanga.subtitles.transcribe import Transcriber

    console.print(f"[cyan]Reading what {_esc(sample.name)} says, once - a cloned voice matches "
                  f"closer when the model is told the words of the recording it is copying...[/]")
    transcriber = Transcriber(subtitles_config)
    try:
        transcriber.ensure_ready()
        clip = _reference_clip(sample)
        out = cached.with_suffix(".words.json")
        transcriber.words_for(clip, out)
        words = json.loads(out.read_text(encoding="utf-8"))["words"]
        text = "".join(word["word"] for word in words).strip()
        out.unlink(missing_ok=True)
    except Exception as e:
        console.print(f"[yellow]Could not read the recording ({_esc(str(e)[:120])}) - cloning from "
                      f"the voice alone, as before.[/]")
        return ""
    finally:
        transcriber.shutdown()

    if not text:
        return ""
    cached.write_text(text, encoding="utf-8")
    console.print(f"[dim]The recording says: {_esc(text[:90])}{'...' if len(text) > 90 else ''}[/]")
    return text
