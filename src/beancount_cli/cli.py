import json
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree

from beancount_cli.models import AccountModel, TransactionModel
from beancount_cli.services import (
    AccountService,
    CommodityService,
    LedgerService,
    MapService,
    ReportService,
    TransactionService,
)


def print_balances_table(balances, title) -> None:
    table = Table(title=f"[bold]{title}[/bold]")
    table.add_column("Account", style="cyan")
    table.add_column("Balance", justify="right")

    totals_debit: dict[str, Decimal] = {}
    totals_credit: dict[str, Decimal] = {}

    for account in sorted(balances.keys()):
        account_data = balances[account]
        bal_units = account_data["units"]
        bal_cost = account_data["cost"]

        # Format rows using units
        bal_str = ", ".join(f"{amt:,.2f} {curr}" for curr, amt in sorted(bal_units.items()))
        table.add_row(account, bal_str)

        # Aggregate totals using COST to verify double-entry balance
        if (
            account in ["Assets", "Liabilities", "Equity", "Income", "Expenses"]
            or ":" not in account
        ):
            for curr, amt in bal_cost.items():
                if amt > 0:
                    totals_debit[curr] = totals_debit.get(curr, Decimal(0)) + amt
                else:
                    totals_credit[curr] = totals_credit.get(curr, Decimal(0)) + amt

    if totals_debit or totals_credit:
        table.add_section()

        all_currencies = sorted(set(totals_debit.keys()) | set(totals_credit.keys()))
        for curr in all_currencies:
            debit = totals_debit.get(curr, Decimal(0))
            credit = totals_credit.get(curr, Decimal(0))
            diff = debit + credit

            if abs(diff) < Decimal("0.0001"):
                status = "[green]✓ Balanced[/green]"
            else:
                status = f"[yellow]Exposure: {diff:,.2f} {curr}[/yellow]"

            table.add_row(
                f"[bold]NET POSITION {curr}[/bold]",
                f"{debit:,.2f} (Dr) | {credit:,.2f} (Cr) | {status}",
            )

    console.print(table)
    if any(
        abs(totals_debit.get(c, Decimal(0)) + totals_credit.get(c, Decimal(0))) >= Decimal("0.0001")
        for c in all_currencies
    ):
        console.print(
            "[dim]Note: Perpetual positions in specific currencies are normal where "
            "exchanges occur at market prices (@@).[/dim]"
        )


def print_holdings_table(holdings_data, valuation_method, target_currencies) -> None:
    title = f"[bold]Portfolio Holdings ({valuation_method.capitalize()} Value)[/bold]"
    table = Table(title=title)
    table.add_column("Account", style="cyan")
    table.add_column("Holdings", justify="left")

    # Add columns for each target currency (usually just one)
    for curr in target_currencies:
        table.add_column(f"Value ({curr})", justify="right")
        table.add_column(f"Cost ({curr})", justify="right")
        table.add_column("Gain (%)", justify="right")

    for acc in sorted(holdings_data["accounts"].keys()):
        data = holdings_data["accounts"][acc]
        units_str = ", ".join(f"{v:,.2f} {k}" for k, v in sorted(data["units"].items()))

        row = [acc, units_str]
        for curr in target_currencies:
            m_val = data["market_values"].get(curr, Decimal(0))
            c_val = data["cost_basis"].get(curr, Decimal(0))
            gain = data["unrealized_gains"].get(curr, Decimal(0))

            gain_pct = (gain / c_val * 100) if c_val != 0 else Decimal(0)

            # Coloring for gains
            gain_color = "green" if gain >= 0 else "red"
            gain_str = f"[{gain_color}]{gain:,.2f} ({gain_pct:.1f}%)[/{gain_color}]"

            row.extend([f"{m_val:,.2f}", f"{c_val:,.2f}", gain_str])
        table.add_row(*row)

    if target_currencies:
        table.add_section()
        footer_row = ["[bold]TOTAL[/bold]", ""]
        for curr in target_currencies:
            totals = holdings_data["totals"].get(curr, {})
            m_total = totals.get("market", Decimal(0))
            c_total = totals.get("cost", Decimal(0))
            gain_total = totals.get("gain", Decimal(0))
            gain_pct_total = (gain_total / c_total * 100) if c_total != 0 else Decimal(0)

            gain_color = "green" if gain_total >= 0 else "red"

            footer_row.extend(
                [
                    f"[bold]{m_total:,.2f}[/bold]",
                    f"[bold]{c_total:,.2f}[/bold]",
                    f"[bold][{gain_color}]{gain_total:,.2f} "
                    f"({gain_pct_total:.1f}%)[/{gain_color}][/bold]",
                ]
            )
        table.add_row(*footer_row)

    console.print(table)


app = typer.Typer(help="Beancount CLI tool for managing ledgers.")
tx_app = typer.Typer(help="Manage transactions.")
app.add_typer(tx_app, name="transaction")

console = Console()


def get_ledger_file(ctx: typer.Context, override: Path | None = None) -> Path:
    import os

    # 1. Explicit override (positional arg or --file option from main)
    if override:
        return override

    path_from_option = ctx.obj.get("ledger_file") if ctx.obj else None
    if path_from_option:
        return path_from_option

    # 2. Check BEANCOUNT_FILE directly (redundant if main() ran, but safe)
    env_file = os.environ.get("BEANCOUNT_FILE")
    if env_file:
        return Path(env_file)

    # 3. BEANCOUNT_PATH/main.beancount
    env_path = os.environ.get("BEANCOUNT_PATH")
    if env_path:
        p = Path(env_path) / "main.beancount"
        if p.exists():
            return p

    # 4. ./main.beancount
    p = Path("main.beancount")
    if p.exists():
        return p

    console.print(
        "[red]Error: No ledger file found. Specify file as argument, use --file, "
        "or set BEANCOUNT_FILE/BEANCOUNT_PATH.[/red]"
    )
    raise typer.Exit(code=1)


@app.callback()
def main(
    ctx: typer.Context,
    ledger_file: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="Path to main.beancount file", envvar="BEANCOUNT_FILE"),
    ] = None,
):
    ctx.obj = {"ledger_file": ledger_file}


@app.command("check")
def check_cmd(
    ctx: typer.Context,
    ledger_file: Annotated[Path | None, typer.Argument(help="Path to ledger file")] = None,
):
    """
    Validate the ledger file (wrapper around bean-check).
    """
    ledger_file = get_ledger_file(ctx, ledger_file)
    service = LedgerService(ledger_file)
    service.load()

    if not service.errors:
        console.print("[green]No errors found.[/green]")
    else:
        for error in service.errors:
            # error is usually a namedtuple (source, message, entry)
            # source is {filename, linenos}
            source = error.source
            loc = f"{source['filename']}:{source['lineno']}" if source else "?"
            console.print(f"[red]{loc}: {error.message}[/red]")
        raise typer.Exit(1)


@app.command("tree", help="Visualize the tree of included files")
def map_cmd(
    ctx: typer.Context,
    ledger_file: Annotated[Path | None, typer.Argument(help="Path to ledger file")] = None,
):
    """
    Show tree of included files.
    """
    ledger_file = get_ledger_file(ctx, ledger_file)
    service = MapService(ledger_file)
    tree_dict = service.get_include_tree()

    def build_tree(data: dict, tree_node: Tree):
        for path, children in data.items():
            node = tree_node.add(f"[yellow]{path}[/yellow]")
            build_tree(children, node)

    root = Tree(f"[bold blue]{ledger_file}[/bold blue]")
    build_tree(tree_dict, root)
    console.print(root)


@app.command("report")
def report_cmd(
    ctx: typer.Context,
    report_type: Annotated[
        str,
        typer.Argument(
            help="Type of report: balance-sheet (bs), trial-balance (trial), audit, holdings"
        ),
    ],
    arg1: Annotated[
        str | None, typer.Argument(help="Currency (for audit) or Ledger File (for others)")
    ] = None,
    arg2: Annotated[
        str | None, typer.Argument(help="Ledger File (only if arg1 is Currency)")
    ] = None,
    ledger_file: Annotated[
        Path | None, typer.Option("--file", "-f", help="Path to ledger file")
    ] = None,
    convert: Annotated[
        str | None, typer.Option("--convert", "-c", help="Target currency for unified reporting")
    ] = None,
    valuation: Annotated[
        str,
        typer.Option(
            "--valuation",
            "-v",
            help="Valuation strategy: 'market' (current prices) or 'cost' (historical basis)",
        ),
    ] = "market",
    limit: Annotated[
        int, typer.Option("--limit", "-l", help="Limit number of transactions (audit only)")
    ] = 20,
    all_tx: Annotated[
        bool, typer.Option("--all", help="Show all transactions (audit only)")
    ] = False,
):
    """
    Generate simple reports.
    """
    # Logic to handle positional arguments:
    # 1. report audit [CURRENCY] [FILE]
    # 2. report trial-balance [FILE]
    audit_currency = None
    if report_type == "audit":
        if arg1 and arg2:
            # report audit [CURRENCY] [FILE]
            audit_currency = arg1
            if not ledger_file:
                ledger_file = Path(arg2)
        elif arg1:
            # One argument: check if it's a currency or a path
            if "." in arg1 or "/" in arg1:
                if not ledger_file:
                    ledger_file = Path(arg1)
                audit_currency = None
            else:
                audit_currency = arg1
    elif arg1 and not ledger_file:
        # For non-audit reports, arg1 is always the file if provided
        ledger_file = Path(arg1)

    ledger_file = get_ledger_file(ctx, ledger_file)
    service = LedgerService(ledger_file)
    report_service = ReportService(service)

    # Normalize aliases
    report_type = report_type.lower()
    if report_type in ["trial", "trial-balance"]:
        report_type = "trial-balance"
    if report_type in ["bs", "balance-sheet", "balance"]:
        report_type = "balance-sheet"

    if valuation not in ["market", "cost"]:
        console.print(
            f"[red]Error: Invalid valuation strategy '{valuation}'. Use 'market' or 'cost'.[/red]"
        )
        raise typer.Exit(1)

    if report_type == "balance-sheet":
        # Balance Sheet follows Accounting Equation: Assets, Liabilities, Equity
        balances = report_service.get_balances(
            account_roots=["Assets", "Liabilities", "Equity"],
            convert_to=convert,
            valuation=valuation,
        )
        print_balances_table(balances, "Balance Sheet")
        return

    if report_type in ["trial-balance", "balances"]:
        # Trial Balance includes all accounts (including Income/Expenses)
        balances = report_service.get_balances(convert_to=convert, valuation=valuation)
        print_balances_table(balances, "Trial Balance")
        return

    if report_type == "holdings":
        # Resolve target currency: 1. --convert, 2. first operating_currency, 3. None
        target_currency = convert
        if not target_currency:
            ops = service.get_operating_currencies()
            if ops:
                target_currency = ops[0]

        targets = [target_currency] if target_currency else []
        holdings = report_service.get_holdings(valuation=valuation, target_currencies=targets)
        print_holdings_table(holdings, valuation, targets)
        return

    if report_type == "audit":
        if not audit_currency:
            console.print(
                "[red]Error: 'audit' report requires a currency "
                "(e.g., bean-cli report audit EUR).[/red]"
            )
            raise typer.Exit(1)

        tx_service = TransactionService(ledger_file)
        # Fetch all
        txs = tx_service.list_transactions(currency=audit_currency)
        txs.sort(key=lambda x: x.date, reverse=True)

        if not all_tx:
            txs = txs[:limit]

        from rich.table import Table

        table = Table(title=f"Audit Report: {audit_currency}")
        table.add_column("Date", style="green")
        table.add_column("Description")
        table.add_column("Account", style="cyan")
        table.add_column("Amount", justify="right")
        table.add_column("Basis/Price")

        for tx in txs:
            for p in tx.postings:
                if p.units.currency == audit_currency:
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
        if not all_tx and len(txs) == limit:
            console.print(f"[dim](Showing last {limit} transactions. Use --all to see more.)[/dim]")
        return

    console.print(f"[red]Error: Unknown report type '{report_type}'[/red]")
    raise typer.Exit(1)


@tx_app.command("list")
def list_tx(
    ctx: typer.Context,
    ledger_file: Annotated[Path | None, typer.Argument(help="Path to ledger file")] = None,
    account: Annotated[
        str | None, typer.Option("--account", "-a", help="Filter by account regex")
    ] = None,
    payee: Annotated[
        str | None, typer.Option("--payee", "-p", help="Filter by payee regex")
    ] = None,
    tag: Annotated[str | None, typer.Option("--tag", "-t", help="Filter by tag")] = None,
    where: Annotated[
        str | None, typer.Option("--where", "-w", help="Custom BQL where clause")
    ] = None,
):
    """
    List transactions matching filters.
    """
    ledger_file = get_ledger_file(ctx, ledger_file)
    service = TransactionService(ledger_file)

    txs = service.list_transactions(
        account_regex=account, payee_regex=payee, tag=tag, bql_where=where
    )

    table = Table(title=f"Transactions ({len(txs)})")
    table.add_column("Date", style="green")
    table.add_column("Payee", style="bold")
    table.add_column("Narration")
    # table.add_column("Postings")

    for tx in txs:
        # Simplified view
        table.add_row(str(tx.date), tx.payee or "", tx.narration)
    console.print(table)


@tx_app.command("add")
def add_tx(
    ctx: typer.Context,
    ledger_file: Annotated[Path | None, typer.Argument(help="Path to ledger file")] = None,
    json_data: Annotated[
        str | None, typer.Option("--json", "-j", help="JSON data (or '-' for stdin)")
    ] = None,
    draft: Annotated[bool, typer.Option("--draft", help="Mark as pending (!)")] = False,
    print_only: Annotated[bool, typer.Option("--print", help="Print only, do not write")] = False,
):
    """
    Add a new transaction.
    """
    ledger_file = get_ledger_file(ctx, ledger_file)
    service = TransactionService(ledger_file)

    if json_data:
        if json_data == "-":
            # Read from stdin
            content = sys.stdin.read()
        else:
            content = json_data

        data = json.loads(content)
        model = TransactionModel(**data)

        service.add_transaction(model, draft=draft, print_only=print_only)
    else:
        console.print(
            "[yellow]Interactive mode not implemented in this version. Use --json.[/yellow]"
        )


@tx_app.command("schema")
def tx_schema():
    """
    Output the JSON schema for transactions (useful for AI agents).
    """
    import json

    from beancount_cli.models import TransactionModel

    schema = TransactionModel.model_json_schema()
    console.print(json.dumps(schema, indent=2))


# Account Commands
account_app = typer.Typer(help="Manage accounts.")
app.add_typer(account_app, name="account")


@account_app.command("list")
def list_accounts(
    ctx: typer.Context,
    ledger_file: Annotated[Path | None, typer.Argument(help="Path to ledger file")] = None,
):
    """
    List all accounts.
    """
    ledger_file = get_ledger_file(ctx, ledger_file)
    service = AccountService(ledger_file)
    accounts = service.list_accounts()

    table = Table(title=f"Accounts ({len(accounts)})")
    table.add_column("Account", style="cyan")
    table.add_column("Open Date")
    table.add_column("Currencies")

    for acc in accounts:
        curr_str = ", ".join(acc.currencies)
        table.add_row(acc.name, str(acc.open_date), curr_str)
    console.print(table)


@account_app.command("create")
def create_account(
    ctx: typer.Context,
    ledger_file: Annotated[Path | None, typer.Argument(help="Path to ledger file")] = None,
    name: Annotated[
        str, typer.Option("--name", "-n", help="Account name (e.g. Assets:Bank)")
    ] = ...,  # type: ignore
    currency: Annotated[
        list[str] | None, typer.Option("--currency", "-c", help="Currencies")
    ] = None,
    open_date: Annotated[
        str | None, typer.Option("--date", "-d", help="Open date (YYYY-MM-DD)")
    ] = None,
):
    """
    Create a new account.
    """
    ledger_file = get_ledger_file(ctx, ledger_file)
    service = AccountService(ledger_file)

    # Parse date
    d = date.today()
    if open_date:
        # Quick hack or use datetime
        # let's use dateutil or datetime
        d = date.fromisoformat(open_date)

    model = AccountModel(name=name, open_date=d, currencies=currency or [])

    service.create_account(model)
    console.print(f"[green]Account {name} created.[/green]")


# Commodity Commands
commodity_app = typer.Typer(help="Manage commodities.")
app.add_typer(commodity_app, name="commodity")


@commodity_app.command("create")
def create_commodity(
    ctx: typer.Context,
    currency: Annotated[str, typer.Argument(help="Currency code (e.g. USD)")],
    ledger_file: Annotated[Path | None, typer.Argument(help="Path to ledger file")] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Full name")] = None,
):
    """
    Create a new commodity.
    """
    ledger_file = get_ledger_file(ctx, ledger_file)
    service = CommodityService(ledger_file)

    service.create_commodity(currency, name=name)
    console.print(f"[green]Commodity {currency} created.[/green]")


@app.command("format", help="Format ledger file(s)")
def format_cmd(
    ctx: typer.Context,
    ledger_file: Annotated[Path | None, typer.Argument(help="Path to ledger file")] = None,
    recursive: Annotated[
        bool,
        typer.Option(
            "--recursive",
            "-r",
            help="Format all included files (not implemented in bean-format Wrapper yet)",
        ),
    ] = False,
):
    """
    Format the ledger file using bean-format.
    """
    ledger_file = get_ledger_file(ctx, ledger_file)

    # Check if bean-format is available
    try:
        # We use subprocess because bean-format is a script, not easily
        # importable as a library function without internal knowledge
        cmd = ["bean-format", "-c", "50", str(ledger_file)]

        # Capture output or let it print? bean-format prints to stdout by default.
        # We want to write back to file usually, but safely.
        # bean-format doesn't have an --in-place flag in all versions?
        # Let's check help again... it has -o.

        # To emulate in-place safely:
        # 1. format to temp, 2. move temp to original

        import shutil
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        cmd = ["bean-format", "-c", "50", "-o", str(tmp_path), str(ledger_file)]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

        # If successful, replace
        shutil.move(str(tmp_path), str(ledger_file))
        console.print(f"[green]Formatted {ledger_file}[/green]")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error running bean-format: {e.stderr}[/red]")
        raise typer.Exit(1) from e


@app.command("price", help="Fetch and update prices")
def price_cmd(
    ctx: typer.Context,
    ledger_file: Annotated[Path | None, typer.Argument(help="Path to ledger file")] = None,
    update: Annotated[bool, typer.Option("--update", "-u", help="Update prices in ledger")] = False,
):
    """
    Fetch prices for commodities in the ledger.
    """
    ledger_file = get_ledger_file(ctx, ledger_file)

    # 1. Identify commodities needing prices (optionally)
    # bean-price usually takes the ledger file as input to find commodities

    console.print(f"Fetching prices for {ledger_file}...")

    try:
        # bean-price <file>
        cmd = ["bean-price", str(ledger_file)]

        # If update is true, we append to price DB?
        # Usually prices are stored in a separate price.beancount file included in main.
        # We need to know WHERE to save prices.
        # Let's check for 'price' option in bean-price or just append to a configured file.

        # For now, simplest agent workflow:
        # 1. Run bean-price
        # 2. Append output to 'prices.beancount' (if exists) or 'main.beancount'

        # Let's assume user handles the "where" by configuring 'price' command behavior
        # via simple append for now.

        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        prices_output = result.stdout.strip()

        if not prices_output:
            console.print("[yellow]No new prices found.[/yellow]")
            return

        if update:
            # Determine target file.
            # We can look for an include "prices.beancount" or just append to main.
            # Best effort: if 'prices.beancount' is included, append there.

            # Simple heuristic service
            service = MapService(ledger_file)
            tree = service.get_include_tree()

            target_price_file = ledger_file

            # recursive search for a file named *price*
            def find_price_file(t):
                for k, v in t.items():
                    if "price" in Path(k).name.lower() and "beancount" in k:
                        return Path(k)
                    res = find_price_file(v)
                    if res:
                        return res
                return None

            found = find_price_file(tree)
            if found:
                target_price_file = found

            from datetime import datetime

            with open(target_price_file, "a") as f:
                f.write(f"\n\n; Prices fetched {datetime.now().isoformat()}\n")
                f.write(prices_output)
                f.write("\n")

            console.print(
                f"[green]Appended {len(prices_output.splitlines())} prices to "
                f"{target_price_file.name}[/green]"
            )
        else:
            console.print(prices_output)

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error running bean-price: {e.stderr}[/red]")
        raise typer.Exit(1) from e
    except FileNotFoundError:
        console.print("[red]Error: bean-price not found. Is it installed?[/red]")
        raise typer.Exit(1) from None


if __name__ == "__main__":
    app()
