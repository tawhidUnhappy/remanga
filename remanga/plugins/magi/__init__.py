"""MAGI v3: finds the panels on a printed page for the Panel Marker (the
"pages" layout's detector). Runs in .tools/venv-magi.

    assist.py   the worker driver and weight download
    scripts/    the worker and the download, run in that environment
    setup.py    its environment and weights - runs on its own too"""

from remanga.plugins import register
from remanga.plugins.magi.setup import TOOL

register("tool", TOOL)   # setup.py: its environment and weights
