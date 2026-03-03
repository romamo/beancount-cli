import json
import sys
from datetime import date
from pathlib import Path

import agentyper as typer
from pydantic import TypeAdapter

from beancount_cli.commands.common import _is_table_format, console, get_ledger_file
from beancount_cli.models import AccountModel
from beancount_cli.services import AccountService

app = typer.Agentyper(help="Manage accounts.")


@app.command(name="list")
def account_list(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
):
    """List all accounts."""
    actual_file = get_ledger_file(ledger_file or file)
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
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    name: str | None = typer.Option(None, "--name", "-n", help="Account name (e.g. Assets:Bank)"),
    currency_opt: str | None = typer.Option(
        None, "--currency", "-c", help="Currencies (comma-separated)"
    ),
    open_date: str | None = typer.Option(None, "--date", "-d", help="Open date (YYYY-MM-DD)"),
    json_data: str | None = typer.Option(
        None, "--json", "-j", help="JSON string data (or '-' to read from STDIN)"
    ),
):
    """Create a new account."""
    actual_file = get_ledger_file(ledger_file or file)
    service = AccountService(actual_file)

    if json_data:
        if json_data == "-":
            content = sys.stdin.read()
        else:
            content = json_data

        data_input = json.loads(content)
        if isinstance(data_input, list):
            ta = TypeAdapter(list[AccountModel])
            models = ta.validate_python(data_input)
            for m in models:
                service.create_account(m)
                console.print(f"[green]Account {m.name} created.[/green]")
        else:
            model = AccountModel(**data_input)
            service.create_account(model)
            console.print(f"[green]Account {model.name} created.[/green]")
    else:
        if not name:
            console.print("[red]Error: --name is required if not using --json.[/red]")
            sys.exit(typer.EXIT_VALIDATION)

        d = date.today()
        if open_date:
            d = date.fromisoformat(open_date)

        currencies = [c.strip() for c in currency_opt.split(",")] if currency_opt else []
        model = AccountModel(name=name, open_date=d, currencies=currencies)
        service.create_account(model)
        console.print(f"[green]Account {name} created.[/green]")
