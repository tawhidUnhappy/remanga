"""The tool environments themselves, one ToolSpec each - today only Chatterbox.

bootstrap.sh, `remanga setup` and a tool's own first use all provision from
this list, so none of them can drift from the others."""

from __future__ import annotations

from remanga.tool_envs.spec import InstallStep, ToolSpec

TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "chatterbox", "Chatterbox Turbo", "TTS engine - clones a narrator from a recording",
        steps=(
            # chatterbox-tts pins torch==2.6.0 exactly, which makes a plain
            # install unsatisfiable on every machine that resolves to a recent
            # wheel index: 2.6 is not in cu129 at all (it jumps from <2.6 to
            # >2.7), and uv says so - "there is no version of torch==2.6.0".
            # Like DeepSeek-OCR-2's torch pin it is not load-bearing, so the
            # dependencies go in first against this machine's torch, and the
            # package itself second with --no-deps. transformers and diffusers
            # keep upstream's exact pins - the model code is written against
            # them. Left out on purpose: gradio (upstream's demo UI, several
            # hundred MB) and spacy-pkuseg/pykakasi (Chinese/Japanese text for
            # the multilingual model, imported only inside those code paths).
            InstallStep((
                "torch", "torchaudio", "numpy<2", "librosa==0.11.0", "s3tokenizer",
                "transformers==5.2.0", "diffusers==0.29.0",
                "conformer==0.3.2", "safetensors", "pyloudnorm", "omegaconf",
                "soundfile", "huggingface-hub",
            )),
            # The PyPI package named "resemble-perth" is an abstract-base-class
            # stub with no working implementation - `PerthImplicitWatermarker`
            # imports as None from it, which fails with an opaque "'NoneType'
            # object is not callable" the instant a worker tries to construct
            # one. chatterbox-tts's own pyproject.toml pins the real
            # implementation from GitHub instead of PyPI for exactly this
            # reason; installed here the same way, before the --no-deps
            # package below would otherwise pull in the broken PyPI one.
            InstallStep(
                ("resemble-perth @ git+https://github.com/resemble-ai/Perth.git@master",),
                torch_backend=False,
            ),
            InstallStep(("chatterbox-tts==0.1.7",), torch_backend=False, no_deps=True),
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
