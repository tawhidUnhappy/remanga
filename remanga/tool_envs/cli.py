"""Every isolated tool environment remanga provisions, and how.

`python -m remanga.tool_envs install` provisions them - what bootstrap.sh
runs - and `list` shows each one's state. The first line above doubles as
--help's description."""

from __future__ import annotations

import argparse
import shutil

from remanga.tool_envs.install import orphan_envs, provision, say, status_rows, warn


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
