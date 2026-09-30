from datetime import date
from pathlib import Path

import agentyper as typer
from beancount.core import data
from beancount.parser import printer
from rich.markup import escape

from beancount_cli.adapters import to_core_balance, to_core_pad
from beancount_cli.commands.common import (
    _is_table_format,
    emit,
    get_ledger_file,
)
from beancount_cli.models import AccountModel, BalanceModel, PadBalanceModel
from beancount_cli.services import AccountService

app = typer.Agentyper(help="Manage accounts.")


def _format_open(m: AccountModel) -> str:
    return printer.format_entry(
        data.Open(
            meta={},
            date=m.open_date,
            account=str(m.name),
            currencies=[str(c) for c in m.currencies],
            booking=None,
        )
    )


@app.command(name="list")
def account_list(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
):
    """List all accounts."""
    actual_file = get_ledger_file(file)
    service = AccountService(actual_file)
    accounts = service.list_accounts()

    if _is_table_format():
        data = [
            {
                "Account": acc.name,
                "Open Date": str(acc.open_date),
                "Currencies": ", ".join(acc.currencies),
            }
            for acc in accounts
        ]
        typer.output(data, title=f"Accounts ({len(accounts)})")
    else:
        typer.output(accounts, title=f"Accounts ({len(accounts)})")


@app.command(name="create", mutating=True)
def account_create(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    name: str = typer.Option(..., "--name", "-n", help="Account name (e.g. Assets:Bank)"),
    currency_opt: str | None = typer.Option(
        None, "--currency", "-c", help="Currencies (comma-separated)"
    ),
    open_date: str | None = typer.Option(None, "--date", "-d", help="Open date (YYYY-MM-DD)"),
    target: Path | None = typer.Option(None, "--target", help="Override target file to write to"),
    dry_run: bool = False,
):
    """Create a new account."""
    d = date.fromisoformat(open_date) if open_date else date.today()

    currencies = [c.strip() for c in currency_opt.split(",")] if currency_opt else []
    model = AccountModel(name=name, open_date=d, currencies=currencies)
    entry = _format_open(model)
    data = {**model.model_dump(mode="json"), "entry": entry}
    if dry_run:
        return emit({**data, "file": None}, effect="would_create", human=escape(entry))
    try:
        written = AccountService(get_ledger_file(file)).create_account(model, target_file=target)
    except ValueError as e:
        typer.exit_error(str(e))
    return emit(
        {**data, "file": str(written)},
        effect="created",
        human=f"[green]Account {escape(name)} created in {escape(str(written))}.[/green]",
    )


@app.command(name="balance", mutating=True)
def account_balance(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    account: str = typer.Option(..., "--account", help="Account name (e.g. Assets:Bank)"),
    date: str = typer.Option(..., "--date", help="Balance date (YYYY-MM-DD)"),
    amount: str = typer.Option(..., "--amount", help="Balance amount (e.g. 1000.00)"),
    currency: str = typer.Option(..., "--currency", "-c", help="Currency code (e.g. USD)"),
    target: Path | None = typer.Option(None, "--target", help="Override target file to write to"),
    dry_run: bool = False,
):
    """Add a balance directive for an account."""
    model = BalanceModel(
        account=account,
        date=date,
        amount={"number": amount, "currency": currency},
    )
    entry = printer.format_entry(to_core_balance(model))
    data = {**model.model_dump(mode="json"), "entry": entry}
    if dry_run:
        return emit({**data, "file": None}, effect="would_create", human=escape(entry))
    written = AccountService(get_ledger_file(file)).add_balance(model, target_file=target)
    return emit(
        {**data, "file": str(written)},
        effect="created",
        human=f"[green]Balance check for {escape(str(model.account))} added to "
        f"{escape(str(written))}.[/green]",
    )


@app.command(name="pad-balance", mutating=True)
def account_pad_balance(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    account: str = typer.Option(
        ..., "--account", help="Account to adjust (e.g. Assets:BE:Wise:EUR)"
    ),
    amount: str = typer.Option(..., "--amount", help="Target balance amount (e.g. 1777.00)"),
    currency: str = typer.Option(
        ..., "--currency", "-c", help="Currency of the target balance (e.g. EUR)"
    ),
    pad_account: str = typer.Option(
        "Expenses:Other",
        "--pad-account",
        "-p",
        help="Account to absorb the difference (default: Expenses:Other)",
    ),
    balance_date: str | None = typer.Option(
        None,
        "--date",
        "-d",
        help="Date of the balance assertion (YYYY-MM-DD). Defaults to today.",
    ),
    pad_date: str | None = typer.Option(
        None,
        "--pad-date",
        help="Date of the pad directive (YYYY-MM-DD). Defaults to balance-date minus 1 day.",
    ),
    target: Path | None = typer.Option(None, "--target", help="Override target file to write to"),
    dry_run: bool = False,
):
    """Adjust an account balance using a Pad + Balance directive pair.

    Beancount inserts a synthetic transaction to bring ACCOUNT to AMOUNT
    on BALANCE-DATE.  The adjustment is automatically booked to PAD-ACCOUNT.

    Example:
      uv run bean account pad-balance \\
        --account Assets:BE:Wise:EUR \\
        --amount 1777 --currency EUR \\
        --pad-account Expenses:Other
    """
    b_date = date.fromisoformat(balance_date) if balance_date else date.today()
    p_date = date.fromisoformat(pad_date) if pad_date else None

    model = PadBalanceModel(
        balance_date=b_date,
        account=account,
        amount={"number": amount, "currency": currency},
        pad_account=pad_account,
        pad_date=p_date,
    )

    core_pad, core_balance = to_core_pad(model)
    entry = printer.format_entry(core_pad) + "\n" + printer.format_entry(core_balance)
    data = {**model.model_dump(mode="json"), "entry": entry}
    if dry_run:
        return emit({**data, "file": None}, effect="would_create", human=escape(entry))
    written = AccountService(get_ledger_file(file)).add_pad_balance(model, target_file=target)
    return emit(
        {**data, "file": str(written)},
        effect="created",
        human=f"[green]Pad + Balance for {escape(str(model.account))} → {model.amount.number} "
        f"{model.amount.currency} added to {escape(str(written))}.[/green]",
    )
