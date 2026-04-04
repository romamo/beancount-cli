import json
import sys
from pathlib import Path

import agentyper as typer

from beancount_cli.commands.common import (
    _is_table_format,
    console,
    get_ledger_file,
    read_json_input,
)
from beancount_cli.services import CommodityService

app = typer.Agentyper(help="Manage commodities.")


@app.command(name="list")
def commodity_list(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    asset_class: str | None = typer.Option(
        None, "--asset-class", "-c", help="Filter by asset-class meta (e.g. stock, Cash)"
    ),
):
    """List all commodities."""
    actual_file = get_ledger_file(ledger_file or file)
    service = CommodityService(actual_file)
    commodities = service.list_commodities(asset_class=asset_class)

    if _is_table_format():
        data = [
            {
                "Currency": c.currency,
                "Date": str(c.date) if c.date else "",
                "Name": c.meta.get("name", "") if c.meta else "",
            }
            for c in commodities
        ]
        typer.output(data, title=f"Commodities ({len(commodities)})")
    else:
        typer.output(commodities, title=f"Commodities ({len(commodities)})")


@app.command(name="check")
def commodity_check(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
):
    """Check for currencies used in transactions but missing a commodity directive."""
    actual_file = get_ledger_file(ledger_file or file)
    service = CommodityService(actual_file)
    undeclared = service.get_undeclared_commodities()

    if _is_table_format():
        if not undeclared:
            console.print("[green]All used currencies are declared.[/green]")
        else:
            typer.output(undeclared, title=f"Undeclared Commodities ({len(undeclared)})")
    else:
        typer.output(undeclared, title="Undeclared Commodities")


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
        data_input = json.loads(read_json_input(json_data))
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
