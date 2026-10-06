import datetime
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from treaty import Ctx, Exit, Flag, Format, Out

from beancount_cli.app import LedgerArgs, app, ledger_path, render_rows, text
from beancount_cli.formatting import Table
from beancount_cli.models import CurrencyCode
from beancount_cli.services import LedgerService, ReportService, TransactionService

report = app.group("report", description="Generate reports")

ROOTS = ("Assets", "Liabilities", "Equity", "Income", "Expenses")
TOLERANCE = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class ValuationArgs(LedgerArgs):
    convert: CurrencyCode | None = Flag(
        default=None, short="c", description="Target currency for unified reporting"
    )
    valuation: Literal["market", "cost"] = Flag(default="market", description="Valuation strategy")


@dataclass(frozen=True, slots=True)
class AccountBalance:
    account: str
    units: dict[str, Decimal]
    cost: dict[str, Decimal]


@dataclass(frozen=True, slots=True)
class NetPosition:
    """The debit and credit totals of the root accounts at cost, per currency."""

    currency: str
    debit: Decimal
    credit: Decimal
    net: Decimal
    balanced: bool


@dataclass(frozen=True, slots=True)
class BalanceReport:
    accounts: list[AccountBalance] = Out(default_factory=list, sort_key="account")
    net_positions: list[NetPosition] = Out(default_factory=list, sort_key="currency")


def _balance_report(service: ReportService, args: ValuationArgs, roots: list[str] | None):
    try:
        balances = service.get_balances(
            account_roots=roots, convert_to=args.convert, valuation=args.valuation
        )
    except ValueError as e:
        raise Exit.CONVERSION_FAILED(str(e), context={"convert": args.convert}) from e

    debit: dict[str, Decimal] = {}
    credit: dict[str, Decimal] = {}
    for account, values in balances.items():
        if account in ROOTS or ":" not in account:
            for currency, amount in values["cost"].items():
                totals = debit if amount > 0 else credit
                totals[currency] = totals.get(currency, Decimal(0)) + amount

    return BalanceReport(
        accounts=[
            AccountBalance(account=account, units=values["units"], cost=values["cost"])
            for account, values in balances.items()
        ],
        net_positions=[
            NetPosition(
                currency=currency,
                debit=debit.get(currency, Decimal(0)),
                credit=credit.get(currency, Decimal(0)),
                net=debit.get(currency, Decimal(0)) + credit.get(currency, Decimal(0)),
                balanced=abs(debit.get(currency, Decimal(0)) + credit.get(currency, Decimal(0)))
                < TOLERANCE,
            )
            for currency in sorted(set(debit) | set(credit))
        ],
    )


def _amounts(values: Mapping[str, Any]) -> str:
    return ", ".join(f"{Decimal(v):,.2f} {k}" for k, v in sorted(values.items()))


def render_balances(title: str) -> Callable[[Mapping[str, Any]], str]:
    def render(data: Mapping[str, Any]) -> str:
        table = Table(title=title)
        table.add_column("Account")
        table.add_column("Balance", justify="right")
        for row in data.get("accounts", []):
            table.add_row(row["account"], _amounts(row["units"]))

        positions = data.get("net_positions", [])
        if positions:
            table.add_section()
        for position in positions:
            status = (
                "✓ Balanced"
                if position["balanced"]
                else f"Exposure: {Decimal(position['net']):,.2f} {position['currency']}"
            )
            table.add_row(
                f"NET POSITION {position['currency']}",
                f"{Decimal(position['debit']):,.2f} (Dr) | "
                f"{Decimal(position['credit']):,.2f} (Cr) | {status}",
            )

        out = f"{table}\n"
        if any(not p["balanced"] for p in positions):
            out += (
                "Note: Perpetual positions in specific currencies are normal where "
                "exchanges occur at market prices (@@).\n"
            )
        return out

    return render


@report.command(
    "balance-sheet",
    description="Snapshot of Assets, Liabilities, and Equity",
    danger_level="safe",
    exit_codes=["NOT_FOUND", "CONVERSION_FAILED"],
    examples=[("Balance sheet in USD", "bean report balance-sheet -c USD")],
    renderers={Format.PLAIN: render_balances("Balance Sheet")},
)
def report_balance_sheet(args: ValuationArgs, ctx: Ctx) -> BalanceReport:
    service = ReportService(LedgerService(ledger_path(args.file, ctx)))
    return _balance_report(service, args, ["Assets", "Liabilities", "Equity"])


@report.command(
    "trial-balance",
    description="All account balances, for ledger-wide checks",
    danger_level="safe",
    exit_codes=["NOT_FOUND", "CONVERSION_FAILED"],
    examples=[("Trial balance at cost", "bean report trial-balance --valuation cost")],
    renderers={Format.PLAIN: render_balances("Trial Balance")},
)
def report_trial_balance(args: ValuationArgs, ctx: Ctx) -> BalanceReport:
    service = ReportService(LedgerService(ledger_path(args.file, ctx)))
    return _balance_report(service, args, None)


@dataclass(frozen=True, slots=True)
class Holding:
    account: str
    units: dict[str, Decimal]
    market_value: dict[str, Decimal]
    cost_basis: dict[str, Decimal]
    unrealized_gain: dict[str, Decimal]


@dataclass(frozen=True, slots=True)
class HoldingTotal:
    currency: str
    market_value: Decimal
    cost_basis: Decimal
    unrealized_gain: Decimal


@dataclass(frozen=True, slots=True)
class HoldingsReport:
    valuation: str
    currencies: list[str] = Out(default_factory=list, ordered=True)
    accounts: list[Holding] = Out(default_factory=list, sort_key="account")
    totals: list[HoldingTotal] = Out(default_factory=list, sort_key="currency")


def _gain(gain: Decimal, cost: Decimal) -> str:
    pct = (gain / cost * 100) if cost != 0 else Decimal(0)
    return f"{gain:,.2f} ({pct:.1f}%)"


def render_holdings(data: Mapping[str, Any]) -> str:
    currencies = data.get("currencies", [])
    table = Table(title=f"Portfolio Holdings ({str(data.get('valuation', '')).capitalize()} Value)")
    table.add_column("Account")
    table.add_column("Holdings")
    for currency in currencies:
        table.add_column(f"Value ({currency})", justify="right")
        table.add_column(f"Cost ({currency})", justify="right")
        table.add_column("Gain (%)", justify="right")

    for holding in data.get("accounts", []):
        row = [holding["account"], _amounts(holding["units"])]
        for currency in currencies:
            market = Decimal(holding["market_value"].get(currency, 0))
            cost = Decimal(holding["cost_basis"].get(currency, 0))
            gain = Decimal(holding["unrealized_gain"].get(currency, 0))
            row.extend([f"{market:,.2f}", f"{cost:,.2f}", _gain(gain, cost)])
        table.add_row(*row)

    totals = {t["currency"]: t for t in data.get("totals", [])}
    if currencies:
        table.add_section()
        row = ["TOTAL", ""]
        for currency in currencies:
            total = totals.get(currency, {})
            market = Decimal(total.get("market_value", 0))
            cost = Decimal(total.get("cost_basis", 0))
            gain = Decimal(total.get("unrealized_gain", 0))
            row.extend([f"{market:,.2f}", f"{cost:,.2f}", _gain(gain, cost)])
        table.add_row(*row)
    return f"{table}\n"


@report.command(
    "holdings",
    description="Asset positions with valuation and gains",
    danger_level="safe",
    exit_codes=["NOT_FOUND", "CONVERSION_FAILED"],
    examples=[("Holdings valued in EUR", "bean report holdings -c EUR")],
    renderers={Format.PLAIN: render_holdings},
)
def report_holdings(args: ValuationArgs, ctx: Ctx) -> HoldingsReport:
    service = LedgerService(ledger_path(args.file, ctx))
    target = args.convert or next(iter(service.get_operating_currencies()), None)
    targets = [target] if target else []
    try:
        holdings = ReportService(service).get_holdings(
            valuation=args.valuation, target_currencies=targets
        )
    except ValueError as e:
        raise Exit.CONVERSION_FAILED(str(e), context={"convert": args.convert}) from e

    return HoldingsReport(
        valuation=args.valuation,
        currencies=list(targets),
        accounts=[
            Holding(
                account=account,
                units=h["units"],
                market_value=h["market_values"],
                cost_basis=h["cost_basis"],
                unrealized_gain=h["unrealized_gains"],
            )
            for account, h in holdings["accounts"].items()
        ],
        totals=[
            HoldingTotal(
                currency=currency,
                market_value=t["market"],
                cost_basis=t["cost"],
                unrealized_gain=t["gain"],
            )
            for currency, t in holdings["totals"].items()
        ],
    )


@dataclass(frozen=True, slots=True)
class AuditArgs(LedgerArgs):
    currency: CurrencyCode | None = Flag(
        default=None, short="c", description="Currency to audit; default the operating currency"
    )
    limit: int = Flag(default=20, short="l", description="Show the last N transactions")
    all: bool = Flag(default=False, description="Show every transaction")


@dataclass(frozen=True, slots=True)
class AuditPosting:
    date: datetime.date
    description: str
    account: str
    amount: Decimal
    currency: str
    price: Decimal | None
    price_currency: str | None
    cost: Decimal | None
    cost_currency: str | None


@dataclass(frozen=True, slots=True)
class AuditReport:
    currency: str
    transactions: int
    limited: bool
    postings: list[AuditPosting] = Out(default_factory=list, ordered=True)


def render_audit(data: Mapping[str, Any]) -> str:
    rows = []
    for p in data.get("postings", []):
        basis = ""
        if p["price"] is not None:
            basis = f"@ {p['price']} {p['price_currency']}"
        elif p["cost"] is not None:
            basis = f"{{{p['cost']} {p['cost_currency']}}}"
        amount = f"{Decimal(p['amount']):,.2f} {p['currency']}"
        rows.append([p["date"], p["description"], p["account"], amount, basis])

    out = render_rows(
        f"Audit Report: {text(data, 'currency')}",
        ["Date", "Description", "Account", "Amount", "Basis/Price"],
        rows,
        right=["Amount"],
    )
    if data.get("limited"):
        out += f"(Showing last {text(data, 'transactions')} transactions. Use --all to see more.)\n"
    return out


@report.command(
    "audit",
    description="Posting-level trace of the last transactions in one currency, oldest first",
    danger_level="safe",
    exit_codes=["NOT_FOUND", "CURRENCY_REQUIRED"],
    examples=[
        ("Audit the last 20 USD transactions", "bean report audit -c USD"),
        ("Audit every EUR transaction", "bean report audit -c EUR --all"),
    ],
    renderers={Format.PLAIN: render_audit},
)
def report_audit(args: AuditArgs, ctx: Ctx) -> AuditReport:
    tx_service = TransactionService(ledger_path(args.file, ctx))
    currency = args.currency or next(
        iter(tx_service.ledger_service.get_operating_currencies()), None
    )
    if currency is None:
        raise Exit.CURRENCY_REQUIRED("The ledger declares no operating_currency")

    txs = tx_service.list_transactions(currency=currency)
    txs.sort(key=lambda x: (x.date, x.payee or "", x.narration))
    limited = not args.all and len(txs) > args.limit
    if not args.all:
        txs = txs[-args.limit :] if args.limit else []

    postings = [
        AuditPosting(
            date=tx.date,
            description=f"{tx.payee}: {tx.narration}" if tx.payee else tx.narration,
            account=p.account,
            amount=p.units.number,
            currency=p.units.currency,
            price=p.price.number if p.price else None,
            price_currency=p.price.currency if p.price else None,
            cost=p.cost.number if p.cost else None,
            cost_currency=p.cost.currency if p.cost else None,
        )
        for tx in txs
        for p in tx.postings
        if p.units.currency == currency
    ]
    return AuditReport(currency=currency, transactions=len(txs), limited=limited, postings=postings)
