import sys
from pathlib import Path

import agentyper as typer

from beancount_cli.commands.common import (
    _is_table_format,
    console,
    get_ledger_file,
    print_balances_table,
    print_holdings_table,
)
from beancount_cli.services import LedgerService, ReportService, TransactionService

app = typer.Agentyper(help="Generate simple reports.")


@app.command(name="balance-sheet")
def report_balance_sheet(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    convert: str | None = typer.Option(
        None, "--convert", "-c", help="Target currency for unified reporting"
    ),
    valuation: str = typer.Option(
        "market", "--valuation", help="Valuation strategy: 'market' or 'cost'"
    ),
):
    """Snapshot of Assets, Liabilities, and Equity."""
    if valuation not in ["market", "cost"]:
        console.print(
            f"[red]Error: Invalid valuation strategy '{valuation}'. Use 'market' or 'cost'.[/red]"
        )
        sys.exit(typer.EXIT_VALIDATION)

    actual_file = get_ledger_file(ledger_file or file)
    service = LedgerService(actual_file)
    report_service = ReportService(service)

    balances = report_service.get_balances(
        account_roots=["Assets", "Liabilities", "Equity"],
        convert_to=convert,
        valuation=valuation,
    )

    if _is_table_format():
        print_balances_table(balances, "Balance Sheet")
    else:
        data = []
        for acc, vals in balances.items():
            row = {"Account": acc}
            for curr, amt in vals["units"].items():
                row[f"Units {curr}"] = str(amt)
            for curr, amt in vals["cost"].items():
                row[f"Cost {curr}"] = str(amt)
            data.append(row)
        typer.output(data, title="Balance Sheet")


@app.command(name="trial-balance")
def report_trial_balance(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    convert: str | None = typer.Option(
        None, "--convert", "-c", help="Target currency for unified reporting"
    ),
    valuation: str = typer.Option(
        "market", "--valuation", help="Valuation strategy: 'market' or 'cost'"
    ),
):
    """All account balances for ledger-wide checks."""
    if valuation not in ["market", "cost"]:
        console.print(
            f"[red]Error: Invalid valuation strategy '{valuation}'. Use 'market' or 'cost'.[/red]"
        )
        sys.exit(typer.EXIT_VALIDATION)

    actual_file = get_ledger_file(ledger_file or file)
    service = LedgerService(actual_file)
    report_service = ReportService(service)

    balances = report_service.get_balances(convert_to=convert, valuation=valuation)

    if _is_table_format():
        print_balances_table(balances, "Trial Balance")
    else:
        data = []
        for acc, vals in balances.items():
            row = {"Account": acc}
            for curr, amt in vals["units"].items():
                row[f"Units {curr}"] = str(amt)
            for curr, amt in vals["cost"].items():
                row[f"Cost {curr}"] = str(amt)
            data.append(row)
        typer.output(data, title="Trial Balance")


@app.command(name="holdings")
def report_holdings(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    convert: str | None = typer.Option(
        None, "--convert", "-c", help="Target currency for unified reporting"
    ),
    valuation: str = typer.Option(
        "market", "--valuation", help="Valuation strategy: 'market' or 'cost'"
    ),
):
    """Asset positions with valuation and gains."""
    if valuation not in ["market", "cost"]:
        console.print(
            f"[red]Error: Invalid valuation strategy '{valuation}'. Use 'market' or 'cost'.[/red]"
        )
        sys.exit(typer.EXIT_VALIDATION)

    actual_file = get_ledger_file(ledger_file or file)
    service = LedgerService(actual_file)
    report_service = ReportService(service)

    target_currency = convert
    if not target_currency:
        ops = service.get_operating_currencies()
        if ops:
            target_currency = ops[0]

    targets = [target_currency] if target_currency else []
    holdings = report_service.get_holdings(valuation=valuation, target_currencies=targets)

    if _is_table_format():
        print_holdings_table(holdings, valuation, targets)
    else:
        # Also include JSON dicts or tabular structures
        flat_data = []
        for acc, h in holdings["accounts"].items():
            row = {"Account": acc}
            for curr, amt in h["units"].items():
                row[f"Units {curr}"] = str(amt)
            for target in targets:
                row[f"MarketValue {target}"] = str(h["market_values"].get(target, 0))
                row[f"CostBasis {target}"] = str(h["cost_basis"].get(target, 0))
                row[f"UnrealizedGain {target}"] = str(h["unrealized_gains"].get(target, 0))
            flat_data.append(row)
        typer.output(flat_data, title="Holdings")


@app.command(name="audit")
def report_audit(
    ledger_file: Path | None = typer.Argument(None, help="Path to ledger file"),
    currency: str | None = typer.Option(None, "--currency", "-c", help="Currency to audit"),
    file: Path | None = typer.Option(
        None, "--file", "-f", envvar="BEANCOUNT_FILE", help="Main beancount file"
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Limit number of transactions"),
    all_: bool = typer.Option(False, "--all", help="Show all transactions"),
):
    """Transaction-level trace for one currency."""
    actual_file = get_ledger_file(ledger_file or file)
    tx_service = TransactionService(actual_file)

    audit_currency = currency
    if not audit_currency:
        ops = tx_service.ledger_service.get_operating_currencies()
        if ops:
            audit_currency = ops[0]
        else:
            console.print(
                "[red]Error: Please specify a currency to audit with --currency/-c.[/red]"
            )
            sys.exit(typer.EXIT_VALIDATION)

    txs = tx_service.list_transactions(currency=audit_currency)
    txs.sort(key=lambda x: x.date, reverse=True)

    if not all_:
        txs = txs[:limit]

    if _is_table_format():
        from rich.table import Table

        table = Table(title=f"Audit Report: {audit_currency}")
        table.add_column("Date", style="green")
        table.add_column("Description")
        table.add_column("Account", style="cyan")
        table.add_column("Amount", justify="right")
        table.add_column("Basis/Price")

        for tx in txs:
            for p in tx.postings:
                if p.units and p.units.currency == audit_currency:
                    basis = ""
                    if p.price:
                        basis = f"@ {p.price.number} {p.price.currency}"
                    elif p.cost:
                        basis = f"{{{p.cost.number} {p.cost.currency}}}"

                    desc = f"{tx.payee}: {tx.narration}" if tx.payee else tx.narration
                    table.add_row(
                        str(tx.date),
                        desc,
                        p.account,
                        f"{p.units.number:,.2f} {p.units.currency}",
                        basis,
                    )
        console.print(table)
        if not all_ and len(txs) == limit:
            console.print(f"[dim](Showing last {limit} transactions. Use --all to see more.)[/dim]")
    else:
        data = []
        for tx in txs:
            for p in tx.postings:
                if p.units and p.units.currency == audit_currency:
                    data.append(
                        {
                            "Date": str(tx.date),
                            "Description": f"{tx.payee}: {tx.narration}"
                            if tx.payee
                            else tx.narration,
                            "Account": p.account,
                            "Amount": str(p.units.number),
                            "Currency": p.units.currency,
                            "Price": str(p.price.number) if p.price else "",
                            "Cost": str(p.cost.number) if p.cost else "",
                        }
                    )
        typer.output(data, title=f"Audit {audit_currency}")
