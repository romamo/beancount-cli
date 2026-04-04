import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import gettempdir

import agentyper as typer
from beancount.core import data
from beancount.parser import printer
from beanprice import price as bp_price

from beancount_cli.commands.common import _is_table_format, error_console, get_ledger_file
from beancount_cli.services import LedgerService, MapService, PriceService

app = typer.Agentyper(help="Manage prices.")


@app.command(name="check")
def price_check(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    tolerance: int = typer.Option(
        7, "--tolerance", "-t", help="Allowed delay in days before flagging a gap"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Verbosity level (-v for INFO, -vv for DEBUG)"
    ),
    rate: str = typer.Option(
        "daily", "--rate", "-r", help="Check frequency: daily, weekday, weekly, monthly"
    ),
):
    """Check for missing price data in the ledger."""
    actual_file = get_ledger_file(ledger_file or file)
    ledger_service = LedgerService(actual_file)
    price_service = PriceService(ledger_service)

    _setup_logging(verbose)
    _warn_missing_price_meta(ledger_service, "Price history cannot be verified.")

    gaps = price_service.get_price_gaps(tolerance_days=tolerance, rate=rate)

    if _is_table_format():
        if not gaps:
            typer.echo("No price gaps found.")
        else:
            gaps_data = [
                {
                    "Currency": g.currency,
                    "Target": g.target_currency,
                    "Gap Date": str(g.gap_start),
                    "Last Date": str(g.last_available_date) if g.last_available_date else "None",
                    "Days Out": g.days_missing,
                }
                for g in gaps
            ]
            typer.output(gaps_data, title=f"Price Gaps ({len(gaps)})")
    else:
        typer.output(gaps, title="Price Gaps")


@app.command(name="fetch")
def price_fetch(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    update: bool = typer.Option(
        False, "--update", "-u", help="Fetch from last price forward and update ledger"
    ),
    inactive: bool = typer.Option(
        False, "--inactive", "-i", help="Include commodities with no balance"
    ),
    fill_gaps: bool = typer.Option(False, "--fill-gaps", help="Fill gaps in price history"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Don't actually fetch, just print"),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Verbosity level (-v for INFO, -vv for DEBUG)"
    ),
):
    """Fetch and update prices using bean-price library."""
    actual_file = get_ledger_file(ledger_file or file)
    error_console.print(f"Fetching prices for {actual_file}...")

    _setup_logging(verbose)

    try:
        cache_path = Path(gettempdir()) / "bean-price.cache"
        bp_price.setup_cache(str(cache_path), clear_cache=False)

        ledger_service = LedgerService(actual_file)
        ledger_service.load()
        entries = ledger_service.entries

        _warn_missing_price_meta(ledger_service, "Skipping fetch.")

        if update or fill_gaps:
            jobs = bp_price.get_price_jobs_up_to_date(
                entries,
                date_last=datetime.now().date(),
                inactive=inactive,
                fill_gaps=fill_gaps,
            )
        else:
            jobs = bp_price.get_price_jobs_at_date(entries, date=None, inactive=inactive)

        if not jobs:
            error_console.print("[yellow]No price jobs to execute.[/yellow]")
            return

        if dry_run:
            error_console.print(f"[blue]Dry run: {len(jobs)} jobs generated.[/blue]")
            for job in jobs:
                error_console.print(f"  {bp_price.format_dated_price_str(job)}")
            return

        new_price_entries = []
        # Build a set of existing (date, currency) for fast redundancy check
        # This keeps the streaming output clean of duplicates already in the ledger
        existing_prices = {(e.date, e.currency) for e in entries if isinstance(e, data.Price)}

        try:
            with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as executor:
                future_to_job = {executor.submit(bp_price.fetch_price, job): job for job in jobs}

                for future in as_completed(future_to_job):
                    price_entry = future.result()
                    if price_entry:
                        price_entry = price_entry._replace(
                            amount=price_entry.amount._replace(
                                number=price_entry.amount.number.quantize(Decimal("1.000000"))
                            )
                        )

                        if (price_entry.date, price_entry.currency) not in existing_prices:
                            new_price_entries.append(price_entry)
                            existing_prices.add((price_entry.date, price_entry.currency))
                            print(printer.format_entry(price_entry), end="")
                            sys.stdout.flush()
        except KeyboardInterrupt:
            error_console.print("\n[yellow]Interrupt received. Stopping fetch...[/yellow]")

        if update and not dry_run and new_price_entries:
            filtered_prices, _ = bp_price.filter_redundant_prices(new_price_entries, entries)

            if not filtered_prices:
                error_console.print(
                    "[yellow]All fetched prices are already in the ledger.[/yellow]"
                )
                return

            prices_output = "".join(printer.format_entry(p) for p in filtered_prices)

            map_service = MapService(actual_file)
            inc_tree = map_service.get_include_tree()
            target_price_file = actual_file

            # Prioritize standard names
            sibling_prices = actual_file.parent / "prices.beancount"
            if sibling_prices.exists():
                target_price_file = sibling_prices
            else:
                found = _find_price_file(inc_tree)
                if found:
                    target_price_file = found

            with open(target_price_file, "a") as f:
                f.write(prices_output)

            error_console.print(
                f"[green]Appended {len(filtered_prices)} new prices to {target_price_file.name}[/green]"
            )
        elif not new_price_entries:
            error_console.print("[yellow]No new prices found.[/yellow]")

    except Exception as e:
        error_console.print(f"[red]Error fetching prices: {e}[/red]")
        sys.exit(typer.EXIT_SYSTEM)


def _find_price_file(tree: dict) -> Path | None:
    """Search an include tree for a beancount file with 'price' in its name or parent directory."""
    for k, v in tree.items():
        path_obj = Path(k)
        if "price" in path_obj.name.lower() or "price" in path_obj.parent.name.lower():
            if k.endswith(".beancount"):
                return path_obj
        found = _find_price_file(v)
        if found:
            return found
    return None


def _warn_missing_price_meta(ledger_service: LedgerService, context: str) -> None:
    """Warn about held commodities that lack 'price' metadata and cannot be priced."""
    held = ledger_service.get_inventory(date.today())
    op_currs = set(ledger_service.get_operating_currencies()) or {"USD"}
    commodity_meta = {
        e.currency: e.meta for e in ledger_service.entries if isinstance(e, data.Commodity)
    }
    for curr in sorted(held):
        if curr in op_currs:
            continue
        meta = commodity_meta.get(curr, {})
        if not meta or "price" not in meta:
            error_console.print(
                f"[red]Error: Commodity {curr} is held but has no 'price' metadata. {context}[/red]"
            )


def _setup_logging(verbose: bool):
    """Sets up logging levels based on verbosity count in sys.argv."""
    # Manual count of 'v' flags in sys.argv to handle -v, -vv, etc.
    count = 0
    for arg in sys.argv:
        if arg == "-v":
            count += 1
        elif arg.startswith("-") and not arg.startswith("--"):
            # Handle combined flags like -uvv
            count += arg.count("v")
        elif arg == "--verbose":
            count += 1

    if count >= 2:
        log_level = logging.DEBUG
    elif count == 1 or verbose:
        log_level = logging.INFO
    else:
        log_level = logging.WARNING

    logging.basicConfig(level=log_level, format="%(levelname)-8s: %(message)s", force=True)

    # Silence noisy loggers unless -vv is used
    if count < 2:
        for logger_name in ["yfinance", "urllib3", "requests", "diskcache"]:
            logging.getLogger(logger_name).setLevel(logging.WARNING)
