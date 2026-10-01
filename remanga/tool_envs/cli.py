"""Every isolated tool environment remanga provisions, and how.

`python -m remanga.tool_envs install` provisions them - what bootstrap.sh
runs - and `list` shows each one's state. The first line above doubles as
--help's description."""

from __future__ import annotations

import argparse
import shutil

from remanga.tool_envs.install import provision, say, warn
from remanga.tool_envs.status import orphan_envs, status_rows


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m remanga.tool_envs", description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("install", "list"), nargs="?", default="install")
    parser.add_argument("--tool", action="append", default=[],
                        help="only this tool (repeatable); default is every tool")
    parser.add_argument("--torch-backend", default=None,
                        help="wheel index for torch-ecosystem installs (cu129, rocm6.4, cpu, default)")
    parser.add_argument("--force", action="store_true", help="rebuild the environment from scratch")
    parser.add_argument("--prune", action="store_true",
                        help="delete .tools/venv-* directories no tool claims any more")
    args = parser.parse_args()

    if args.action == "list":
        for name, display, state in status_rows():
            print(f"{name:14} {display:20} {state}")
        for path in orphan_envs():
            print(f"{path.name:14} {'(no such tool)':20} orphaned - delete it with --prune")
        return 0

    failed = provision(args.tool or None, args.torch_backend, force=args.force)

    for path in orphan_envs():
        if args.prune:
            say(f"removing {path} - no tool claims it any more")
            shutil.rmtree(path, ignore_errors=True)
        else:
            say(f"{path} belongs to no tool any more - `--prune` deletes it")

    if failed:
        warn(f"tool environment(s) that failed: {', '.join(failed)}")
        return 1
    return 0


def run_setup(spec) -> int:
    """`python -m remanga.plugins.<name>.setup`: one tool plug-in's setup on
    its own - its environment, then its weights."""
    parser = argparse.ArgumentParser(description=f"Set up {spec.display_name}: its environment and its weights")
    parser.add_argument("--torch-backend", default=None, help="wheel index (cu129, rocm6.4, cpu, default)")
    parser.add_argument("--force", action="store_true", help="rebuild the environment from scratch")
    parser.add_argument("--no-weights", action="store_true", help="only the environment")
    args = parser.parse_args()
    from remanga.tool_envs.install import install_tool, venv_python

    if not install_tool(spec, args.torch_backend, force=args.force) or not venv_python(spec.venv_dir):
        warn(f"{spec.display_name}'s environment did not install")
        return 1
    if spec.weights and not args.no_weights:
        from remanga import plugins
        from remanga.config import RemangaConfig

        plugins.call(spec.weights, RemangaConfig.load())
    say(f"{spec.display_name} is set up.")
    return 0
