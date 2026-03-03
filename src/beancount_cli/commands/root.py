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
    service = LedgerService(actual_file)
    service.load()

    if not service.errors:
        console.print("[green]No errors found.[/green]")
    else:
        for error in service.errors:
            source = error.source
            loc = f"{source['filename']}:{source['lineno']}" if source else "?"
            console.print(f"[red]{loc}: {error.message}[/red]")
        sys.exit(typer.EXIT_VALIDATION)


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


def price(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    update: bool = typer.Option(False, "--update", "-u", help="Update prices in ledger"),
):
    """Fetch and update prices."""
    actual_file = get_ledger_file(ledger_file or file)
    console.print(f"Fetching prices for {actual_file}...")

    try:
        cmd = ["bean-price", str(actual_file)]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)  # nosec B603
        prices_output = result.stdout.strip()

        if not prices_output:
            console.print("[yellow]No new prices found.[/yellow]")
            return

        if update:
            service = MapService(actual_file)
            inc_tree = service.get_include_tree()
            target_price_file = actual_file

            def find_price_file(t):
                for k, v in t.items():
                    if "price" in Path(k).name.lower() and "beancount" in k:
                        return Path(k)
                    res = find_price_file(v)
                    if res:
                        return res
                return None

            found = find_price_file(inc_tree)
            if found:
                target_price_file = found

            from datetime import datetime

            with open(target_price_file, "a") as f:
                f.write(f"\n\n; Prices fetched {datetime.now().isoformat()}\n")
                f.write(prices_output)
                f.write("\n")

            console.print(
                f"[green]Appended {len(prices_output.splitlines())} prices to {target_price_file.name}[/green]"
            )
        else:
            console.print(prices_output)

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error running bean-price: {e.stderr}[/red]")
        sys.exit(typer.EXIT_SYSTEM)
    except FileNotFoundError:
        console.print("[red]Error: bean-price not found. Is it installed?[/red]")
        sys.exit(typer.EXIT_SYSTEM)
