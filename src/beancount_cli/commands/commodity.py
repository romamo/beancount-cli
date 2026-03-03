import json
import sys
from pathlib import Path

import agentyper as typer

from beancount_cli.commands.common import console, get_ledger_file
from beancount_cli.services import CommodityService

app = typer.Agentyper(help="Manage commodities.")


@app.command(name="create")
def commodity_create(
    currency: str | None = typer.Argument(None, help="Currency code (e.g. USD)"),
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    name: str | None = typer.Option(None, "--name", "-n", help="Full name"),
    json_data: str | None = typer.Option(
        None, "--json", "-j", help="JSON string data (or '-' to read from STDIN)"
    ),
):
    """Create a new commodity."""
    actual_file = get_ledger_file(ledger_file or file)
    service = CommodityService(actual_file)

    if json_data:
        if json_data == "-":
            content = sys.stdin.read()
        else:
            content = json_data

        data_input = json.loads(content)
        items = data_input if isinstance(data_input, list) else [data_input]
        for item in items:
            curr = item.get("currency")
            comm_name = item.get("name")
            if not curr:
                console.print(f"[yellow]Skipping invalid commodity entry: {item}[/yellow]")
                continue
            service.create_commodity(curr, name=comm_name)
            console.print(f"[green]Commodity {curr} created.[/green]")
    else:
        if not currency:
            console.print("[red]Error: currency argument is required if not using --json.[/red]")
            sys.exit(typer.EXIT_VALIDATION)
        service.create_commodity(currency, name=name)
        console.print(f"[green]Commodity {currency} created.[/green]")
