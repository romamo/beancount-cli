import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from beancount.core import data
from beancount.parser import parser as bp_parser
from beancount.parser import printer
from treaty import Arg, Ctx, Exit, Flag, Format, Out, already_exists

from beancount_cli.app import (
    LedgerArgs,
    app,
    ledger_path,
    refuse_directory_target,
    render_rows,
    target_path,
    text,
)
from beancount_cli.models import (
    CommodityImportResult,
    CommodityModel,
    CurrencyCode,
    UndeclaredCommodityModel,
)
from beancount_cli.services import CommodityService

commodity = app.group("commodity", description="Manage commodities")


@dataclass(frozen=True, slots=True)
class ListArgs(LedgerArgs):
    asset_class: str | None = Flag(
        default=None, short="c", description="Filter by asset-class meta (e.g. stock, Cash)"
    )


def render_list(data: Sequence[Mapping[str, Any]]) -> str:
    rows = [[text(c, "currency"), text(c, "date"), text(c.get("meta") or {}, "name")] for c in data]
    return render_rows(f"Commodities ({len(rows)})", ["Currency", "Date", "Name"], rows)


@commodity.command(
    "list",
    description="List all commodities",
    danger_level="safe",
    exit_codes=["NOT_FOUND"],
    examples=[("List the stocks", "bean commodity list --asset-class stock")],
    sort_key="currency",
    renderers={Format.PLAIN: render_list},
)
def commodity_list(args: ListArgs, ctx: Ctx) -> list[CommodityModel]:
    service = CommodityService(ledger_path(args.file, ctx))
    return service.list_commodities(asset_class=args.asset_class)


def render_check(data: Sequence[Mapping[str, Any]]) -> str:
    if not data:
        return "All used currencies are declared.\n"
    rows = [[text(c, "currency")] for c in data]
    return render_rows(f"Undeclared Commodities ({len(rows)})", ["Currency"], rows)


@commodity.command(
    "check",
    description="List currencies used in transactions but missing a commodity directive",
    danger_level="safe",
    exit_codes=["NOT_FOUND"],
    examples=[("Find undeclared currencies", "bean commodity check")],
    sort_key="currency",
    renderers={Format.PLAIN: render_check},
)
def commodity_check(args: LedgerArgs, ctx: Ctx) -> list[UndeclaredCommodityModel]:
    return CommodityService(ledger_path(args.file, ctx)).get_undeclared_commodities()


@dataclass(frozen=True, slots=True)
class ExportArgs(ListArgs):
    output_file: Path | None = Flag(
        default=None,
        description="Write here; default the ledger's commodities_file, else return the text",
    )
    dry_run: bool = Flag(default=False, description="Report what would be written, write nothing")

    def __post_init__(self) -> None:
        refuse_directory_target(
            self.output_file, flag="--output-file", example="DIR/commodities.beancount"
        )


@dataclass(frozen=True, slots=True)
class Exported:
    effect: Literal["created", "updated", "noop", "would_create", "would_update"]
    file: Path | None
    count: int
    entry: str


def render_export(data: Mapping[str, Any]) -> str:
    if data.get("file") is None:
        return text(data, "entry")
    verb = "Would export" if str(data.get("effect", "")).startswith("would_") else "Exported"
    return f"{verb} {text(data, 'count')} commodities → {text(data, 'file')}\n"


@commodity.command(
    "export",
    description="Export commodities as beancount directives",
    danger_level="mutating",
    exit_codes=["NOT_FOUND"],
    examples=[("Write the stocks to a file", "bean commodity export -c stock --output-file s.bc")],
    renderers={Format.PLAIN: render_export},
)
def commodity_export(args: ExportArgs, ctx: Ctx) -> Exported:
    output_file = target_path(args.output_file, flag="--output-file")
    service = CommodityService(ledger_path(args.file, ctx))
    commodities = service.list_commodities(asset_class=args.asset_class)
    content = "\n".join(service._format_commodity_block(c) for c in commodities)

    dest = output_file or service.ledger_service.get_commodities_file()
    if dest is None:
        return Exported(effect="noop", file=None, count=len(commodities), entry=content)
    if dest.exists() and dest.read_text() == content:
        return Exported(effect="noop", file=dest, count=len(commodities), entry=content)
    existed = dest.exists()
    if args.dry_run:
        return Exported(
            effect="would_update" if existed else "would_create",
            file=dest,
            count=len(commodities),
            entry=content,
        )
    dest.write_text(content)
    return Exported(
        effect="updated" if existed else "created",
        file=dest,
        count=len(commodities),
        entry=content,
    )


@dataclass(frozen=True, slots=True)
class ImportArgs(LedgerArgs):
    output_file: Path | None = Flag(
        default=None, description="Write here; default the ledger's commodities_file"
    )
    overwrite: bool = Flag(default=False, description="Replace commodities that already exist")
    dry_run: bool = Flag(default=False, description="Report what would change, write nothing")

    def __post_init__(self) -> None:
        refuse_directory_target(
            self.output_file, flag="--output-file", example="DIR/commodities.beancount"
        )


@dataclass(frozen=True, slots=True)
class Imported:
    effect: Literal["created", "updated", "noop", "would_create", "would_update"]
    file: Path | None
    entry: str
    results: list[CommodityImportResult] = Out(default_factory=list, ordered=True)


def render_import(data: Mapping[str, Any]) -> str:
    if data.get("file") is None and data.get("entry"):
        return text(data, "entry")
    prefix = "(dry-run) " if str(data.get("effect", "")).startswith("would_") else ""
    lines = [f"{prefix}{r['action']:12} {r['currency']}\n" for r in data.get("results", [])]
    if not lines:
        lines.append("No commodity directives found.\n")
    return "".join(lines)


@commodity.command(
    "import",
    description=(
        "Import commodity directives from stdin or --input-file into the commodities_file;"
        " without one, return the new directives"
    ),
    danger_level="mutating",
    exit_codes=["NOT_FOUND", "DIRECTIVES_INVALID"],
    examples=[("Import a registry", "bean commodity import --input-file registry.beancount")],
    stdin_input=True,
    renderers={Format.PLAIN: render_import},
)
def commodity_import(args: ImportArgs, ctx: Ctx) -> Imported:
    output_file = target_path(args.output_file, flag="--output-file")
    entries, errors, _ = bp_parser.parse_string(ctx.stdin_text or "")
    if errors:
        raise Exit.DIRECTIVES_INVALID(
            "Parse error: " + "; ".join(e.message for e in errors),
            context={"errors": [e.message for e in errors]},
        )

    commodities = [
        CommodityModel(currency=e.currency, date=e.date, meta=e.meta)
        for e in entries
        if isinstance(e, data.Commodity)
    ]
    if not commodities:
        return Imported(effect="noop", file=None, entry="")

    service = CommodityService(ledger_path(args.file, ctx))
    dest = output_file or service.ledger_service.get_commodities_file()
    if dest is not None and not dest.exists():
        raise Exit.NOT_FOUND(f"commodities_file not found: {dest}", context={"file": str(dest)})

    results, commodities_file = service.import_commodities(
        commodities, output_file=dest, overwrite=args.overwrite, dry_run=args.dry_run
    )
    written = {r.currency for r in results if r.action != "skipped"}
    blocks = "".join(
        service._format_commodity_block(c) for c in commodities if str(c.currency) in written
    )

    # Without a commodities_file nothing reaches disk: the blocks are returned in entry
    effect: Literal["created", "updated", "noop", "would_create", "would_update"]
    if not written or (commodities_file is None and not args.dry_run):
        effect = "noop"
    elif any(r.action == "overwritten" for r in results):
        effect = "would_update" if args.dry_run else "updated"
    else:
        effect = "would_create" if args.dry_run else "created"
    return Imported(effect=effect, file=commodities_file, entry=blocks, results=results)


@dataclass(frozen=True, slots=True)
class CreateArgs(LedgerArgs):
    currency: CurrencyCode = Arg(description="Currency code (e.g. USD)")
    name: str | None = Flag(default=None, short="n", description="Full name")
    dry_run: bool = Flag(default=False, description="Show the entry, write nothing")


class CommodityWritten(CommodityModel):
    effect: Literal["created", "would_create"]
    file: Path | None
    entry: str


def render_create(data: Mapping[str, Any]) -> str:
    if data.get("file") is None:
        return text(data, "entry")
    return f"Commodity {text(data, 'currency')} created in {text(data, 'file')}.\n"


@commodity.command(
    "create",
    description="Declare a new commodity",
    danger_level="mutating",
    exit_codes=["NOT_FOUND", "CONFLICT"],
    examples=[("Declare Ethereum", "bean commodity create ETH --name Ethereum")],
    renderers={Format.PLAIN: render_create},
)
def commodity_create(args: CreateArgs, ctx: Ctx) -> CommodityWritten:
    meta = {"name": args.name} if args.name else {}
    today = datetime.date.today()
    model = CommodityModel(currency=args.currency, date=today, meta=meta)
    entry = printer.format_entry(data.Commodity(meta=meta, date=today, currency=str(args.currency)))
    fields = model.model_dump()
    if args.dry_run:
        return CommodityWritten(**fields, effect="would_create", file=None, entry=entry)
    service = CommodityService(ledger_path(args.file, ctx))
    if str(args.currency) in service.ledger_service.get_commodities():
        raise already_exists({"currency": str(args.currency)}, conflict_id=str(args.currency))
    written = service.create_commodity(args.currency, name=args.name)
    return CommodityWritten(**fields, effect="created", file=written, entry=entry)
