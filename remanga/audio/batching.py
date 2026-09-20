"""Which panels are narrated together in one generation.

A panel synthesized on its own is a generation on its own, and the voice
starts again every time: Qwen picks the pitch, pace and weight of a line
from nothing but that line, so two panels of the same scene come back in
audibly different tones. Trimming the silence between them made the joins
tight and changed none of that - it is not a gap, it is a new take. The only
thing that keeps a chapter in one voice is asking for it in one go.

So panels are joined into batches, each batch is one call, and where a panel
starts inside the result is read back off the audio afterwards
(remanga/subtitles/). A batch is named for its ends - `{first}-{last}.wav` -
so a folder of them says what it holds without opening anything.

Batches break on PAGE boundaries rather than wherever the character count
runs out. Not for how it sounds - a page break is a scene break often enough
to be a good seam, but the real reason is what an edit costs: packed
greedily, inserting one panel early in a chapter shifts every boundary after
it and re-synthesizes the whole chapter; anchored to pages, it re-does one
batch and leaves the rest byte-identical."""

from __future__ import annotations

from dataclasses import dataclass

from remanga.narration import StoryPanel

# How many characters of narration a second of speech is worth. Measured by
# generating real narration as joined batches in the user's own cloned voice:
# 1,229 characters came back as 55.5s and 3,318 as 142.2s, so 22.1 and 23.3.
# Deliberately NOT the 18.9 the finished chapter measures - that figure is
# per-panel audio after its silence is trimmed, and a batch has no per-panel
# silence to trim. Only used to decide where to break; nothing downstream
# trusts it, because the real durations are read back off the audio.
CHARS_PER_SECOND = 22.5

# The hard ceiling, whatever the settings ask for. Qwen3-TTS's shipped
# generation budget is max_new_tokens 8192 at 12.5 frames/second = 655s, and
# it does not fail when it runs out - it stops mid-sentence, with no error.
# This is 80% of it: CHARS_PER_SECOND is an average over two takes, and a
# batch that happens to be read 20% slower than that still has to finish
# inside the budget rather than lose its last sentences.
MAX_BATCH_SECONDS = 520.0

# What goes between two panels' narration in one call. A single space, so the
# model reads them as consecutive sentences of one paragraph, which is what
# they are - the full stop each line already ends with is what it takes its
# breath from.
JOIN = " "


@dataclass(frozen=True)
class Batch:
    """One generation: the panels in it, in order."""

    panels: tuple[StoryPanel, ...]

    @property
    def name(self) -> str:
        """`{first}-{last}`, or just the panel id when a batch holds one."""
        first, last = self.panels[0].panel_id, self.panels[-1].panel_id
        return first if first == last else f"{first}-{last}"

    @property
    def text(self) -> str:
        return JOIN.join(panel.text for panel in self.panels)

    @property
    def estimated_seconds(self) -> float:
        return len(self.text) / CHARS_PER_SECOND


def page_of(panel_id: str) -> str:
    """The page a panel was cut from, as its id spells it
    (`{chapter}_{page}_{panel}`). A name that is not in that shape is its own
    page, which makes every panel its own break - worse batching, never a
    wrong one."""
    parts = panel_id.split("_")
    return parts[1] if len(parts) >= 3 else panel_id


def pages(panels: list[StoryPanel]) -> list[list[StoryPanel]]:
    """The panels grouped into the pages they came from, in order."""
    grouped: list[list[StoryPanel]] = []
    for panel in panels:
        if grouped and page_of(grouped[-1][0].panel_id) == page_of(panel.panel_id):
            grouped[-1].append(panel)
        else:
            grouped.append([panel])
    return grouped


def plan_batches(panels: list[StoryPanel], target_minutes: float) -> list[Batch]:
    """The panels packed into batches of about `target_minutes`, breaking
    only between pages.

    A page longer than the target on its own becomes its own batch rather
    than being split: a page is a handful of panels, so this is theory
    rather than practice, but splitting one would put a seam inside a scene
    to save nothing."""
    target = min(max(target_minutes, 0.0) * 60.0, MAX_BATCH_SECONDS)
    batches: list[Batch] = []
    current: list[StoryPanel] = []
    current_seconds = 0.0

    for page in pages(panels):
        page_seconds = sum(len(panel.text) for panel in page) / CHARS_PER_SECOND
        if current and current_seconds + page_seconds > target:
            batches.append(Batch(tuple(current)))
            current, current_seconds = [], 0.0
        current.extend(page)
        current_seconds += page_seconds

    if current:
        batches.append(Batch(tuple(current)))
    return batches
