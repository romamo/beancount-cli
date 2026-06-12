import json
from pathlib import Path

import agentyper as typer

from beancount_cli.commands.common import _is_table_format, get_ledger_file
from beancount_cli.models import TransactionModel
from beancount_cli.services import TransactionService

app = typer.Agentyper(help="Manage transactions.")


@app.command(name="list")
def tx_list(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    account: str | None = typer.Option(None, "--account", help="Filter by account regex"),
    payee: str | None = typer.Option(None, "--payee", "-p", help="Filter by payee regex"),
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag"),
    where: str | None = typer.Option(None, "--where", "-w", help="Custom BQL where clause"),
    fields: str | None = typer.Option(
        None, "--fields", help="Comma-separated fields to include in JSON output"
    ),
):
    """List transactions matching filters."""
    actual_file = get_ledger_file(file)
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
        results = [tx.model_dump(mode="json") for tx in txs]
        if fields:
            fields_set = set(fields.split(","))
            results = [{k: v for k, v in r.items() if k in fields_set} for r in results]
        typer.output(results, title=f"Transactions ({len(txs)})")


@app.command(name="add", mutating=True)
def tx_add(
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    date: str = typer.Option(..., "--date", help="Transaction date (YYYY-MM-DD)"),
    narration: str = typer.Option(..., "--narration", help="Transaction narration"),
    postings: str = typer.Option(..., "--postings", help="JSON array of posting objects"),
    payee: str | None = typer.Option(None, "--payee", help="Payee name"),
    tags: str = typer.Option("[]", "--tags", help="JSON array of tags"),
    links: str = typer.Option("[]", "--links", help="JSON array of links"),
    draft: bool = typer.Option(False, "--draft", help="Mark as pending (!)"),
    print_only: bool = typer.Option(False, "--print", help="Print only, do not write"),
    dry_run: bool = False,
    target: Path | None = typer.Option(None, "--target", help="Override target file to write to"),
):
    """Add a new transaction."""
    model = TransactionModel(
        date=date,
        narration=narration,
        payee=payee,
        postings=json.loads(postings),
        tags=set(json.loads(tags)),
        links=set(json.loads(links)),
    )
    service = TransactionService(get_ledger_file(file))
    service.add_transaction(
        model, draft=draft, print_only=print_only or dry_run, target_file=target
    )
