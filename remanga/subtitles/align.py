"""Where each panel starts and stops inside a batch's audio.

A batch is one long take, so nothing in it says where one panel's line ends
and the next begins - that knowledge was thrown away the moment the texts
were joined. What remanga still has is the exact script it asked for, and
what whisper gives back is roughly that script with a time on every word. So
the two are lined up against each other (difflib, over normalized tokens),
and every panel takes its start from the first word of its own text that was
matched and its end from the last.

Matched, not transcribed: whisper is never trusted for WHAT was said, only
for WHEN. A word it mis-hears simply fails to match and costs nothing as
long as its neighbours match, which is why a mis-heard name - the common
case in manga narration - is harmless here.

Spans come out contiguous by construction: a boundary is the midpoint of the
silence between the last word of one panel and the first of the next, so
laying the panels end to end reproduces the batch exactly, with no gap
inserted and none of the take removed."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from remanga.subtitles.normalize import words as normalize

# A batch whose script matches this much of what whisper heard is aligned;
# below it something is wrong that per-panel guessing would only hide - the
# wrong audio file, a batch that stopped early, a take in another language.
MIN_MATCH_RATIO = 0.90

# A panel with no matched word at all has no timing of its own and takes one
# interpolated from its neighbours. One or two in a chapter is whisper
# dropping a short line; a lot of them means the alignment is not working.
MAX_UNANCHORED_SHARE = 0.05


class AlignmentError(RuntimeError):
    """The narration and the audio could not be lined up well enough to cut
    a video to."""


@dataclass(frozen=True)
class PanelSpan:
    """One panel's place in the batch, in milliseconds from its start."""

    panel_id: str
    start_ms: int
    end_ms: int
    matched_words: int

    @property
    def anchored(self) -> bool:
        """Whether this span came from the panel's own words rather than
        from its neighbours."""
        return self.matched_words > 0


@dataclass(frozen=True)
class Alignment:
    spans: tuple[PanelSpan, ...]
    match_ratio: float

    @property
    def unanchored(self) -> tuple[str, ...]:
        return tuple(span.panel_id for span in self.spans if not span.anchored)


def _script_tokens(panels: list[tuple[str, str]]) -> tuple[list[str], list[int]]:
    """Every word of the batch's script, and which panel each came from."""
    tokens: list[str] = []
    owners: list[int] = []
    for index, (_, text) in enumerate(panels):
        for token in normalize(text):
            tokens.append(token)
            owners.append(index)
    return tokens, owners


def _heard_tokens(heard: list[dict]) -> tuple[list[str], list[tuple[float, float]]]:
    """Every word whisper heard, normalized, with the time it covers. One
    heard word can normalize into several tokens ("21" -> twenty one); they
    share the word's span, split evenly, so a token still lands inside the
    word it came from."""
    tokens: list[str] = []
    times: list[tuple[float, float]] = []
    for word in heard:
        parts = normalize(str(word.get("word", "")))
        if not parts:
            continue
        start, end = float(word["start"]), float(word["end"])
        step = (end - start) / len(parts)
        for i, part in enumerate(parts):
            tokens.append(part)
            times.append((start + i * step, start + (i + 1) * step))
    return tokens, times


def align(panels: list[tuple[str, str]], heard: list[dict], audio_seconds: float) -> Alignment:
    """Line the batch's script up against what whisper heard, and give every
    panel a span. `panels` is [(panel_id, text)] in the order they were
    narrated."""
    if not panels:
        raise AlignmentError("a batch with no panels cannot be aligned")

    script, owners = _script_tokens(panels)
    tokens, times = _heard_tokens(heard)
    if not script or not tokens:
        raise AlignmentError("nothing to align: the script or the transcript is empty")

    # autojunk throws away tokens it considers too popular, which for ordinary
    # English is most of the common words - exactly the ones holding a long
    # script in step.
    matcher = SequenceMatcher(a=script, b=tokens, autojunk=False)
    first: dict[int, float] = {}
    last: dict[int, float] = {}
    counts: dict[int, int] = {}
    matched = 0
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            panel = owners[block.a + offset]
            start, end = times[block.b + offset]
            first.setdefault(panel, start)
            last[panel] = end
            counts[panel] = counts.get(panel, 0) + 1
            matched += 1

    bounds = _fill_and_close(panels, first, last, counts, audio_seconds)
    return Alignment(spans=tuple(bounds), match_ratio=matched / len(script))


def _fill_and_close(panels: list[tuple[str, str]], first: dict[int, float], last: dict[int, float],
                    counts: dict[int, int], audio_seconds: float) -> list[PanelSpan]:
    """Every panel with a span: its own where it matched words, interpolated
    between its neighbours where it did not, and contiguous either way."""
    count = len(panels)
    starts: list[float | None] = [first.get(i) for i in range(count)]
    ends: list[float | None] = [last.get(i) for i in range(count)]

    # A panel nobody matched is given the room between the panels around it,
    # shared by how long its text is relative to theirs.
    for index in range(count):
        if starts[index] is not None:
            continue
        before = next((ends[j] for j in range(index - 1, -1, -1) if ends[j] is not None), 0.0)
        after = next((starts[j] for j in range(index + 1, count) if starts[j] is not None), audio_seconds)
        gap_owners = [j for j in range(count) if starts[j] is None
                      and _between(j, index, starts, ends)]
        share = max(1, len(gap_owners))
        width = max(0.0, after - before) / share
        rank = gap_owners.index(index) if index in gap_owners else 0
        starts[index] = before + rank * width
        ends[index] = before + (rank + 1) * width

    # Contiguous: each boundary is the middle of the silence between the two
    # panels, so the spans laid end to end are the take itself.
    edges = [0.0]
    edges.extend(max(ends[i], (ends[i] + starts[i + 1]) / 2.0) for i in range(count - 1))
    edges.append(audio_seconds)
    edges = _monotonic(edges, audio_seconds)

    return [PanelSpan(panel_id=panels[i][0], start_ms=round(edges[i] * 1000),
                      end_ms=round(edges[i + 1] * 1000), matched_words=counts.get(i, 0))
            for i in range(count)]


def _between(candidate: int, index: int, starts: list, ends: list) -> bool:
    """Whether `candidate` is an unmatched panel in the same run as `index`."""
    low = min(candidate, index)
    high = max(candidate, index)
    return all(starts[j] is None for j in range(low, high + 1))


def _monotonic(edges: list[float], audio_seconds: float) -> list[float]:
    """Edges that only ever move forward and stay inside the audio - a
    whisper timing that goes backwards would otherwise make a negative span."""
    fixed = [min(max(edges[0], 0.0), audio_seconds)]
    for edge in edges[1:]:
        fixed.append(min(max(edge, fixed[-1]), audio_seconds))
    return fixed


def check(alignment: Alignment, batch_name: str) -> None:
    """Raises AlignmentError when a batch is not aligned well enough to cut a
    video to. Loud rather than quiet on purpose: a misalignment is silent -
    the audio sounds perfect and the pictures are simply cut to the wrong
    words - so it has to be refused here or it ships."""
    if alignment.match_ratio < MIN_MATCH_RATIO:
        raise AlignmentError(
            f"Batch {batch_name}: only {alignment.match_ratio:.0%} of the narration was found in "
            f"what was actually said (needs {MIN_MATCH_RATIO:.0%}) - the take does not match the "
            f"script it was asked for, so the panels cannot be placed in it."
        )
    unanchored = alignment.unanchored
    if len(unanchored) > max(1, int(len(alignment.spans) * MAX_UNANCHORED_SHARE)):
        shown = ", ".join(unanchored[:5]) + ("..." if len(unanchored) > 5 else "")
        raise AlignmentError(
            f"Batch {batch_name}: {len(unanchored)} of {len(alignment.spans)} panel(s) have no word "
            f"of their own in the take ({shown}) - their timings would be guesses."
        )
