from __future__ import annotations

import argparse
import signal
import sys

from remanga.commands import COMMAND_BY_NAME, COMMAND_REGISTRY, add_param_to_parser, params_from_namespace
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.wizard import run_interactive_pipeline


def graceful_sigint_handler(signum, frame):
    """Handle Ctrl+C gracefully without traceback noise."""
    console.print("\n\n[bold yellow]👋 Production paused. You can resume at any time![/]")
    sys.exit(0)


signal.signal(signal.SIGINT, graceful_sigint_handler)


def main():
    parser = argparse.ArgumentParser(description="remanga: Lightweight, Self-Contained Manga Recap Production Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    # interactive wizard - the one subcommand not driven by COMMAND_REGISTRY
    # (it's the thing that displays a menu built from that registry).
    subparsers.add_parser("interactive", help="Start interactive step-by-step production wizard")

    # Every other subcommand's argparse declaration comes straight from
    # COMMAND_REGISTRY - one loop instead of one hand-written add_parser/
    # add_argument block per command, so cli.py and wizard.py can never drift
    # out of sync with each other again.
    for cmd in COMMAND_REGISTRY:
        p = subparsers.add_parser(cmd.name, help=cmd.help)
        for param in cmd.params:
            add_param_to_parser(p, param)

    args = parser.parse_args()
    config = RemangaConfig.load()

    try:
        if args.command in ("interactive", None):
            run_interactive_pipeline()
        else:
            cmd = COMMAND_BY_NAME.get(args.command)
            if cmd is None:
                parser.error(f"unknown command: {args.command}")
                return
            cmd.handler(params_from_namespace(cmd, args), config)
    except Exception as e:
        console.print(f"[bold red]Error:[/] {_esc(str(e))}")
        sys.exit(1)


if __name__ == "__main__":
    main()
