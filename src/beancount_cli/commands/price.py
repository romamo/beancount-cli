import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import gettempdir

import agentyper as typer
from beancount.core import data
from beancount.core.data import sorted as bean_sorted
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
    rate: str = typer.Option(
        "daily", "--rate", "-r", help="Check frequency: daily, weekday, weekly, monthly"
    ),
):
    """Check for missing price data in the ledger."""
    actual_file = get_ledger_file(ledger_file or file)
    ledger_service = LedgerService(actual_file)
    price_service = PriceService(ledger_service)

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


@app.command(name="fetch", mutating=True)
def price_fetch(
    ledger_files: list[Path] = typer.Argument(
        [],
        help="One or more beancount ledger files to merge before fetching prices",
    ),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file (legacy fallback)"
    ),
    update: bool = typer.Option(
        False, "--update", "-u", help="Fetch from last price forward and update ledger"
    ),
    inactive: bool = typer.Option(
        False, "--inactive", "-i", help="Include commodities with no balance"
    ),
    fill_gaps: bool = typer.Option(False, "--fill-gaps", help="Fill gaps in price history"),
    dry_run: bool = False,
):
    """Fetch and update prices using bean-price library.

    Accepts one or more beancount ledger files as positional arguments. When
    multiple files are provided they are all loaded and their entries merged
    before price jobs are computed. This lets you split commodities/prices
    across separate files (e.g. a common registry and a portfolio ledger) while
    still running a single fetch pass.

    If no positional arguments are given the command falls back to --file / the
    BEANCOUNT_FILE environment variable for backward compatibility.
    """
    # Resolve the list of ledger files to load.
    if ledger_files:
        files_to_load = ledger_files
    else:
        files_to_load = [get_ledger_file(file)]

    label = ", ".join(str(f) for f in files_to_load)
    error_console.print(f"Fetching prices for {label}...", highlight=False)

    try:
        cache_path = Path(gettempdir()) / "bean-price.cache"
        bp_price.setup_cache(str(cache_path), clear_cache=False)

        # Load and merge all ledger files
        all_entries: list[data.Directive] = []
        all_errors: list = []
        primary_ledger_service: LedgerService | None = None

        for ledger_path in files_to_load:
            svc = LedgerService(ledger_path)
            svc.load()
            all_entries.extend(svc.entries)
            all_errors.extend(svc.errors)
            if primary_ledger_service is None:
                primary_ledger_service = svc

        # Sort merged entries by date (beancount canonical order)
        entries = bean_sorted(all_entries)

        assert primary_ledger_service is not None  # always set — files_to_load is non-empty

        _warn_missing_price_meta_entries(entries, "Skipping fetch.")

        if update or fill_gaps:
            jobs = bp_price.get_price_jobs_up_to_date(
                entries,
                date_last=datetime.now().date(),
                inactive=inactive
            )
        else:
            jobs = bp_price.get_price_jobs_at_date(
                entries, date=None, inactive=inactive
            )

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

        failed_jobs = []
        redundant_count = 0
        try:
            with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as executor:
                future_to_job = {executor.submit(bp_price.fetch_price, job): job for job in jobs}

                for future in as_completed(future_to_job):
                    job = future_to_job[future]
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
                        else:
                            redundant_count += 1
                            logging.debug(
                                "Redundant: %s", printer.format_entry(price_entry).strip()
                            )
                    else:
                        failed_jobs.append(job)
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

            # Resolve target price file.
            # Strategy:
            # 1. Look for a file named 'prices.beancount' in the argument list itself.
            # 2. Look for a sibling named 'prices.beancount' relative to the primary ledger.
            # 3. Search the include tree for a file with 'price' in the name.
            # 4. Fallback to the primary ledger.

            target_price_file = None
            for f in files_to_load:
                if f.name == "prices.beancount":
                    target_price_file = f
                    break

            if target_price_file is None:
                primary_file = files_to_load[0]
                sibling_prices = primary_file.parent / "prices.beancount"
                if sibling_prices.exists():
                    target_price_file = sibling_prices
                else:
                    map_service = MapService(primary_file)
                    inc_tree = map_service.get_include_tree()
                    found = _find_price_file(inc_tree)
                    if found:
                        target_price_file = found
                    else:
                        target_price_file = primary_file

            with open(target_price_file, "a") as f:
                f.write(prices_output)

            error_console.print(
                f"[green]Appended {len(filtered_prices)} new prices to {target_price_file.name}[/green]"
            )

        if redundant_count:
            error_console.print(
                f"[yellow]Ignored {redundant_count} fetched prices as they are already in the ledger.[/yellow]"
            )

        if failed_jobs:
            failed_info = ", ".join(f"{j.currency} on {j.date}" for j in failed_jobs[:5])
            if len(failed_jobs) > 5:
                failed_info += f" (+{len(failed_jobs) - 5} more)"
            error_console.print(
                f"[yellow]Skipped {len(failed_jobs)} jobs with no data from source: {failed_info}[/yellow]"
            )

        if not new_price_entries and not failed_jobs and not redundant_count:
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
    _warn_missing_price_meta_entries(ledger_service.entries, context)


def _warn_missing_price_meta_entries(entries: list[data.Directive], context: str) -> None:
    """Warn about held commodities (from a merged entry list) that lack 'price' metadata."""
    from beancount.core import convert
    from beancount.core.inventory import Inventory

    inv = Inventory()
    today = date.today()
    for e in entries:
        if e.date > today:
            break
        if isinstance(e, data.Transaction):
            for p in e.postings:
                if p.account.startswith(("Assets", "Liabilities")):
                    inv.add_position(p)

    held = {
        pos.units.currency
        for pos in inv.reduce(convert.get_units)
        if not pos.units.number.is_zero()
    }

    # Extract operating currencies from options if possible
    # In a merged entry list, we might have 'option' directives as Custom entries or similar?
    # Actually, Beancount usually loads them into an options map.
    # For now, we'll just check commodity metadata.

    commodity_meta = {e.currency: e.meta for e in entries if isinstance(e, data.Commodity)}
    for curr in sorted(held):
        meta = commodity_meta.get(curr, {})
        if not meta or "price" not in meta:
            error_console.print(
                f"[red]Error: Commodity {curr} is held but has no 'price' metadata. {context}[/red]"
            )
