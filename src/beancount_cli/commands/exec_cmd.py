import contextlib
import io
import json
import sys
from pathlib import Path

import agentyper as typer

from beancount_cli.commands.common import error_console, get_ledger_file, iter_jsonl


def _opts_to_args(opts: dict) -> list[str]:
    """Convert {'draft': True, 'target': 'inbox.bc'} -> ['--draft', '--target', 'inbox.bc']."""
    args: list[str] = []
    for key, val in opts.items():
        flag = "--" + key.replace("_", "-")
        if isinstance(val, bool):
            if val:
                args.append(flag)
        else:
            args.append(flag)
            args.append(str(val))
    return args


def _invoke(cmd_args: list[str], payload: dict, opts: dict, ledger_file: Path | None) -> tuple[str, str, int]:
    # Lazy import avoids circular dependency (cli.py imports exec_cmd).
    from beancount_cli.cli import main

    args = list(cmd_args)
    if ledger_file:
        args += ["--file", str(ledger_file)]
    args += _opts_to_args(opts)
    if payload:
        args += ["--input", json.dumps(payload)]

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code = 0
    try:
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            main(args)
    except SystemExit as e:
        exit_code = int(e.code) if e.code is not None else 0
    return stdout_buf.getvalue(), stderr_buf.getvalue(), exit_code


def exec_cmd(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    ignore_errors: bool = typer.Option(
        False, "--ignore-errors", help="Continue processing after errors (default: stop on first)"
    ),
    dry_run: bool = False,
):
    """Execute a JSONL command stream from stdin.

    Each line: {"_cmd": "transaction.add", "_opts": {"draft": true}, ...payload...}
    '_cmd' maps to any CLI subcommand; '_opts' injects CLI flags.
    Use --dry-run to preview without writing.
    """
    ledger_file = get_ledger_file(file)
    extra_opts: dict = {"dry_run": True} if dry_run else {}
    parse_errors: list = []
    had_error = False
    for lineno, cmd, rest, opts in iter_jsonl(ignore_errors, parse_errors):
        stdout_out, stderr_out, exit_code = _invoke(cmd.split(".", 1), rest, opts | extra_opts, ledger_file)
        if stderr_out:
            sys.stderr.write(stderr_out)
            sys.stderr.flush()
        if stdout_out:
            sys.stdout.write(stdout_out)
            sys.stdout.flush()
        if exit_code != 0:
            error_console.print(f"[red]line {lineno} ({cmd}): exit {exit_code}[/red]")
            had_error = True
            if not ignore_errors:
                sys.exit(exit_code)
    if had_error or parse_errors:
        sys.exit(typer.EXIT_VALIDATION)
