"""Shared command dispatcher for the consolidated workflow entry points."""

from __future__ import annotations

import argparse
import importlib
import sys
from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Command:
    module: str
    description: str
    apply_required: bool = False
    accepts_arguments: bool = True


def dispatch(
    description: str,
    commands: dict[str, Command],
    argv: Sequence[str] | None = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(
            f"  {name:<18} {command.description}"
            for name, command in commands.items()
        ),
    )
    parser.add_argument("command", choices=commands)
    arguments = list(argv) if argv is not None else sys.argv[1:]
    if not arguments or arguments[0] in {"-h", "--help"}:
        parser.print_help()
        return 0
    command_name, remainder = arguments[0], arguments[1:]
    if command_name not in commands:
        parser.error(f"invalid command: {command_name!r}")
    command = commands[command_name]
    requesting_help = any(value in {"-h", "--help"} for value in remainder)

    if requesting_help and not command.accepts_arguments:
        print(f"{command_name}: {command.description}")
        if command.apply_required:
            print("This command writes reviewed data and requires --apply.")
        return 0

    if command.apply_required and not requesting_help:
        if "--apply" not in remainder:
            parser.error(f"{command_name} writes reviewed data; add --apply to continue")
        remainder = [value for value in remainder if value != "--apply"]

    if not command.accepts_arguments and remainder:
        parser.error(f"{command_name} does not accept arguments: {remainder}")

    module = importlib.import_module(command.module)
    previous_argv = sys.argv
    try:
        sys.argv = [f"{parser.prog} {command_name}", *remainder]
        result = module.main()
    finally:
        sys.argv = previous_argv
    return result if isinstance(result, int) else 0
