"""The tool environments themselves, one ToolSpec each: Kokoro-82M for the
narration and MAGI v3 for finding panels.

bootstrap.sh, `remanga setup` and a tool's own first use all provision from
this list, so none of them can drift from the others."""

from __future__ import annotations

from remanga.tool_envs.spec import InstallStep, ToolSpec

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "kokoro", "Kokoro-82M", "TTS engine - fixed built-in voices",
        steps=(
            InstallStep(("torch", "kokoro", "soundfile", "numpy", "huggingface-hub")),
            # misaki (Kokoro's English G2P, pulled in above) loads a spaCy
            # pipeline, and spaCy ships its models as separate packages rather
            # than fetching them at runtime - without this every synthesis dies
            # on "Can't find model 'en_core_web_sm'".
            #
            # Installed from the release URL rather than via `python -m spacy
            # download`: that command shells out to the ambient installer,
            # which under uv reports "Download and installation successful"
            # and installs NOTHING into the target venv. Verified - it exits 0
            # and the model is still absent. The URL form is the only one that
            # reliably lands here. No torch in it, so no wheel index needed.
            InstallStep(
                ("https://github.com/explosion/spacy-models/releases/download/"
                 "en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl",),
                torch_backend=False,
            ),
        ),
    ),
    ToolSpec(
        "magi", "MAGI v3", "panel detection for the Panel Marker web UI",
        steps=(
            # einops/matplotlib: undeclared imports MAGI v3's remote modeling
            # code needs beyond its own requirements. magi_assist.py
            # auto-installs anything still missing on first load; listing the
            # known ones saves a round trip.
            InstallStep((
                "torch", "transformers<4.52.0", "timm", "shapely",
                "pytorch-metric-learning", "huggingface-hub", "pillow", "numpy",
                "einops", "matplotlib",
            )),
        ),
    ),
    ToolSpec(
        "qwen-tts", "Qwen3-TTS", "TTS engine - voices designed from a description, and preset narrators",
        steps=(
            # qwen-tts pulls transformers and its own tokenizer stack; torch
            # comes from this machine's wheel index (see hardware.py), which
            # is why it is named first rather than left to the dependency
            # resolver. flash-attn is deliberately left out: it builds from
            # source for many minutes and only saves some VRAM.
            InstallStep(("torch", "torchaudio", "qwen-tts", "soundfile", "huggingface-hub")),
        ),
    ),
)

TOOL_NAMES = tuple(spec.name for spec in TOOLS)


def tool_spec(name: str) -> ToolSpec | None:
    """The entry for `name`, or None if no tool is called that."""
    for spec in TOOLS:
        if spec.name == name:
            return spec
    return None
