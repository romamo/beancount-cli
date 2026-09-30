import logging
import sys
from datetime import date
from pathlib import Path

import agentyper as typer
from beancount.core import data
from beancount.parser import parser as bp_parser
from beancount.parser import printer
from rich.markup import escape

from beancount_cli.commands.common import (
    _is_table_format,
    console,
    emit,
    error_console,
    get_ledger_file,
    read_stdin,
)
from beancount_cli.models import CommodityModel
from beancount_cli.services import CommodityService

app = typer.Agentyper(help="Manage commodities.")


@app.command(name="list")
def commodity_list(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    asset_class: str | None = typer.Option(
        None, "--asset-class", "-c", help="Filter by asset-class meta (e.g. stock, Cash)"
    ),
):
    """List all commodities."""
    actual_file = get_ledger_file(file)
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
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
):
    """Check for currencies used in transactions but missing a commodity directive."""
    actual_file = get_ledger_file(file)
    service = CommodityService(actual_file)
    undeclared = service.get_undeclared_commodities()

    if _is_table_format():
        if not undeclared:
            console.print("[green]All used currencies are declared.[/green]")
        else:
            typer.output(undeclared, title=f"Undeclared Commodities ({len(undeclared)})")
    else:
        typer.output(undeclared, title="Undeclared Commodities")


@app.command(name="export")
def commodity_export(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    asset_class: str | None = typer.Option(
        None, "--asset-class", "-c", help="Filter by asset-class meta (e.g. stock, Cash)"
    ),
    output_file: Path | None = typer.Option(
        None, "--output-file", help="Write output to file (default: commodities_file or stdout)"
    ),
):
    """Export commodities as beancount directives."""
    actual_file = get_ledger_file(file)
    service = CommodityService(actual_file)
    commodities = service.list_commodities(asset_class=asset_class)

    content = "\n".join(service._format_commodity_block(c) for c in commodities)

    dest = output_file or service.ledger_service.get_commodities_file()
    if dest:
        dest.write_text(content)
        console.print(f"[green]Exported {len(commodities)} commodities →[/green] {dest}")
    else:
        sys.stdout.write(content)


@app.command(name="import", mutating=True)
def commodity_import(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    input_file: Path | None = typer.Option(
        None, "--input-file", help="Read beancount directives from file instead of stdin"
    ),
    output_file: Path | None = typer.Option(
        None, "--output-file", help="Write to file (default: commodities_file from ledger config)"
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Overwrite existing commodities"),
    dry_run: bool = False,
):
    """Import commodity directives from stdin (or --input-file) into the commodities_file."""
    stdin_text = Path(input_file).read_text() if input_file else read_stdin()
    entries, errors, _ = bp_parser.parse_string(stdin_text)
    if errors:
        typer.exit_error(
            "Parse error: " + "; ".join(e.message for e in errors),
            error_type="ParseError",
            field="input",
        )

    commodities = [
        CommodityModel(currency=e.currency, date=e.date, meta=e.meta)
        for e in entries
        if isinstance(e, data.Commodity)
    ]
    if not commodities:
        return emit(
            {"results": [], "file": None, "entry": ""},
            effect="noop",
            human="[yellow]No commodity directives found in stdin.[/yellow]",
        )

    actual_file = get_ledger_file(file)
    service = CommodityService(actual_file)
    dest = output_file or service.ledger_service.get_commodities_file()

    results, commodities_file = service.import_commodities(
        commodities, output_file=dest, overwrite=overwrite, dry_run=dry_run
    )
    written = {r.currency for r in results if r.action != "skipped"}
    blocks = "".join(
        service._format_commodity_block(c) for c in commodities if str(c.currency) in written
    )

    if not _is_table_format():
        # Nothing reaches disk on a dry run or without a commodities_file (the
        # blocks are returned instead), so those report a would_* effect.
        applied = not dry_run and commodities_file is not None
        if any(r.action == "overwritten" for r in results):
            effect = "updated" if applied else "would_update"
        elif written:
            effect = "created" if applied else "would_create"
        else:
            effect = "noop"
        return typer.result(
            {
                "results": [r.model_dump(mode="json") for r in results],
                "file": str(commodities_file) if commodities_file else None,
                "entry": blocks,
            },
            effect=effect,
        )

    stdout_mode = not dry_run and commodities_file is None
    status_console = error_console if stdout_mode else console
    verbose = logging.getLogger().isEnabledFor(logging.INFO)
    prefix = "[dim](dry-run)[/dim] " if dry_run else ""
    for r in results:
        if not verbose and not dry_run and r.action == "skipped":
            continue
        color = {"added": "green", "overwritten": "yellow", "skipped": "dim"}.get(r.action, "white")
        status_console.print(f"{prefix}[{color}]{r.action:12}[/{color}] {r.currency}")

    if dry_run:
        return

    if commodities_file:
        console.print(f"\n[green]Done →[/green] {commodities_file}")
    else:
        # No destination configured — stream added/overwritten entries to stdout
        sys.stdout.write(blocks)


@app.command(name="create", mutating=True)
def commodity_create(
    currency: str = typer.Argument(..., help="Currency code (e.g. USD)"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    name: str | None = typer.Option(None, "--name", "-n", help="Full name"),
    dry_run: bool = False,
):
    """Create a new commodity."""
    meta = {"name": name} if name else {}
    entry = printer.format_entry(data.Commodity(meta=meta, date=date.today(), currency=currency))
    result = {"currency": currency, "meta": meta, "entry": entry}
    if dry_run:
        return emit({**result, "file": None}, effect="would_create", human=escape(entry))
    try:
        written = CommodityService(get_ledger_file(file)).create_commodity(currency, name=name)
    except ValueError as e:
        typer.exit_error(str(e))
    return emit(
        {**result, "file": str(written)},
        effect="created",
        human=f"[green]Commodity {escape(currency)} created in {escape(str(written))}.[/green]",
    )
