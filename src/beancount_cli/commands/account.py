import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from beancount.core import data
from beancount.parser import printer
from treaty import Ctx, Exit, Flag, Format, already_exists

from beancount_cli.adapters import to_core_balance, to_core_pad
from beancount_cli.app import LedgerArgs, app, ledger_path, render_rows, text
from beancount_cli.models import (
    AccountModel,
    AccountName,
    AmountModel,
    BalanceModel,
    CurrencyCode,
    PadBalanceModel,
)
from beancount_cli.services import AccountService

account = app.group("account", description="Manage accounts")


def render_list(data: Sequence[Mapping[str, Any]]) -> str:
    rows = [
        [text(acc, "name"), text(acc, "open_date"), ", ".join(acc.get("currencies", []))]
        for acc in data
    ]
    return render_rows(f"Accounts ({len(rows)})", ["Account", "Open Date", "Currencies"], rows)


@account.command(
    "list",
    description="List all accounts",
    danger_level="safe",
    exit_codes=["NOT_FOUND"],
    examples=[("List the accounts of main.beancount", "bean account list -f main.beancount")],
    sort_key="name",
    renderers={Format.PLAIN: render_list},
)
def account_list(args: LedgerArgs, ctx: Ctx) -> list[AccountModel]:
    return AccountService(ledger_path(args.file, ctx)).list_accounts()


def render_written(template: str):
    """A plain renderer: the entry on a dry run, else ``template`` filled from the result."""

    def render(data: Mapping[str, Any]) -> str:
        if data.get("file") is None:
            return text(data, "entry")
        return template.format(**{key: text(data, key) for key in ("name", "account", "file")})

    return render


@dataclass(frozen=True, slots=True)
class CreateArgs(LedgerArgs):
    name: AccountName = Flag(short="n", description="Account name (e.g. Assets:Bank)")
    currency: tuple[CurrencyCode, ...] = Flag(
        default=(), short="c", description="Allowed currency; repeat for more"
    )
    date: datetime.date | None = Flag(
        default=None, short="d", description="Open date (YYYY-MM-DD); default today"
    )
    target: Path | None = Flag(default=None, description="Write to this file instead")
    dry_run: bool = Flag(default=False, description="Show the entry, write nothing")


class AccountWritten(AccountModel):
    effect: Literal["created", "would_create"]
    file: Path | None
    entry: str


@account.command(
    "create",
    description="Open a new account",
    danger_level="mutating",
    exit_codes=["NOT_FOUND", "CONFLICT"],
    examples=[("Open a credit card account", "bean account create -n Liabilities:Card -c USD")],
    renderers={Format.PLAIN: render_written("Account {name} created in {file}.\n")},
)
def account_create(args: CreateArgs, ctx: Ctx) -> AccountWritten:
    open_date = args.date or datetime.date.today()
    model = AccountModel(name=args.name, open_date=open_date, currencies=list(args.currency))
    entry = printer.format_entry(
        data.Open(
            meta={},
            date=open_date,
            account=str(model.name),
            currencies=[str(c) for c in model.currencies],
            booking=None,
        )
    )
    fields = model.model_dump()
    if args.dry_run:
        return AccountWritten(**fields, effect="would_create", file=None, entry=entry)
    service = AccountService(ledger_path(args.file, ctx))
    if str(args.name) in service.ledger_service.get_accounts():
        raise already_exists({"name": str(args.name)}, conflict_id=str(args.name))
    written = service.create_account(model, target_file=args.target)
    return AccountWritten(**fields, effect="created", file=written, entry=entry)


@dataclass(frozen=True, slots=True)
class BalanceArgs(LedgerArgs):
    account: AccountName = Flag(description="Account name (e.g. Assets:Bank)")
    date: datetime.date = Flag(description="Balance date (YYYY-MM-DD)")
    amount: Decimal = Flag(description="Balance amount (e.g. 1000.00)")
    currency: CurrencyCode = Flag(short="c", description="Currency code (e.g. USD)")
    target: Path | None = Flag(default=None, description="Write to this file instead")
    dry_run: bool = Flag(default=False, description="Show the entry, write nothing")


class BalanceWritten(BalanceModel):
    effect: Literal["created", "would_create"]
    file: Path | None
    entry: str


def _require_open(service: AccountService, name: AccountName) -> None:
    if str(name) not in service.ledger_service.get_accounts():
        raise Exit.NOT_FOUND(
            f"Account '{name}' does not exist (no Open directive)",
            context={"account": str(name)},
            suggestion=f"bean account create -n {name}",
        )


@account.command(
    "balance",
    description="Assert an account's balance with a balance directive",
    danger_level="mutating",
    exit_codes=["NOT_FOUND"],
    examples=[
        (
            "Assert the cash balance",
            "bean account balance --account Assets:Cash --date 2024-01-01 --amount 1000 -c USD",
        )
    ],
    renderers={Format.PLAIN: render_written("Balance check for {account} added to {file}.\n")},
)
def account_balance(args: BalanceArgs, ctx: Ctx) -> BalanceWritten:
    model = BalanceModel(
        account=args.account,
        date=args.date,
        amount=AmountModel(number=args.amount, currency=args.currency),
    )
    entry = printer.format_entry(to_core_balance(model))
    fields = model.model_dump()
    if args.dry_run:
        return BalanceWritten(**fields, effect="would_create", file=None, entry=entry)
    service = AccountService(ledger_path(args.file, ctx))
    _require_open(service, args.account)
    written = service.add_balance(model, target_file=args.target)
    return BalanceWritten(**fields, effect="created", file=written, entry=entry)


@dataclass(frozen=True, slots=True)
class PadBalanceArgs(LedgerArgs):
    account: AccountName = Flag(description="Account to adjust (e.g. Assets:BE:Wise:EUR)")
    amount: Decimal = Flag(description="Target balance amount (e.g. 1777.00)")
    currency: CurrencyCode = Flag(short="c", description="Currency of the target balance")
    pad_account: AccountName = Flag(
        default=AccountName("Expenses:Other"),
        short="p",
        description="Account that absorbs the difference",
    )
    date: datetime.date | None = Flag(
        default=None, short="d", description="Date of the balance assertion; default today"
    )
    pad_date: datetime.date | None = Flag(
        default=None, description="Date of the pad directive; default the day before --date"
    )
    target: Path | None = Flag(default=None, description="Write to this file instead")
    dry_run: bool = Flag(default=False, description="Show the entries, write nothing")


class PadBalanceWritten(PadBalanceModel):
    effect: Literal["created", "would_create"]
    file: Path | None
    entry: str


@account.command(
    "pad-balance",
    description=(
        "Bring an account to a balance with a pad and a balance directive; beancount books"
        " the difference to --pad-account"
    ),
    danger_level="mutating",
    exit_codes=["NOT_FOUND"],
    examples=[
        (
            "Record that the Wise EUR balance is now 1777",
            "bean account pad-balance --account Assets:BE:Wise:EUR --amount 1777 -c EUR",
        )
    ],
    renderers={Format.PLAIN: render_written("Pad + Balance for {account} added to {file}.\n")},
)
def account_pad_balance(args: PadBalanceArgs, ctx: Ctx) -> PadBalanceWritten:
    model = PadBalanceModel(
        balance_date=args.date or datetime.date.today(),
        account=args.account,
        amount=AmountModel(number=args.amount, currency=args.currency),
        pad_account=args.pad_account,
        pad_date=args.pad_date,
    )
    core_pad, core_balance = to_core_pad(model)
    entry = printer.format_entry(core_pad) + "\n" + printer.format_entry(core_balance)
    fields = model.model_dump()
    if args.dry_run:
        return PadBalanceWritten(**fields, effect="would_create", file=None, entry=entry)
    service = AccountService(ledger_path(args.file, ctx))
    _require_open(service, args.account)
    written = service.add_pad_balance(model, target_file=args.target)
    return PadBalanceWritten(**fields, effect="created", file=written, entry=entry)
