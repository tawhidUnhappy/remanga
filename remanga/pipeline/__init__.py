"""Modular step-registry + JSON pipeline config: the download -> mark ->
crop -> package -> narration -> review -> tts -> mix -> render sequence,
expressed as an ordered list of named, independently runnable steps instead
of one hardcoded function. This lets a caller run "just one tool" (a single
step name), "a lot of them" (an arbitrary subset, in any order), or the full
default pipeline - driven by the project's own saved step list
(project.json's "pipeline") instead of code.

    spec.py     - what a Step is
    steps.py    - the core steps' work
    registry.py - the ordered registry, extensions' steps included
    runner.py   - running a pipeline, and loading a project's

The wizard's own "run the pipeline" path is just the `run` command, which
calls run_pipeline(project, chapter, config, load_pipeline(project))."""

from __future__ import annotations

from remanga.pipeline.registry import ALTERNATIVE_STEPS, DEFAULT_STEPS, STEP_REGISTRY
from remanga.pipeline.runner import load_pipeline, run_pipeline
from remanga.pipeline.spec import Step

__all__ = ["ALTERNATIVE_STEPS", "DEFAULT_STEPS", "STEP_REGISTRY", "Step", "load_pipeline", "run_pipeline"]
