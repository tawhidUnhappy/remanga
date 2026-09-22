"""The reference a voice is cloned from: the piece of the recording that is
used, and what that piece says - built together, so the two agree.

A voice cloned from a recording sounds closer when the model is told what the
recording says: it can then use the audio in context rather than leaning on
the speaker embedding alone. remanga knows the words when it designed the
sample itself; for a recording the user supplied, nothing does, and
faster-whisper (here for the batched narration anyway) reads them once and
caches the answer beside the recording.

**The transcript must be of exactly the audio the model gets, and must end
where it ends.** Qwen3-TTS clones in context, so a word in `ref_text` that is
not in `ref_audio` is a word it has been shown mid-sentence and never heard
finished - and it finishes it, out loud, in the narration. That is not
hypothetical: the user's 31-second recording was cut at a flat 15.000s, in
the middle of "And that danger is our contagiously handsome main guy", and
whisper - which invents an ending when audio stops mid-sentence - transcribed
the cut as "And that danger is going to be the danger of the future." Seven
words that are nowhere in the recording, all stamped with zero duration at
the clip's last frame, went to the model as fact, and it read them into the
chapter's audio (user report, 2026-09-22).

So the pair is built in one place, here:

  1. take at most REFERENCE_MAX_SECONDS of the recording;
  2. read it with word timings;
  3. drop any word the audio cannot contain - the zero-length tail crammed
     against the end, which is what a whisper hallucination looks like;
  4. cut BOTH the audio and the text at the last sentence that finished
     inside it, so neither has anything the other does not.

Never fatal. A machine that cannot run whisper, or a recording it makes
nothing of, leaves the transcript empty and the clone falls back to the
speaker embedding (x_vector_only_mode) - which is exactly what it did before
any of this, and cannot leak words because it is given none.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from remanga.audio.synth.qwen import REFERENCE_MAX_SECONDS, reference_pair_path
from remanga.config import SubtitlesConfig, TTSConfig
from remanga.console import console, escape as _esc

# A word whose timings are this close together is not a word anyone said: it
# is the decoder filling in an ending for audio that stopped mid-sentence, and
# every one of them lands against the clip's final frame. Real words in the
# same recording run 120-300 ms.
_EMPTY_WORD_MS = 20.0

# How close to the end of the clip a word has to sit to be part of that tail.
_TAIL_WINDOW_MS = 250.0

# What ends a sentence. The pair is cut after one of these, so the model is
# never shown half a thought.
_SENTENCE_END = ".!?"

# Kept either side of the speech when the clip is re-cut, so a word is never
# clipped by a frame.
_PAD_MS = 120


def _drop_invented_tail(words: list[dict[str, Any]], clip_ms: float) -> list[dict[str, Any]]:
    """Every word up to the first of the zero-length ones stamped against the
    end of the clip - see _EMPTY_WORD_MS."""
    kept = list(words)
    while kept:
        word = kept[-1]
        start_ms, end_ms = float(word["start"]) * 1000, float(word["end"]) * 1000
        if end_ms - start_ms <= _EMPTY_WORD_MS and end_ms >= clip_ms - _TAIL_WINDOW_MS:
            kept.pop()
            continue
        break
    return kept


def _cut_at_last_sentence(words: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """The words up to and including the last one that ends a sentence, and
    that text. Empty when the clip holds no finished sentence at all - better
    no transcript (the clone falls back to the speaker embedding) than one
    that stops in the middle of a thought."""
    last = -1
    for index, word in enumerate(words):
        if str(word.get("word", "")).strip().endswith(tuple(_SENTENCE_END)):
            last = index
    if last < 0:
        return [], ""
    kept = words[:last + 1]
    return kept, "".join(word["word"] for word in kept).strip()


def _read_pair(path: Path) -> tuple[Path, str] | None:
    """A pair built earlier, if it is still the one this recording asks for."""
    if not path.exists():
        return None
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
        clip = path.with_name(saved["clip"])
        source = path.with_name(saved["source"])
        if not clip.exists() or not source.exists():
            return None
        if source.stat().st_mtime > path.stat().st_mtime:
            return None      # the recording changed; the pair is about a different one
        return clip, str(saved["text"]).strip()
    except (OSError, ValueError, KeyError):
        return None


def ensure_reference_pair(tts_config: TTSConfig, subtitles_config: SubtitlesConfig) -> tuple[Path | None, str]:
    """The clip the clone is built from and what it says, agreeing with each
    other. `("", "")`-ish - (None, "") - when there is no recording to clone
    from; (clip, "") when nothing could read it, which is the speaker-
    embedding fallback.

    Built once and cached beside the recording; a changed recording rebuilds
    it."""
    qwen = tts_config.qwen
    if tts_config.spec.name != "qwen" or not qwen.designed:
        return None, ""

    sample = Path(qwen.designed_sample)
    if not sample.exists():
        return None, ""
    # remanga wrote this sample itself and chose the words, so the pair is
    # already known and exact - nothing to read, nothing to cut.
    if qwen.designed_text.strip():
        return sample, qwen.designed_text.strip()

    pair_path = reference_pair_path(sample)
    existing = _read_pair(pair_path)
    if existing:
        return existing

    from pydub import AudioSegment

    from remanga.subtitles.transcribe import Transcriber

    console.print(f"[cyan]Reading what {_esc(sample.name)} says, once - a cloned voice matches "
                  f"closer when the model is told the words of the recording it is copying...[/]")

    audio = AudioSegment.from_file(sample)
    clip_path = sample.with_name(f"{sample.stem}.reference.wav")
    limit_ms = int(REFERENCE_MAX_SECONDS * 1000)
    first_cut = audio[:limit_ms] if len(audio) > limit_ms else audio
    first_cut.export(clip_path, format="wav")

    transcriber = Transcriber(subtitles_config)
    try:
        transcriber.ensure_ready()
        words_path = clip_path.with_suffix(".words.json")
        transcriber.words_for(clip_path, words_path)
        words = json.loads(words_path.read_text(encoding="utf-8"))["words"]
        words_path.unlink(missing_ok=True)
    except Exception as e:
        console.print(f"[yellow]Could not read the recording ({_esc(str(e)[:120])}) - cloning from "
                      f"the voice alone, as before.[/]")
        return clip_path, ""
    finally:
        transcriber.shutdown()

    kept = _drop_invented_tail(words, len(first_cut))
    dropped = len(words) - len(kept)
    kept, text = _cut_at_last_sentence(kept)
    if not text:
        console.print(f"[yellow]{_esc(sample.name)} has no sentence that finishes inside its first "
                      f"{REFERENCE_MAX_SECONDS:g}s - cloning from the voice alone, which cannot "
                      f"put words in the narration.[/]")
        return clip_path, ""

    # The audio is cut to the same place as the text: the clone is shown a
    # recording and a transcript that end together, on a finished sentence.
    end_ms = min(len(first_cut), int(float(kept[-1]["end"]) * 1000) + _PAD_MS)
    first_cut[:end_ms].export(clip_path, format="wav")
    pair_path.write_text(json.dumps({
        "source": sample.name, "clip": clip_path.name, "clip_seconds": round(end_ms / 1000, 2),
        "text": text,
    }, indent=1, ensure_ascii=False), encoding="utf-8")
    # The transcript this used to keep on its own, next to a clip cut
    # somewhere else entirely. Nothing reads it any more, and a file that
    # looks like the answer but is not is how this went wrong the first time.
    sample.with_name(f"{sample.stem}.transcript.txt").unlink(missing_ok=True)
    sample.with_name(f"{sample.stem}.first{int(REFERENCE_MAX_SECONDS)}s.wav").unlink(missing_ok=True)

    note = f", dropped {dropped} word(s) the recording does not contain" if dropped else ""
    console.print(f"[dim]Cloning from the first {end_ms / 1000:.1f}s of {_esc(sample.name)}{note}. "
                  f"It says: {_esc(text[:90])}{'...' if len(text) > 90 else ''}[/]")
    return clip_path, text


def ensure_reference_text(tts_config: TTSConfig, subtitles_config: SubtitlesConfig) -> str:
    """What the reference clip says - the pair's text half. Kept as its own
    name because that is what the TTS entry point asks for before the model
    loads (audio/tts.py)."""
    return ensure_reference_pair(tts_config, subtitles_config)[1]
