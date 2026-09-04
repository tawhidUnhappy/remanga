from __future__ import annotations

import argparse
import signal
import sys

from remanga.commands import COMMAND_BY_NAME, COMMAND_REGISTRY, add_param_to_parser, params_from_namespace
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.wizard import run_interactive_pipeline


PAUSED_MESSAGE = "\n[bold yellow]👋 Production paused. You can resume at any time![/]"


def graceful_sigint_handler(signum, frame):
    """Handle Ctrl+C gracefully without traceback noise.

    This covers Ctrl+C anywhere the terminal is in its normal mode. While an
    interactive menu is open the terminal has SIGINT delivery turned off (so
    a keypress can't tear down a half-drawn screen - see remanga/tui/keys.py),
    and Ctrl+C arrives as a KeyboardInterrupt instead, handled in main()
    below. Both paths print the same thing."""
    console.print("\n" + PAUSED_MESSAGE)
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
    # add_argument block per command, so the CLI and the wizard can never
    # drift out of sync with each other.
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
    except KeyboardInterrupt:
        # Raised out of an interactive menu (see the note on
        # graceful_sigint_handler above), with the terminal already restored.
        console.print(PAUSED_MESSAGE)
        sys.exit(0)
    except Exception as e:
        console.print(f"[bold red]Error:[/] {_esc(str(e))}")
        sys.exit(1)


if __name__ == "__main__":
    main()
