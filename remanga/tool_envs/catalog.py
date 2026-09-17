"""The tool environments themselves, one ToolSpec each - today only Kokoro.

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
)

TOOL_NAMES = tuple(spec.name for spec in TOOLS)


def tool_spec(name: str) -> ToolSpec | None:
    """The entry for `name`, or None if no tool is called that."""
    for spec in TOOLS:
        if spec.name == name:
            return spec
    return None
