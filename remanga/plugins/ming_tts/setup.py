"""Ming-3.0-tts's setup: its isolated environment (.tools/venv-ming-tts), the
model's source code, and its weights.

remanga runs this the first time Ming-3.0-tts is used, from bootstrap.sh and
from `./run.sh setup --tool ming-tts`. It also runs on its own:

    .venv/bin/python -m remanga.plugins.ming_tts.setup [--force] [--torch-backend cu129] [--no-weights]

Only stdlib and remanga.tool_envs.spec at the top: the plug-in's __init__
imports TOOL from here when remanga starts."""

from __future__ import annotations

from pathlib import Path

from remanga.tool_envs.spec import TOOLS_DIR, InstallStep, ToolSpec

# Upstream is a folder of modules, not a package - nothing to pip install - so
# the source is fetched at this commit and put on the worker's sys.path.
MING_REPO = "https://github.com/inclusionAI/Ming-3.0-tts"
MING_COMMIT = "028c1eace193e7acdb256453da89b6e9207e052b"
SOURCE_DIR = TOOLS_DIR / f"ming-tts-src-{MING_COMMIT[:12]}"

TOOL = ToolSpec(
    "ming-tts", "Ming-3.0-tts", "TTS engine - built-in English voices",
    steps=(
        # Upstream's requirements.txt, except torch: it pins 2.6, which has no
        # wheels on this machine's cu129 index, so 2.8 as IndexTTS uses. The
        # rest stay at upstream's pins - transformers especially, since its
        # modeling code is written against 4.46.
        InstallStep(("torch==2.8.*", "torchaudio==2.8.*", "transformers==4.46.3", "tokenizers",
                     "accelerate==1.3.0", "huggingface-hub", "numpy", "soundfile", "tqdm", "loguru",
                     "x_transformers==2.9.2", "diffusers==0.33.0", "onnxruntime", "inflect",
                     "einops", "packaging")),
        # Text normalization (numbers, abbreviations) - optional upstream, but
        # without it "3" is read however the model guesses.
        InstallStep(("pynini==2.1.6",), torch_backend=False),
    ),
    install="remanga.plugins.ming_tts.setup:install",
    weights="remanga.plugins.ming_tts.setup:weights",
)


def ensure_source() -> Path:
    """The model's source at MING_COMMIT, fetched once into .tools/."""
    if (SOURCE_DIR / "ming_tts.py").is_file():
        return SOURCE_DIR
    import io
    import shutil
    import tarfile
    import urllib.request

    url = f"{MING_REPO}/archive/{MING_COMMIT}.tar.gz"
    print(f"Fetching the Ming-3.0-tts source ({MING_COMMIT[:12]})...")
    with urllib.request.urlopen(url, timeout=120) as response:
        archive = response.read()
    staging = SOURCE_DIR.with_name(SOURCE_DIR.name + ".tmp")
    shutil.rmtree(staging, ignore_errors=True)
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
        tar.extractall(staging, filter="data")
    # The archive holds one folder, Ming-3.0-tts-<commit>/.
    (top,) = staging.iterdir()
    top.rename(SOURCE_DIR)
    staging.rmdir()
    return SOURCE_DIR


def install(torch_backend: str | None = None, force: bool = False) -> bool:
    """The environment: TOOL.steps installed with uv into .tools/venv-ming-tts,
    then the source."""
    from remanga.tool_envs import build_env

    if not build_env(TOOL, torch_backend, force=force):
        return False
    ensure_source()
    return True


def weights(config) -> None:
    """The checkpoint (scripts/download_ming_tts.py)."""
    from remanga.plugins.ming_tts.synth import model_manager

    model_manager(config.tts.ming).ensure_model()


if __name__ == "__main__":
    from remanga.tool_envs.cli import run_setup

    raise SystemExit(run_setup(TOOL))
