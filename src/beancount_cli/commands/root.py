import json
import subprocess  # nosec B404
import sys
from pathlib import Path

import agentyper as typer
from rich.tree import Tree

from beancount_cli.commands.common import _is_table_format, console, get_ledger_file
from beancount_cli.services import LedgerService, MapService


def check(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
):
    """Validate the ledger file."""
    actual_file = get_ledger_file(ledger_file or file)
    format_ = "table" if _is_table_format() else "json"

    try:
        service = LedgerService(actual_file)
        service.load()
    except FileNotFoundError as exc:
        typer.exit_error(
            str(exc), code=typer.EXIT_SYSTEM, error_type="FileNotFoundError", format_=format_
        )
    except OSError as exc:
        typer.exit_error(str(exc), code=typer.EXIT_SYSTEM, error_type="OSError", format_=format_)

    if not service.errors:
        console.print("[green]No errors found.[/green]")
        return

    if format_ == "json":
        payload = {
            "error": True,
            "error_type": "BeancountValidationError",
            "exit_code": typer.EXIT_VALIDATION,
            "errors": [
                {
                    "location": f"{e.source['filename']}:{e.source['lineno']}"
                    if e.source
                    else None,
                    "message": e.message,
                }
                for e in service.errors
            ],
        }
        print(json.dumps(payload), file=sys.stderr)
    else:
        for error in service.errors:
            source = error.source
            loc = f"{source['filename']}:{source['lineno']}" if source else "?"
            console.print(f"[red]{loc}: {error.message}[/red]")
    raise SystemExit(typer.EXIT_VALIDATION)


def tree(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
):
    """Visualize the tree of included files."""
    actual_file = get_ledger_file(ledger_file or file)
    service = MapService(actual_file)
    tree_dict = service.get_include_tree()

    def build_tree(data: dict, tree_node: Tree):
        for path, children in data.items():
            node = tree_node.add(f"[yellow]{path}[/yellow]")
            build_tree(children, node)

    root = Tree(f"[bold blue]{actual_file}[/bold blue]")
    build_tree(tree_dict, root)
    if _is_table_format():
        console.print(root)
    else:
        typer.output(tree_dict, title="File Tree")


def format_cmd(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Format all included files"),
):
    """Format ledger file(s)."""
    actual_file = get_ledger_file(ledger_file or file)
    try:
        import shutil
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        cmd = ["bean-format", "-c", "50", "-o", str(tmp_path), str(actual_file)]
        subprocess.run(cmd, check=True, capture_output=True, text=True)  # nosec B603

        shutil.move(str(tmp_path), str(actual_file))
        console.print(f"[green]Formatted {actual_file}[/green]")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error running bean-format: {e.stderr}[/red]")
        sys.exit(typer.EXIT_SYSTEM)
