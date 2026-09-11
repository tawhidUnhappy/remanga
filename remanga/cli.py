"""The `remanga` command line: every registered command as a subcommand, and
the interactive wizard when no command is given.

Exit status follows the shell's conventions, so remanga composes in scripts
the way any other command does: 0 when the run finished or you chose to
quit, 1 when it failed, 130 when Ctrl+C stopped it - a chain like
`remanga download-all -p x && remanga crop-all -p x` stops when you stop it
instead of reading the interrupted half as a success. The error or
interruption itself goes to stderr, so it reaches the terminal even when
stdout is redirected."""

from __future__ import annotations

import argparse
import difflib
import sys
from importlib.metadata import PackageNotFoundError, version

from remanga.commands import COMMAND_BY_NAME, add_param_to_parser, commands_by_category, params_from_namespace
from remanga.config import RemangaConfig
from remanga.console import console, err_console, escape as _esc
from remanga.tui import PromptExit
from remanga.wizard import run_interactive_pipeline

PAUSED_MESSAGE = "[bold yellow]👋 Production paused. You can resume at any time![/]"
# 128 + SIGINT: what a shell reports for a command stopped by Ctrl+C.
EXIT_INTERRUPTED = 130
_INTERACTIVE_HELP = "Start the interactive wizard (the default when no command is given)"


def _version() -> str:
    try:
        return version("remanga")
    except PackageNotFoundError:
        return "unknown"


def _command_overview() -> str:
    """Every command, grouped the way the wizard's menus group them, one
    line each - the listing `remanga --help` ends with. Built from the
    registry like everything else, so the help can't list a command the
    wizard doesn't have, or file it under a different heading."""
    groups = commands_by_category()
    width = max(len(cmd.name) for cmds in groups.values() for cmd in cmds) + 2
    lines = ["commands:", f"  {'interactive'.ljust(width)}{_INTERACTIVE_HELP}"]
    for category, cmds in groups.items():
        lines.append(f"\n  {category.name} - {category.description}")
        lines.extend(f"    {cmd.name.ljust(width)}{cmd.summary}" for cmd in cmds)
    lines.append("\nrun `remanga <command> --help` for a command's options")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """One subparser per registered command. Each one's full help text is its
    own --help description; the top-level help lists them all by category
    instead of argparse's flat, unreadable `{a,b,c,...}` of thirty names."""
    parser = argparse.ArgumentParser(
        prog="remanga",
        description="Manga-to-recap-video production pipeline. With no command, starts the "
                    "interactive wizard.",
        epilog=_command_overview(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"remanga {_version()}")
    subparsers = parser.add_subparsers(dest="command", metavar="<command>",
                                       help="one of the commands listed below")
    subparsers.add_parser("interactive", description=_INTERACTIVE_HELP)
    for cmd in COMMAND_BY_NAME.values():
        sub = subparsers.add_parser(cmd.name, description=cmd.help)
        for param in cmd.params:
            add_param_to_parser(sub, param)
    return parser


def _reject_unknown_command(parser: argparse.ArgumentParser, argv: list[str]) -> None:
    """A mistyped command gets its nearest match suggested, rather than
    argparse's list of every command there is."""
    if not argv or argv[0].startswith("-") or argv[0] == "interactive" or argv[0] in COMMAND_BY_NAME:
        return
    close = difflib.get_close_matches(argv[0], [*COMMAND_BY_NAME, "interactive"], n=1)
    hint = f" - did you mean '{close[0]}'?" if close else " - see `remanga --help`"
    parser.error(f"unknown command '{argv[0]}'{hint}")


def main() -> None:
    parser = build_parser()
    _reject_unknown_command(parser, sys.argv[1:])
    args = parser.parse_args()
    try:
        if args.command in ("interactive", None):
            run_interactive_pipeline()
            return
        cmd = COMMAND_BY_NAME[args.command]
        params = params_from_namespace(cmd, args)
        # Every command that names a project runs on that project's
        # settings - its voice, its music, its resolution - falling back to
        # config.json for everything it hasn't overridden. A command with no
        # project (setup-config, paths, setup-models) edits the machine's
        # own configuration.
        config = RemangaConfig.load()
        project = params.get("project")
        cmd.handler(params, config.for_project(project) if project else config)
    except PromptExit:
        # The Exit row / ctrl+q, from any prompt at any depth (see
        # remanga.tui.result.PromptExit). Not an error - the user asked to
        # leave.
        console.print("\n[dim]Bye.[/]")
    except KeyboardInterrupt:
        # Ctrl+C anywhere: raised by Python itself in normal terminal mode,
        # and by remanga.tui.loop from inside a menu (which reads Ctrl+C as a
        # key), with the terminal already restored either way. Worker
        # processes are shut down by their own atexit hooks on the way out.
        err_console.print("\n" + PAUSED_MESSAGE)
        sys.exit(EXIT_INTERRUPTED)
    except EOFError:
        # A scripted/non-tty run whose piped input ran out mid-prompt. Said
        # plainly instead of surfacing readline's "EOF when reading a line".
        err_console.print("\n[yellow]Input ended before the prompt was answered - stopping here.[/]")
        sys.exit(1)
    except Exception as error:
        err_console.print(f"[bold red]Error:[/] {_esc(str(error))}")
        sys.exit(1)


if __name__ == "__main__":
    main()
