"""Joining many audio segments into one track, in a single copy.

pydub's `a + b` builds a brand-new buffer holding both, so growing a track
with `track += clip` in a loop re-copies everything accumulated so far on
every step - quadratic in the length of the track. Measured on a real
82-minute, 584-panel full recap (1,168 appends): 168.9s of nothing but
copying. Joining the raw samples once gives the byte-identical track in
0.23s."""

from __future__ import annotations

from collections.abc import Iterable

from pydub import AudioSegment


def join_segments(segments: Iterable[AudioSegment]) -> AudioSegment:
    """Every segment, end to end, as one AudioSegment - the same track
    summing them with `+` produces, including pydub's promotion of every
    part to the highest frame rate, channel count and sample width among
    them (a no-op when, as usual, they all already match)."""
    parts = list(segments)
    if not parts:
        return AudioSegment.empty()
    frame_rate = max(p.frame_rate for p in parts)
    channels = max(p.channels for p in parts)
    sample_width = max(p.sample_width for p in parts)
    data = b"".join(
        p.set_frame_rate(frame_rate).set_channels(channels).set_sample_width(sample_width).raw_data
        for p in parts
    )
    return parts[0]._spawn(data, overrides={
        "frame_rate": frame_rate, "channels": channels, "sample_width": sample_width,
        "frame_width": channels * sample_width,
    })
