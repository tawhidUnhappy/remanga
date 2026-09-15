"""The tool environments themselves, one ToolSpec each.

Adding a tool is an entry here plus the code that drives it; removing one is
deleting both. bootstrap.sh, `remanga setup-tools` and a tool's own first use
all provision from this list, so none of them can drift from the others."""

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
        "deepseek-ocr", "DeepSeek-OCR-2", "OCR for the Narration Writer's per-panel button",
        steps=(
            # transformers is pinned exactly, torch is not. The model card pins
            # both (transformers==4.46.3, torch==2.6.0), but the pins are not
            # equally load-bearing: the pinned transformers is what the model's
            # own trust_remote_code modeling code is written against, while
            # torch 2.6 simply is not in the wheel index this machine resolves
            # to, so honouring it would mean installing wheels built for a
            # different machine. einops/addict/easydict are undeclared imports
            # that modeling code needs.
            #
            # flash-attn is deliberately absent. The card uses it, but it is a
            # long, fragile CUDA extension build and transformers falls back to
            # its own attention without it - the same reasoning that keeps
            # every other optional kernel build out of a first run.
            InstallStep((
                "torch", "transformers==4.46.3", "tokenizers==0.20.3", "einops",
                "addict", "easydict", "accelerate", "pillow", "huggingface-hub",
                "safetensors",
            )),
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
