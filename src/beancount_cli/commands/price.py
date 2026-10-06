import datetime
import logging
from collections.abc import Iterable, Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from tempfile import gettempdir
from typing import Any, Literal

from beancount.core import convert, data
from beancount.core.data import sorted as bean_sorted
from beancount.core.inventory import Inventory
from beancount.ops import lifetimes as bean_lifetimes
from beancount.parser import printer
from beanprice import price as bp_price
from treaty import Arg, Ctx, Exit, Flag, Format, Out

from beancount_cli.app import LedgerArgs, app, ledger_path, render_rows, text
from beancount_cli.models import PriceAnomalyModel, PriceGapModel
from beancount_cli.services import LedgerService, MapService, PriceService

price = app.group("price", description="Manage prices")


@dataclass(frozen=True, slots=True)
class CheckArgs(LedgerArgs):
    tolerance: int = Flag(
        default=7, short="t", description="Allowed delay in days before flagging a gap"
    )
    rate: Literal["daily", "weekday", "weekly", "monthly"] = Flag(
        default="daily", short="r", description="Expected price frequency"
    )


def render_gaps(data: Sequence[Mapping[str, Any]]) -> str:
    if not data:
        return "No price gaps found.\n"
    rows = [
        [
            text(g, "currency"),
            text(g, "target_currency"),
            text(g, "gap_start"),
            text(g, "last_available_date") or "None",
            text(g, "days_missing"),
        ]
        for g in data
    ]
    return render_rows(
        f"Price Gaps ({len(rows)})",
        ["Currency", "Target", "Gap Date", "Last Date", "Days Out"],
        rows,
        right=["Days Out"],
    )


@price.command(
    "check",
    description="Find periods of missing price data for held commodities",
    danger_level="safe",
    exit_codes=["NOT_FOUND"],
    examples=[("Find weekly price gaps", "bean price check --rate weekly")],
    ordered=True,
    renderers={Format.PLAIN: render_gaps},
)
def price_check(args: CheckArgs, ctx: Ctx) -> list[PriceGapModel]:
    ledger_service = LedgerService(ledger_path(args.file, ctx))
    ledger_service.load()
    _warn_missing_price_meta(
        ctx,
        ledger_service.entries,
        "Price history cannot be verified.",
        ledger_service.get_operating_currencies(),
    )
    return PriceService(ledger_service).get_price_gaps(
        tolerance_days=args.tolerance, rate=args.rate
    )


@dataclass(frozen=True, slots=True)
class AnomalyArgs(LedgerArgs):
    threshold: Decimal = Flag(
        default=Decimal("1.0"),
        short="t",
        description="Minimum change as a fraction (1.0 is 100%)",
    )
    max_days: int = Flag(
        default=7, short="d", description="Maximum days between consecutive prices"
    )


def render_anomalies(data: Sequence[Mapping[str, Any]]) -> str:
    if not data:
        return "No price anomalies found.\n"
    rows = [
        [
            text(a, "currency"),
            text(a, "target_currency"),
            text(a, "date"),
            text(a, "next_date"),
            f"{Decimal(a['price']):,.4f}" if "price" in a else "",
            f"{Decimal(a['next_price']):,.4f}" if "next_price" in a else "",
            f"{Decimal(a['change_pct']):,.1f}%" if "change_pct" in a else "",
        ]
        for a in data
    ]
    return render_rows(
        f"Price Anomalies ({len(rows)})",
        ["Currency", "Target", "Date", "Next Date", "Price", "Next Price", "Change %"],
        rows,
        right=["Price", "Next Price", "Change %"],
    )


@price.command(
    "check-anomalies",
    description="Find sudden price jumps or drops",
    danger_level="safe",
    exit_codes=["NOT_FOUND"],
    examples=[("Flag moves of 50% or more", "bean price check-anomalies --threshold 0.5")],
    ordered=True,
    renderers={Format.PLAIN: render_anomalies},
)
def price_check_anomalies(args: AnomalyArgs, ctx: Ctx) -> list[PriceAnomalyModel]:
    price_service = PriceService(LedgerService(ledger_path(args.file, ctx)))
    return price_service.get_price_anomalies(threshold=args.threshold, max_days=args.max_days)


@dataclass(frozen=True, slots=True)
class FetchArgs(LedgerArgs):
    ledger_files: tuple[Path, ...] = Arg(
        default=(),
        description="Ledger files to merge before fetching; default --file",
    )
    update: bool = Flag(
        default=False, short="u", description="Fetch from the last price forward and write them"
    )
    inactive: bool = Flag(
        default=False, short="i", description="Include commodities with no balance"
    )
    fill_gaps: bool = Flag(default=False, description="Fill gaps in the price history")
    dry_run: bool = Flag(default=False, description="List the price jobs, fetch nothing")


@dataclass(frozen=True, slots=True)
class FetchedPrice:
    date: datetime.date
    currency: str
    number: Decimal
    quote: str


@dataclass(frozen=True, slots=True)
class JobError:
    job: str
    error: str


@dataclass(frozen=True, slots=True)
class PriceFetch:
    """What a fetch did: ``prices`` is every new price, ``written`` how many reached ``file``"""

    effect: Literal["created", "noop", "would_create"]
    file: Path | None
    written: int
    redundant: int
    jobs: list[str] = Out(default_factory=list, ordered=True)
    prices: list[FetchedPrice] = Out(default_factory=list, ordered=True)
    no_data: list[str] = Out(default_factory=list)
    errors: list[JobError] = Out(default_factory=list, sort_key="job")


def render_fetch(data: Mapping[str, Any]) -> str:
    if data.get("effect") == "would_create":
        # Beancount comments, so the dry-run output is still a valid price file
        jobs = data.get("jobs", [])
        return f"; Dry run: {len(jobs)} jobs generated.\n" + "".join(f";   {j}\n" for j in jobs)
    # Only directives, so the output can be appended to a price file; status goes to stderr
    return "".join(
        f"{p['date']} price {p['currency']} {p['number']} {p['quote']}\n"
        for p in data.get("prices", [])
    )


@price.command(
    "fetch",
    description=(
        "Fetch the latest prices with bean-price; --update writes them to the ledger's price"
        " file. Several ledger files are merged before the jobs are computed"
    ),
    danger_level="mutating",
    exit_codes=["NOT_FOUND", "PARTIAL_FAILURE"],
    examples=[
        ("Show today's prices", "bean price fetch main.beancount"),
        ("Fetch and write missing prices", "bean price fetch main.beancount --update"),
    ],
    has_network_io=True,
    external=True,
    timeout=None,
    renderers={Format.PLAIN: render_fetch},
)
def price_fetch(args: FetchArgs, ctx: Ctx) -> PriceFetch:
    files_to_load = [ledger_path(f, ctx) for f in args.ledger_files or (args.file,)]
    ctx.progress(f"Fetching prices for {', '.join(str(f) for f in files_to_load)}")

    bp_price.setup_cache(str(Path(gettempdir()) / "bean-price.cache"), clear_cache=False)

    # Merge every ledger, in beancount's canonical order
    services = [LedgerService(f) for f in files_to_load]
    all_entries: list[data.Directive] = []
    for svc in services:
        svc.load()
        all_entries.extend(svc.entries)
    entries = bean_sorted(all_entries)

    _warn_missing_price_meta(
        ctx, entries, "Skipping fetch.", services[0].get_operating_currencies()
    )

    date_last = datetime.date.today()
    jobs = _resolve_price_jobs(entries, date_last, args.inactive, args.update, args.fill_gaps)
    if not args.inactive:
        inactive_jobs = _resolve_price_jobs(entries, date_last, True, args.update, args.fill_gaps)
        existing = {(j.base, j.quote, j.date) for j in jobs}
        jobs.extend(
            j
            for j in _get_cash_currency_jobs(entries, date_last, inactive_jobs)
            if (j.base, j.quote, j.date) not in existing
        )

    job_names = [bp_price.format_dated_price_str(job) for job in jobs]
    if not jobs:
        ctx.progress("No new prices found.")
        return PriceFetch(effect="noop", file=None, written=0, redundant=0)
    if args.dry_run:
        return PriceFetch(effect="would_create", file=None, written=0, redundant=0, jobs=job_names)

    # Skip prices already in the ledger, and duplicates among the fetched ones
    existing_prices = {(e.date, e.currency) for e in entries if isinstance(e, data.Price)}
    new_prices: list[data.Price] = []
    failed_jobs: list[bp_price.DatedPrice] = []
    errored_jobs: list[tuple[bp_price.DatedPrice, str]] = []
    redundant = 0
    for job, price_entry, error in _fetch_price_jobs(jobs):
        if error is not None:
            errored_jobs.append((job, error))
        elif price_entry is None:
            failed_jobs.append(job)
        elif (price_entry.date, price_entry.currency) in existing_prices:
            redundant += 1
        else:
            assert price_entry.amount.number is not None  # beanprice always sets it
            new_prices.append(
                price_entry._replace(
                    amount=price_entry.amount._replace(
                        number=price_entry.amount.number.quantize(Decimal("1.000000"))
                    )
                )
            )
            existing_prices.add((price_entry.date, price_entry.currency))
    new_prices.sort(key=lambda p: (p.currency, p.date))

    target_price_file: Path | None = None
    to_write: list[data.Price] = []
    if args.update and new_prices:
        to_write, _ = bp_price.filter_redundant_prices(new_prices, entries)
    if to_write:
        target_price_file = _price_file(files_to_load)
        with open(target_price_file, "a") as f:
            f.write("".join(printer.format_entry(p) for p in to_write))
        ctx.progress(f"Appended {len(to_write)} new prices to {target_price_file}")
    elif not new_prices:
        ctx.progress("No new prices found.")

    if redundant:
        ctx.warn(
            "PRICES_REDUNDANT",
            f"Ignored {redundant} fetched prices as they are already in the ledger",
            count=redundant,
        )
    if failed_jobs:
        ctx.warn(
            "PRICES_NO_DATA",
            f"Skipped {len(failed_jobs)} jobs with no data from source: "
            + _summarize(_describe_job(j) for j in failed_jobs),
            jobs=[_describe_job(j) for j in failed_jobs],
        )

    result = PriceFetch(
        effect="created" if to_write else "noop",
        file=target_price_file,
        written=len(to_write),
        redundant=redundant,
        jobs=job_names,
        prices=[_fetched(p) for p in new_prices],
        no_data=[_describe_job(j) for j in failed_jobs],
        errors=[JobError(job=_describe_job(j), error=e) for j, e in errored_jobs],
    )
    if errored_jobs:
        raise Exit.PARTIAL_FAILURE(
            f"Skipped {len(errored_jobs)} jobs with source errors: "
            + _summarize(f"{_describe_job(j)} ({e})" for j, e in errored_jobs),
            context={"failed": len(errored_jobs), "jobs": len(jobs)},
            suggestion="rerun later; the prices that were fetched are kept",
            data=result,
        )
    return result


def _fetched(p: data.Price) -> FetchedPrice:
    assert p.amount.number is not None  # beanprice always sets it
    return FetchedPrice(
        date=p.date, currency=p.currency, number=p.amount.number, quote=p.amount.currency
    )


def _price_file(files_to_load: list[Path]) -> Path:
    """Where fetched prices go: a prices.beancount among the files or beside the first one,
    else a file with 'price' in its name in the include tree, else the first file."""
    for f in files_to_load:
        if f.name == "prices.beancount":
            return f
    primary_file = files_to_load[0]
    sibling_prices = primary_file.parent / "prices.beancount"
    if sibling_prices.exists():
        return sibling_prices
    found = _find_price_file(MapService(primary_file).get_include_tree())
    return found or primary_file


def _fetch_price_job(job: bp_price.DatedPrice) -> tuple[data.Price | None, str | None]:
    """Fetch one job, returning (price, error) instead of raising on a source failure.

    Price sources signal fetch errors with ValueError (the beanprice source
    convention) and transport failures with OSError (urllib, requests and
    curl_cffi errors all derive from it). Anything else is a bug and propagates.
    """
    try:
        return bp_price.fetch_price(job), None
    except (ValueError, OSError) as exc:
        logging.error("Error fetching %s: %s", bp_price.format_dated_price_str(job), exc)
        return None, str(exc)


def _fetch_price_jobs(
    jobs: list[bp_price.DatedPrice],
) -> Iterator[tuple[bp_price.DatedPrice, data.Price | None, str | None]]:
    """Fetch jobs concurrently, yielding (job, price, error) as each completes."""
    with ThreadPoolExecutor(max_workers=min(8, len(jobs))) as executor:
        future_to_job = {executor.submit(_fetch_price_job, job): job for job in jobs}
        for future in as_completed(future_to_job):
            yield future_to_job[future], *future.result()


def _describe_job(job: bp_price.DatedPrice) -> str:
    return f"{job.base} on {job.date or 'latest'}"


def _summarize(items: Iterable[str], limit: int = 5) -> str:
    items = list(items)
    info = ", ".join(items[:limit])
    if len(items) > limit:
        info += f" (+{len(items) - limit} more)"
    return info


def _resolve_price_jobs(
    entries: list[data.Directive],
    date_last: datetime.date,
    inactive: bool,
    update: bool,
    fill_gaps: bool,
) -> list:
    if update or fill_gaps:
        return bp_price.get_price_jobs_up_to_date(
            entries, date_last=date_last, inactive=inactive, fill_gaps=fill_gaps
        )
    return bp_price.get_price_jobs_at_date(entries, date=None, inactive=inactive)


def _get_cash_currency_jobs(
    entries: list[data.Directive],
    date_last: datetime.date,
    inactive_jobs: list,
) -> list:
    """Return price jobs for currencies held as cash that beanprice silently drops.

    beanprice's lifetimes tracker keys holdings as (currency, cost_currency). Cash
    currencies produce (base, None) keys, but declared price sources register as
    (base, quote) — they never match, so the filter at price.py:478 drops them.
    """
    raw_lifetimes = bean_lifetimes.get_commodity_lifetimes(entries)
    cash_bases = {
        base for (base, cost), intervals in raw_lifetimes.items() if cost is None and intervals
    }
    if not cash_bases:
        return []

    declared_triples = bp_price.find_currencies_declared(entries, date_last)
    cash_pairs = {(base, quote) for base, quote, _ in declared_triples if base in cash_bases}
    if not cash_pairs:
        return []

    return [job for job in inactive_jobs if (job.base, job.quote) in cash_pairs]


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


def _warn_missing_price_meta(
    ctx: Ctx,
    entries: list[data.Directive],
    context: str,
    operating_currencies: list[str],
) -> None:
    """Warn about held commodities that lack 'price' metadata and so cannot be priced."""
    inv = Inventory()
    today = datetime.date.today()
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

    commodity_meta = {e.currency: e.meta for e in entries if isinstance(e, data.Commodity)}
    for curr in sorted(held - set(operating_currencies)):
        meta = commodity_meta.get(curr, {})
        if not meta or "price" not in meta:
            ctx.warn(
                "PRICE_META_MISSING",
                f"Commodity {curr} is held but has no 'price' metadata. {context}",
                currency=curr,
            )
