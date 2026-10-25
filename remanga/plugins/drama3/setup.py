"""Fish Audio Drama 3's setup: an empty isolated environment for its worker
script (.tools/venv-drama3), speech.cpp's release (the program that runs the
model), and the model file.

remanga runs this the first time Drama 3 is used, from bootstrap.sh and from
`./run.sh setup --tool drama3`. It also runs on its own:

    .venv/bin/python -m remanga.plugins.drama3.setup [--force] [--no-weights]

Only stdlib and remanga.tool_envs.spec at the top: the plug-in's __init__
imports TOOL from here when remanga starts."""

from __future__ import annotations

from pathlib import Path

from remanga.tool_envs.spec import TOOLS_DIR, ToolSpec

# speech.cpp's prebuilt Linux release for Vulkan - no CUDA toolkit, no Python
# packages. Its archive is checked against this SHA-256, taken from the
# release's own SHA256SUMS.
SPEECH_VERSION = "0.8.11"
SPEECH_ARCHIVE = f"speech-{SPEECH_VERSION}-linux-x64-vulkan.zip"
SPEECH_SHA256 = "91925a09ceed23b87197877e744ff763df83262582d195338282121e53e7e6f9"
SPEECH_URL = f"https://github.com/nyosegawa/speech.cpp/releases/download/v{SPEECH_VERSION}/{SPEECH_ARCHIVE}"
SPEECH_DIR = TOOLS_DIR / f"speech-cpp-{SPEECH_VERSION}"

TOOL = ToolSpec(
    "drama3", "Fish Audio Drama 3", "TTS engine - described voices, via speech.cpp",
    install="remanga.plugins.drama3.setup:install",
    weights="remanga.plugins.drama3.setup:weights",
)


def ensure_speech() -> Path:
    """speech.cpp's executable at SPEECH_VERSION, fetched once into .tools/."""
    executable = SPEECH_DIR / "speech"
    if executable.is_file():
        return executable
    import hashlib
    import io
    import shutil
    import urllib.request
    import zipfile

    print(f"Fetching speech.cpp {SPEECH_VERSION}...")
    with urllib.request.urlopen(SPEECH_URL, timeout=300) as response:
        archive = response.read()
    digest = hashlib.sha256(archive).hexdigest()
    if digest != SPEECH_SHA256:
        raise RuntimeError(f"{SPEECH_ARCHIVE} has SHA-256 {digest}, not the release's {SPEECH_SHA256}")
    staging = SPEECH_DIR.with_name(SPEECH_DIR.name + ".tmp")
    shutil.rmtree(staging, ignore_errors=True)
    # The executable alone: libspeech is linked into it, and it needs only the
    # system's Vulkan loader (libvulkan.so.1) beside libc.
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        zf.extract("speech", staging)
    (staging / "speech").chmod(0o755)
    staging.rename(SPEECH_DIR)
    return executable


def install(torch_backend: str | None = None, force: bool = False) -> bool:
    """The environment (no packages: the worker is stdlib only), then
    speech.cpp."""
    from remanga.tool_envs import build_env

    if not build_env(TOOL, torch_backend, force=force):
        return False
    ensure_speech()
    return True


def weights(config) -> None:
    """The model file, fetched by speech.cpp."""
    from remanga.plugins.drama3.synth import model_manager

    model_manager(config.tts.drama3).ensure_model()


if __name__ == "__main__":
    from remanga.tool_envs.cli import run_setup

    raise SystemExit(run_setup(TOOL))
