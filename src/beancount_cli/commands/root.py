import json
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path

import agentyper as typer
from rich.markup import escape
from rich.tree import Tree

from beancount_cli.commands.common import _is_table_format, console, emit, get_ledger_file
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
        if format_ == "table":
            console.print("[green]No errors found.[/green]")
            return None
        return {"file": str(actual_file), "valid": True, "errors": []}

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
        typer.output({str(actual_file): tree_dict}, title="File Tree")


def format_cmd(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    recursive: bool = typer.Option(False, "--recursive", "-r", help="Format all included files"),
    dry_run: bool = False,
):
    """Format ledger file(s)."""
    actual_file = get_ledger_file(ledger_file or file)
    if not actual_file.is_file():
        typer.exit_error(
            f"Ledger file not found: {actual_file}",
            code=typer.EXIT_SYSTEM,
            error_type="FileNotFoundError",
            field="file",
        )
    if shutil.which("bean-format") is None:
        typer.exit_error(
            "bean-format is not on PATH",
            code=typer.EXIT_SYSTEM,
            error_type="DependencyMissing",
            hint="Install beancount, which provides bean-format, into the active environment",
        )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".beancount", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        cmd = ["bean-format", "-c", "50", "-o", str(tmp_path), str(actual_file)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)  # nosec B603
        except subprocess.CalledProcessError as e:
            typer.exit_error(
                f"bean-format failed: {e.stderr.strip()}",
                code=typer.EXIT_SYSTEM,
                error_type="FormatError",
            )
        formatted = tmp_path.read_text()
    finally:
        tmp_path.unlink(missing_ok=True)

    changed = formatted != actual_file.read_text()
    if changed and not dry_run:
        actual_file.write_text(formatted)

    if not changed:
        effect, human = "noop", f"[green]{escape(str(actual_file))} is already formatted.[/green]"
    elif dry_run:
        effect, human = "would_update", f"[yellow]Would format {escape(str(actual_file))}.[/yellow]"
    else:
        effect, human = "updated", f"[green]Formatted {escape(str(actual_file))}[/green]"
    return emit({"file": str(actual_file), "changed": changed}, effect=effect, human=human)
