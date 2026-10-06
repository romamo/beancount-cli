import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from treaty import Ctx, Exit, Flag, Format

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
    AccountName,
    AmountModel,
    CostModel,
    CurrencyCode,
    PostingModel,
    RegexPattern,
    TransactionModel,
)
from beancount_cli.services import TransactionService

transaction = app.group("transaction", description="Manage transactions")


@dataclass(frozen=True, slots=True)
class ListArgs(LedgerArgs):
    account: RegexPattern | None = Flag(default=None, description="Filter by account regex")
    payee: RegexPattern | None = Flag(default=None, short="p", description="Filter by payee regex")
    tag: str | None = Flag(default=None, short="t", description="Filter by tag")
    where: str | None = Flag(default=None, short="w", description="BQL where clause")


def render_list(data: Sequence[Mapping[str, Any]]) -> str:
    rows = [[text(tx, "date"), text(tx, "payee"), text(tx, "narration")] for tx in data]
    return render_rows(f"Transactions ({len(rows)})", ["Date", "Payee", "Narration"], rows)


@transaction.command(
    "list",
    description="List transactions matching the filters, oldest first",
    danger_level="safe",
    exit_codes=["NOT_FOUND", "QUERY_INVALID"],
    examples=[
        ("List grocery transactions", "bean transaction list --payee Store"),
        ("Filter with BQL", "bean transaction list --where \"account ~ 'Expenses'\""),
    ],
    ordered=True,
    renderers={Format.PLAIN: render_list},
)
def tx_list(args: ListArgs, ctx: Ctx) -> list[TransactionModel]:
    service = TransactionService(ledger_path(args.file, ctx))
    try:
        return service.list_transactions(
            account_regex=args.account, payee_regex=args.payee, tag=args.tag, bql_where=args.where
        )
    except ValueError as e:
        raise Exit.QUERY_INVALID(str(e), context={"where": args.where}) from e


@dataclass(frozen=True, slots=True)
class AmountInput:
    number: Decimal
    currency: CurrencyCode


@dataclass(frozen=True, slots=True)
class CostInput:
    number: Decimal
    currency: CurrencyCode
    date: datetime.date | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class PostingInput:
    account: AccountName
    units: AmountInput
    cost: CostInput | None = None
    price: AmountInput | None = None
    flag: str | None = None

    def to_model(self) -> PostingModel:
        return PostingModel(
            account=self.account,
            units=AmountModel(number=self.units.number, currency=self.units.currency),
            cost=CostModel(
                number=self.cost.number,
                currency=self.cost.currency,
                date=self.cost.date,
                label=self.cost.label,
            )
            if self.cost
            else None,
            price=AmountModel(number=self.price.number, currency=self.price.currency)
            if self.price
            else None,
            flag=self.flag,
        )


@dataclass(frozen=True, slots=True)
class AddArgs(LedgerArgs):
    date: datetime.date = Flag(description="Transaction date (YYYY-MM-DD)")
    narration: str = Flag(description="Transaction narration")
    postings: tuple[PostingInput, ...] = Flag(
        description="One posting as a JSON object; repeat the flag for each posting"
    )
    payee: str | None = Flag(default=None, description="Payee name")
    tags: tuple[str, ...] = Flag(default=(), description="Tag, without '#'; repeat for more")
    links: tuple[str, ...] = Flag(default=(), description="Link, without '^'; repeat for more")
    draft: bool = Flag(default=False, description="Mark as pending (!)")
    target: Path | None = Flag(default=None, description="Write to this file instead")
    dry_run: bool = Flag(default=False, description="Show the entry, write nothing")

    def __post_init__(self) -> None:
        refuse_directory_target(self.target)


class TransactionWritten(TransactionModel):
    effect: Literal["created", "would_create"]
    file: Path | None
    entry: str


def render_written(data: Mapping[str, Any]) -> str:
    if data.get("file") is None:
        return text(data, "entry")
    return f"Transaction added to {text(data, 'file')}.\n"


@transaction.command(
    "add",
    description="Add a transaction",
    danger_level="mutating",
    exit_codes=["NOT_FOUND", "TRANSACTION_INVALID"],
    supports_raw_payload=True,
    examples=[
        (
            "Record a grocery purchase",
            "bean transaction add --date 2024-01-15 --narration Groceries"
            ' --postings \'{"account": "Expenses:Food", "units": {"number": 50, "currency": "USD"}}\''
            ' --postings \'{"account": "Assets:Cash", "units": {"number": -50, "currency": "USD"}}\'',
        ),
    ],
    renderers={Format.PLAIN: render_written},
)
def tx_add(args: AddArgs, ctx: Ctx) -> TransactionWritten:
    model = TransactionModel(
        date=args.date,
        narration=args.narration,
        payee=args.payee,
        postings=[p.to_model() for p in args.postings],
        tags=set(args.tags),
        links=set(args.links),
    )
    service = TransactionService(ledger_path(args.file, ctx))
    try:
        entry = service.render_transaction(model, draft=args.draft)
    except ValueError as e:
        raise Exit.TRANSACTION_INVALID(str(e)) from e

    fields = model.model_dump()
    if args.dry_run:
        return TransactionWritten(**fields, effect="would_create", file=None, entry=entry)
    written = service.write_transaction(model, entry, target_file=target_path(args.target))
    return TransactionWritten(**fields, effect="created", file=written, entry=entry)
