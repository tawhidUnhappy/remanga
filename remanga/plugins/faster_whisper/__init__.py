"""faster-whisper: reads word timings back off narrated audio - how a batched
narration finds each panel in its take, and what a cloned voice's reference
recording says. Runs in .tools/venv-faster-whisper.

    transcribe.py   the Transcriber (worker driver)
    scripts/        the worker and the weight download"""

from remanga.plugins import register
from remanga.tool_envs.spec import InstallStep, ToolSpec

register("tool", ToolSpec(
    "faster-whisper", "faster-whisper", "word timestamps for a batched narration",
    steps=(
        # CTranslate2, not torch, so this machine's wheel index has no
        # business here - hence torch_backend=False, the only entry that
        # sets it on its first step.
        #
        # The two NVIDIA runtime libraries are named because ctranslate2
        # dlopens cuDNN and cuBLAS at run time and does not declare them
        # as dependencies: without them the model loads and then dies on
        # "Unable to load libcudnn_ops.so" the first time it is asked for
        # anything, which reads as a model problem and is not one.
        InstallStep(("faster-whisper", "nvidia-cublas-cu12", "nvidia-cudnn-cu12"),
                    torch_backend=False),
    ),
))
