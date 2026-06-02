import json
import sys
from datetime import date
from pathlib import Path

import agentyper as typer
from pydantic import TypeAdapter

from beancount_cli.commands.common import (
    _is_table_format,
    console,
    get_ledger_file,
    read_json_input,
)
from beancount_cli.models import AccountModel, BalanceModel, PadBalanceModel
from beancount_cli.services import AccountService

app = typer.Agentyper(help="Manage accounts.")


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


@app.command(name="create")
def account_create(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    name: str | None = typer.Option(None, "--name", "-n", help="Account name (e.g. Assets:Bank)"),
    currency_opt: str | None = typer.Option(
        None, "--currency", "-c", help="Currencies (comma-separated)"
    ),
    open_date: str | None = typer.Option(None, "--date", "-d", help="Open date (YYYY-MM-DD)"),
    json_data: str | None = typer.Option(
        None, "--input", "-i", help="JSON string data (or '-' to read from STDIN)"
    ),
    target: Path | None = typer.Option(None, "--target", help="Override target file to write to"),
):
    """Create a new account."""
    actual_file = get_ledger_file(file)
    service = AccountService(actual_file)

    if json_data:
        data_input = json.loads(read_json_input(json_data))
        if isinstance(data_input, list):
            ta = TypeAdapter(list[AccountModel])
            models = ta.validate_python(data_input)
            for m in models:
                service.create_account(m, target_file=target)
                console.print(f"[green]Account {m.name} created.[/green]")
        else:
            model = AccountModel(**data_input)
            service.create_account(model, target_file=target)
            console.print(f"[green]Account {model.name} created.[/green]")
    else:
        if not name:
            console.print("[red]Error: --name is required if not using --input.[/red]")
            sys.exit(typer.EXIT_VALIDATION)

        d = date.today()
        if open_date:
            d = date.fromisoformat(open_date)

        currencies = [c.strip() for c in currency_opt.split(",")] if currency_opt else []
        model = AccountModel(name=name, open_date=d, currencies=currencies)
        service.create_account(model, target_file=target)
        console.print(f"[green]Account {name} created.[/green]")


@app.command(name="balance")
def account_balance(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    json_data: str = typer.Option(
        ..., "--input", "-i", help="JSON string data (or '-' to read from STDIN)"
    ),
    target: Path | None = typer.Option(None, "--target", help="Override target file to write to"),
):
    """Add a balance directive for an account."""
    actual_file = get_ledger_file(file)
    service = AccountService(actual_file)

    data_input = json.loads(read_json_input(json_data))
    model = BalanceModel(**data_input)
    service.add_balance(model, target_file=target)
    console.print(f"[green]Balance check for {model.account} added.[/green]")


@app.command(name="pad-balance")
def account_pad_balance(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    account: str | None = typer.Option(
        None, "--account", help="Account to adjust (e.g. Assets:BE:Wise:EUR)"
    ),
    amount: str | None = typer.Option(
        None, "--amount", help="Target balance amount (e.g. 1777.00)"
    ),
    currency: str | None = typer.Option(
        None, "--currency", "-c", help="Currency of the target balance (e.g. EUR)"
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
    json_data: str | None = typer.Option(
        None, "--input", "-i", help="JSON string data (or '-' to read from STDIN)"
    ),
    target: Path | None = typer.Option(None, "--target", help="Override target file to write to"),
):
    """Adjust an account balance using a Pad + Balance directive pair.

    Beancount inserts a synthetic transaction to bring ACCOUNT to AMOUNT
    on BALANCE-DATE.  The adjustment is automatically booked to PAD-ACCOUNT.

    Example:
      uv run bean account pad-balance \\
        --account Assets:BE:Wise:EUR \\
        --amount 1777 --currency EUR \\
        --pad-account Expenses:Other

    JSON example (for agent pipelines):
      echo '{"account": "Assets:BE:Wise:EUR", "amount": {"number": 1777, "currency": "EUR"}, \\
             "pad_account": "Expenses:Other", "balance_date": "2026-06-02"}' \\
        | uv run bean account pad-balance --input -
    """
    actual_file = get_ledger_file(file)
    service = AccountService(actual_file)

    if json_data:
        data_input = json.loads(read_json_input(json_data))
        model = PadBalanceModel(**data_input)
    else:
        missing = [
            f
            for f, v in [
                ("--account", account),
                ("--amount", amount),
                ("--currency", currency),
            ]
            if not v
        ]
        if missing:
            console.print(
                f"[red]Error: {', '.join(missing)} required when not using --input.[/red]"
            )
            sys.exit(typer.EXIT_VALIDATION)

        b_date = date.fromisoformat(balance_date) if balance_date else date.today()
        p_date = date.fromisoformat(pad_date) if pad_date else None

        model = PadBalanceModel(
            balance_date=b_date,
            account=account,  # type: ignore[arg-type]
            amount={"number": amount, "currency": currency},
            pad_account=pad_account,
            pad_date=p_date,
        )

    service.add_pad_balance(model, target_file=target)
    console.print(
        f"[green]Pad + Balance for {model.account} → {model.amount.number} "
        f"{model.amount.currency} added.[/green]"
    )
