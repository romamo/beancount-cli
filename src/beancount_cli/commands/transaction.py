import json
from pathlib import Path

import agentyper as typer
from pydantic import TypeAdapter

from beancount_cli.commands.common import _is_table_format, get_ledger_file, read_json_input
from beancount_cli.models import TransactionModel
from beancount_cli.services import TransactionService

app = typer.Agentyper(help="Manage transactions.")


@app.command(name="list")
def tx_list(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    account: str | None = typer.Option(None, "--account", help="Filter by account regex"),
    payee: str | None = typer.Option(None, "--payee", "-p", help="Filter by payee regex"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag"),
    where: str | None = typer.Option(None, "--where", "-w", help="Custom BQL where clause"),
):
    """List transactions matching filters."""
    actual_file = get_ledger_file(ledger_file or file)
    service = TransactionService(actual_file)
    txs = service.list_transactions(
        account_regex=account, payee_regex=payee, tag=tag, bql_where=where
    )

    if _is_table_format():
        data = [
            {"Date": str(tx.date), "Payee": tx.payee or "", "Narration": tx.narration} for tx in txs
        ]
        typer.output(data, title=f"Transactions ({len(txs)})")
    else:
        # Let agentyper format direct Pydantic models to JSON/CSV naturally!
        typer.output([tx.model_dump(mode="json") for tx in txs], title=f"Transactions ({len(txs)})")


@app.command(name="add")
def tx_add(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    json_data: str = typer.Option(
        ..., "--json", "-j", help="JSON string data (or '-' to read from STDIN)"
    ),
    draft: bool = typer.Option(False, "--draft", help="Mark as pending (!)"),
    print_only: bool = typer.Option(False, "--print", help="Print only, do not write"),
    target: Path | None = typer.Option(None, "--target", help="Override target file to write to"),
):
    """Add a new transaction."""
    actual_file = get_ledger_file(ledger_file or file)
    service = TransactionService(actual_file)

    data = json.loads(read_json_input(json_data))

    if isinstance(data, list):
        ta = TypeAdapter(list[TransactionModel])
        models = ta.validate_python(data)
        for m in models:
            service.add_transaction(m, draft=draft, print_only=print_only, target_file=target)
    else:
        model = TransactionModel(**data)
        service.add_transaction(model, draft=draft, print_only=print_only, target_file=target)
