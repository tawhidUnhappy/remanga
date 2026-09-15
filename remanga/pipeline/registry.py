"""The ordered list of pipeline steps: the core steps, with every extension's
steps placed among them (remanga.extensions), and the default order derived
from it.

Ordered, once - both STEP_REGISTRY (source of truth for what a step is/does)
and DEFAULT_STEPS (the default order, used as the fallback whenever a project
has never chosen) come from this one list."""

from __future__ import annotations

from remanga.extensions import load_extensions, place
from remanga.pipeline.spec import Step
from remanga.pipeline.steps import (
    run_crop,
    run_download,
    run_init_narration,
    run_mark,
    run_mix,
    run_narration,
    run_package,
    run_pause,
    run_render,
    run_review,
    run_tts,
)

CORE_STEPS: list[Step] = [
    Step("download", "Download chapter pages from MangaDex", run_download),
    Step("mark", "Mark panels via the Panel Marker web UI (writes crops.json)", run_mark, needs=["download"]),
    Step("crop", "Crop panels out of the marked pages", run_crop, needs=["mark"]),
    Step("package", "Package the panels into the chosen upload formats (sheets/zips/PDF)",
         run_package, needs=["crop"]),
    Step("init-narration",
         "Create a completely empty narration.json - zero bytes, not even {} - for the script "
         "to be written into",
         run_init_narration),
    Step("pause", "Wait for Enter before going on - room to fill something in by hand first",
         run_pause),
    Step("narration", "Write narration.json + memory.json via LLM copy/paste", run_narration,
         needs=["package"]),
    Step("review", "Review narration via the Narration Reviewer web UI", run_review, needs=["narration"]),
    Step("tts", "Synthesize vocal audio via TTS", run_tts, needs=["review"]),
    Step("mix", "Mix master audio track (narration + BGM + loudnorm)", run_mix, needs=["tts"]),
    Step("render", "Render the final recap video", run_render, needs=["mix"]),
]

STEP_REGISTRY: list[Step] = place(
    CORE_STEPS,
    [placed for extension in load_extensions() if extension.steps for placed in extension.steps()],
    lambda step: step.name,
)
STEP_BY_NAME: dict[str, Step] = {step.name: step for step in STEP_REGISTRY}

# Offered in the step checklist but left out of the default order: each is an
# alternative to a default step, and running both would do that part twice.
ALTERNATIVE_STEPS = frozenset(name for extension in load_extensions() for name in extension.alternative_steps)
DEFAULT_STEPS: list[str] = [step.name for step in STEP_REGISTRY if step.name not in ALTERNATIVE_STEPS]
