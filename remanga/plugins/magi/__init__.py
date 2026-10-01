"""MAGI v3: finds the panels on a printed page for the Panel Marker (the
"pages" layout's detector). Runs in .tools/venv-magi.

    assist.py   the worker driver and weight download
    scripts/    the worker and the download, run in that environment"""

from remanga.plugins import register
from remanga.tool_envs.spec import InstallStep, ToolSpec

register("tool", ToolSpec(
    "magi", "MAGI v3", "panel detection for the Panel Marker web UI",
    steps=(
        # einops/matplotlib: undeclared imports MAGI v3's remote modeling
        # code needs beyond its own requirements. assist.py auto-installs
        # anything still missing on first load; listing the known ones saves
        # a round trip.
        InstallStep((
            "torch", "transformers<4.52.0", "timm", "shapely",
            "pytorch-metric-learning", "huggingface-hub", "pillow", "numpy",
            "einops", "matplotlib",
        )),
    ),
))
