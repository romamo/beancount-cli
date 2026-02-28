import argparse
import json
import os
import shlex
import subprocess  # nosec B404
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import argcomplete

from beancount_cli import __version__
from beancount_cli.config import CliConfig
from beancount_cli.formatting import Console, Table, Tree, render_output
from beancount_cli.models import AccountModel, TransactionModel
from beancount_cli.services import (
    AccountService,
    CommodityService,
    LedgerService,
    MapService,
    ReportService,
    TransactionService,
)

console = Console()
_files_completer = argcomplete.completers.FilesCompleter()
_FILE_OPTIONS = {"--file", "-f"}


def get_ledger_file(override: Path | None = None) -> Path:
    config = CliConfig()
    path = config.get_resolved_ledger(override)
    if not path or not path.exists():
        console.print(
            "[red]Error: No ledger file found. Specify file as argument, use --file, "
            "or set BEANCOUNT_FILE/BEANCOUNT_PATH.[/red]"
        )
        sys.exit(1)
    return path


def _comp_line_tokens(comp_line: str | None = None) -> list[str]:
    raw = comp_line if comp_line is not None else os.environ.get("COMP_LINE", "")
    try:
        return shlex.split(raw)
    except ValueError:
        # Fall back to simple splitting for incomplete quotes during interactive completion.
        return raw.split()


def _file_option_already_present(comp_line: str | None = None) -> bool:
    return any(token in _FILE_OPTIONS for token in _comp_line_tokens(comp_line))


def _completion_validator(completion: str, prefix: str) -> bool:
    # Completion policy: after --file/-f appears once, do not suggest it again.
    if completion in _FILE_OPTIONS and _file_option_already_present():
        return False
    return completion.startswith(prefix)


def _resolve_report_completion_ledger(parsed_args: argparse.Namespace) -> Path | None:
    ledger_file = getattr(parsed_args, "ledger_file", None)
    if isinstance(ledger_file, Path) and ledger_file.exists():
        return ledger_file

    pos_ledger_file = getattr(parsed_args, "pos_ledger_file", None)
    if isinstance(pos_ledger_file, Path) and pos_ledger_file.exists():
        return pos_ledger_file

    config = CliConfig()
    fallback = config.get_resolved_ledger()
    if fallback and fallback.exists():
        return fallback

    return None


def _report_arg1_completer(prefix: str, parsed_args: argparse.Namespace, **kwargs) -> list[str]:
    # This completer is attached to the audit currency positional.
    ledger_file = _resolve_report_completion_ledger(parsed_args)
    if not ledger_file:
        return []

    from beancount.core import data

    service = LedgerService(ledger_file)
    service.load()

    currencies = set(service.get_operating_currencies())
    currencies.update(service.get_commodities())
    for entry in service.entries:
        if isinstance(entry, data.Transaction):
            for posting in entry.postings:
                if posting.units:
                    currencies.add(posting.units.currency)
                if posting.cost and posting.cost.currency is not None:
                    currencies.add(posting.cost.currency)
                if posting.price:
                    currencies.add(posting.price.currency)

    normalized_prefix = prefix.upper()
    return sorted(c for c in currencies if c.upper().startswith(normalized_prefix))


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
        for c in sorted(list(totals_debit.keys()) + list(totals_credit.keys()))
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


def check_cmd(args: argparse.Namespace):
    ledger_file = get_ledger_file(getattr(args, "pos_ledger_file", None) or args.ledger_file)
    service = LedgerService(ledger_file)
    service.load()

    if not service.errors:
        console.print("[green]No errors found.[/green]")
    else:
        for error in service.errors:
            source = error.source
            loc = f"{source['filename']}:{source['lineno']}" if source else "?"
            console.print(f"[red]{loc}: {error.message}[/red]")
        sys.exit(1)


def map_cmd(args: argparse.Namespace):
    ledger_file = get_ledger_file(getattr(args, "pos_ledger_file", None) or args.ledger_file)
    service = MapService(ledger_file)
    tree_dict = service.get_include_tree()

    def build_tree(data: dict, tree_node: Tree):
        for path, children in data.items():
            node = tree_node.add(f"[yellow]{path}[/yellow]")
            build_tree(children, node)

    root = Tree(f"[bold blue]{ledger_file}[/bold blue]")
    build_tree(tree_dict, root)
    console.print(root)


def report_cmd(args: argparse.Namespace):
    report_type = args.report_type
    ledger_file = get_ledger_file(getattr(args, "pos_ledger_file", None) or args.ledger_file)
    service = LedgerService(ledger_file)
    report_service = ReportService(service)
    audit_currency = getattr(args, "audit_currency", None)

    valuation = getattr(args, "valuation", "market")
    convert = getattr(args, "convert", None)

    if report_type != "audit" and valuation not in ["market", "cost"]:
        console.print(
            f"[red]Error: Invalid valuation strategy '{valuation}'. Use 'market' or 'cost'.[/red]"
        )
        sys.exit(1)

    format_type = getattr(args, "format", "table")
    if report_type == "balance-sheet":
        balances = report_service.get_balances(
            account_roots=["Assets", "Liabilities", "Equity"],
            convert_to=convert,
            valuation=valuation,
        )
        if format_type == "table":
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
            render_output(data, format_type=format_type, title="Balance Sheet", console=console)
        return

    if report_type == "trial-balance":
        balances = report_service.get_balances(convert_to=convert, valuation=valuation)
        if format_type == "table":
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
            render_output(data, format_type=format_type, title="Trial Balance", console=console)
        return

    if report_type == "holdings":
        target_currency = convert
        if not target_currency:
            ops = service.get_operating_currencies()
            if ops:
                target_currency = ops[0]

        targets = [target_currency] if target_currency else []
        holdings = report_service.get_holdings(valuation=valuation, target_currencies=targets)

        if format_type == "table":
            print_holdings_table(holdings, valuation, targets)
        else:
            # Flatten holdings for CSV/JSON
            data = []
            for acc, h in holdings["accounts"].items():
                row = {"Account": acc}
                for curr, amt in h["units"].items():
                    row[f"Units {curr}"] = str(amt)
                for target in targets:
                    row[f"MarketValue {target}"] = str(h["market_values"].get(target, 0))
                    row[f"CostBasis {target}"] = str(h["cost_basis"].get(target, 0))
                    row[f"UnrealizedGain {target}"] = str(h["unrealized_gains"].get(target, 0))
                data.append(row)
            # We don't include totals in the flat list for CSV to keep it purely tabular
            # But for JSON we might want to include them?
            # render_output handles dict too.
            if format_type == "json":
                render_output(holdings, format_type="json", console=console)
            else:
                render_output(data, format_type=format_type, title="Holdings", console=console)
        return

    if report_type == "audit":
        if not audit_currency:
            console.print(
                "[red]Error: 'audit' report requires a currency "
                "(e.g., bean report audit EUR).[/red]"
            )
            sys.exit(1)

        tx_service = TransactionService(ledger_file)
        txs = tx_service.list_transactions(currency=audit_currency)
        txs.sort(key=lambda x: x.date, reverse=True)

        if not args.all:
            txs = txs[: args.limit]

        if format_type == "table":
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
            if not args.all and len(txs) == args.limit:
                console.print(
                    f"[dim](Showing last {args.limit} transactions. Use --all to see more.)[/dim]"
                )
        else:
            data = []
            for tx in txs:
                for p in tx.postings:
                    if p.units.currency == audit_currency:
                        data.append(
                            {
                                "Date": str(tx.date),
                                "Description": (
                                    f"{tx.payee}: {tx.narration}" if tx.payee else tx.narration
                                ),
                                "Account": p.account,
                                "Amount": str(p.units.number),
                                "Currency": p.units.currency,
                                "Price": str(p.price.number) if p.price else "",
                                "Cost": str(p.cost.number) if p.cost else "",
                            }
                        )
            render_output(
                data, format_type=format_type, title=f"Audit {audit_currency}", console=console
            )
        return

    console.print(f"[red]Error: Unknown report type '{report_type}'[/red]")
    sys.exit(1)


def tx_list_cmd(args: argparse.Namespace):
    ledger_file = get_ledger_file(getattr(args, "pos_ledger_file", None) or args.ledger_file)
    service = TransactionService(ledger_file)

    txs = service.list_transactions(
        account_regex=args.account, payee_regex=args.payee, tag=args.tag, bql_where=args.where
    )

    format_type = getattr(args, "format", "table")
    if format_type == "json":
        data = [tx.model_dump(mode="json") for tx in txs]
    else:
        data = []
        for tx in txs:
            data.append({"Date": str(tx.date), "Payee": tx.payee or "", "Narration": tx.narration})

    render_output(
        data, format_type=format_type, title=f"Transactions ({len(txs)})", console=console
    )


def tx_add_cmd(args: argparse.Namespace):
    ledger_file = get_ledger_file(getattr(args, "pos_ledger_file", None) or args.ledger_file)
    service = TransactionService(ledger_file)

    if args.json:
        if args.json == "-":
            content = sys.stdin.read()
        else:
            content = args.json

        data = json.loads(content)

        if isinstance(data, list):
            from pydantic import TypeAdapter

            ta = TypeAdapter(list[TransactionModel])
            models = ta.validate_python(data)
            for m in models:
                service.add_transaction(m, draft=args.draft, print_only=args.print_only)
        else:
            model = TransactionModel(**data)
            service.add_transaction(model, draft=args.draft, print_only=args.print_only)
    else:
        console.print(
            "[yellow]Interactive mode not implemented in this version. Use --json.[/yellow]"
        )


def tx_schema_cmd(args: argparse.Namespace):
    schema = TransactionModel.model_json_schema()
    console.print(json.dumps(schema, indent=2))


def account_list_cmd(args: argparse.Namespace):
    ledger_file = get_ledger_file(getattr(args, "pos_ledger_file", None) or args.ledger_file)
    service = AccountService(ledger_file)
    accounts = service.list_accounts()

    format_type = getattr(args, "format", "table")
    if format_type == "json":
        data = [acc.model_dump(mode="json") for acc in accounts]
    else:
        data = []
        for acc in accounts:
            data.append(
                {
                    "Account": acc.name,
                    "Open Date": str(acc.open_date),
                    "Currencies": ", ".join(acc.currencies),
                }
            )

    render_output(
        data, format_type=format_type, title=f"Accounts ({len(accounts)})", console=console
    )


def account_create_cmd(args: argparse.Namespace):
    ledger_file = get_ledger_file(getattr(args, "pos_ledger_file", None) or args.ledger_file)
    service = AccountService(ledger_file)

    if args.json:
        if args.json == "-":
            content = sys.stdin.read()
        else:
            content = args.json

        data_input = json.loads(content)
        if isinstance(data_input, list):
            from pydantic import TypeAdapter

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
        if not args.name:
            console.print("[red]Error: --name is required if not using --json.[/red]")
            sys.exit(1)
        d = date.today()
        if args.date:
            d = date.fromisoformat(args.date)

        model = AccountModel(name=args.name, open_date=d, currencies=args.currency or [])
        service.create_account(model)
        console.print(f"[green]Account {args.name} created.[/green]")


def commodity_create_cmd(args: argparse.Namespace):
    ledger_file = get_ledger_file(args.pos_ledger_file or args.ledger_file)
    service = CommodityService(ledger_file)

    if args.json:
        if args.json == "-":
            content = sys.stdin.read()
        else:
            content = args.json

        data_input = json.loads(content)
        # Simplified batch for commodity as it doesn't have a full model yet,
        # just currency/name args.
        # We'll treat list of dicts with 'currency' and 'name'.
        items = data_input if isinstance(data_input, list) else [data_input]
        for item in items:
            curr = item.get("currency")
            name = item.get("name")
            if not curr:
                # If nested in CommodityModel later, we'd use that.
                # For now just pull from dict.
                console.print(f"[yellow]Skipping invalid commodity entry: {item}[/yellow]")
                continue
            service.create_commodity(curr, name=name)
            console.print(f"[green]Commodity {curr} created.[/green]")
    else:
        if not args.currency:
            console.print("[red]Error: currency argument is required if not using --json.[/red]")
            sys.exit(1)
        service.create_commodity(args.currency, name=args.name)
        console.print(f"[green]Commodity {args.currency} created.[/green]")


def format_cmd(args: argparse.Namespace):
    ledger_file = get_ledger_file(getattr(args, "pos_ledger_file", None) or args.ledger_file)

    try:
        import shutil
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        cmd = ["bean-format", "-c", "50", "-o", str(tmp_path), str(ledger_file)]
        subprocess.run(cmd, check=True, capture_output=True, text=True)  # nosec B603

        shutil.move(str(tmp_path), str(ledger_file))
        console.print(f"[green]Formatted {ledger_file}[/green]")

    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error running bean-format: {e.stderr}[/red]")
        sys.exit(1)


def price_cmd(args: argparse.Namespace):
    ledger_file = get_ledger_file(getattr(args, "pos_ledger_file", None) or args.ledger_file)

    console.print(f"Fetching prices for {ledger_file}...")

    try:
        cmd = ["bean-price", str(ledger_file)]
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)  # nosec B603
        prices_output = result.stdout.strip()

        if not prices_output:
            console.print("[yellow]No new prices found.[/yellow]")
            return

        if args.update:
            service = MapService(ledger_file)
            tree = service.get_include_tree()

            target_price_file = ledger_file

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
        sys.exit(1)
    except FileNotFoundError:
        console.print("[red]Error: bean-price not found. Is it installed?[/red]")
        sys.exit(1)


def main(args=None):
    parser = argparse.ArgumentParser(
        description="Beancount CLI tool for managing ledgers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment Variables:
  BEANCOUNT_FILE    Default ledger file to use if --file (-f) is not specified.
  
Global Flags:
  --format json     Best for single-item structural responses or piping into `jq`.
  --format csv      Highly recommended for AI Agents querying lists (3-5x token savings).
  --format table    Default terminal formatting for human-readable outputs.
        """,
    )
    parser.add_argument(
        "--file", "-f", dest="ledger_file", type=Path, help="Path to main.beancount file"
    )
    parser.add_argument(
        "--version", action="version", version=f"beancount-cli {__version__}", help="Show version"
    )
    parser.add_argument(
        "--format", choices=["table", "json", "csv"], default="table", help="Global output format"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # Check
    check_p = subparsers.add_parser("check", help="Validate the ledger file")
    check_p.add_argument("pos_ledger_file", type=Path, nargs="?", help="Path to ledger file")
    check_p.set_defaults(func=check_cmd)

    # Tree
    tree_p = subparsers.add_parser("tree", help="Visualize the tree of included files")
    tree_p.add_argument("pos_ledger_file", type=Path, nargs="?", help="Path to ledger file")
    tree_p.set_defaults(func=map_cmd)

    # Report
    report_p = subparsers.add_parser(
        "report",
        help="Generate simple reports.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  bean report balance-sheet --convert USD
  bean report holdings --valuation market
  bean report trial-balance
  bean report audit EUR
        """,
    )
    report_subs = report_p.add_subparsers(dest="report_cmd", required=True)

    report_balance = report_subs.add_parser(
        "balance-sheet", aliases=["balance", "bs"], help="Balance Sheet report"
    )
    report_balance.add_argument("pos_ledger_file", type=Path, nargs="?", help="Path to ledger file")
    report_balance.add_argument("--convert", "-c", help="Target currency for unified reporting")
    report_balance.add_argument(
        "--valuation",
        "-v",
        choices=["market", "cost"],
        default="market",
        help="Valuation strategy: 'market' or 'cost'",
    )
    report_balance.set_defaults(func=report_cmd, report_type="balance-sheet")

    report_trial = report_subs.add_parser(
        "trial-balance", aliases=["trial", "balances"], help="Trial Balance report"
    )
    report_trial.add_argument("pos_ledger_file", type=Path, nargs="?", help="Path to ledger file")
    report_trial.add_argument("--convert", "-c", help="Target currency for unified reporting")
    report_trial.add_argument(
        "--valuation",
        "-v",
        choices=["market", "cost"],
        default="market",
        help="Valuation strategy: 'market' or 'cost'",
    )
    report_trial.set_defaults(func=report_cmd, report_type="trial-balance")

    report_holdings = report_subs.add_parser("holdings", help="Portfolio holdings report")
    report_holdings.add_argument(
        "pos_ledger_file", type=Path, nargs="?", help="Path to ledger file"
    )
    report_holdings.add_argument("--convert", "-c", help="Target currency for unified reporting")
    report_holdings.add_argument(
        "--valuation",
        "-v",
        choices=["market", "cost"],
        default="market",
        help="Valuation strategy: 'market' or 'cost'",
    )
    report_holdings.set_defaults(func=report_cmd, report_type="holdings")

    report_audit = report_subs.add_parser("audit", help="Audit report for a specific currency")
    report_audit_currency = report_audit.add_argument("audit_currency", help="Currency to audit")
    report_audit_currency.completer = _report_arg1_completer
    report_audit.add_argument("pos_ledger_file", type=Path, nargs="?", help="Path to ledger file")
    report_audit.add_argument(
        "--limit", "-l", type=int, default=20, help="Limit number of transactions"
    )
    report_audit.add_argument("--all", action="store_true", help="Show all transactions")
    report_audit.set_defaults(func=report_cmd, report_type="audit")

    # Transaction Subcommand
    tx_p = subparsers.add_parser("transaction", help="Manage transactions.")
    tx_subs = tx_p.add_subparsers(dest="tx_cmd", required=True)

    tx_list = tx_subs.add_parser("list", help="List transactions matching filters.")
    tx_list.add_argument("pos_ledger_file", type=Path, nargs="?", help="Path to ledger file")
    tx_list.add_argument("--account", "-a", help="Filter by account regex")
    tx_list.add_argument("--payee", "-p", help="Filter by payee regex")
    tx_list.add_argument("--tag", "-t", help="Filter by tag")
    tx_list.add_argument("--where", "-w", help="Custom BQL where clause")
    tx_list.set_defaults(func=tx_list_cmd)

    tx_add = tx_subs.add_parser(
        "add",
        help="Add a new transaction.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples for AI Agents:
  # Single inline payload
  bean transaction add --json '{"date": "2025-01-01", "narration": "Test", "postings": []}'
  
  # Batch STDIN insertion
  bean transaction list --format json | bean transaction add --json -
        """,
    )
    tx_add.add_argument("pos_ledger_file", type=Path, nargs="?", help="Path to ledger file")
    tx_add.add_argument("--json", "-j", help="JSON string data (or '-' to read from STDIN)")
    tx_add.add_argument("--draft", action="store_true", help="Mark as pending (!)")
    tx_add.add_argument(
        "--print", action="store_true", dest="print_only", help="Print only, do not write"
    )
    tx_add.set_defaults(func=tx_add_cmd)

    tx_schema = tx_subs.add_parser("schema", help="Output the JSON schema for transactions")
    tx_schema.set_defaults(func=tx_schema_cmd)

    # Account Subcommand
    acc_p = subparsers.add_parser("account", help="Manage accounts.")
    acc_subs = acc_p.add_subparsers(dest="acc_cmd", required=True)

    acc_list = acc_subs.add_parser("list", help="List all accounts.")
    acc_list.add_argument("pos_ledger_file", type=Path, nargs="?", help="Path to ledger file")
    acc_list.set_defaults(func=account_list_cmd)

    acc_create = acc_subs.add_parser(
        "create",
        help="Create a new account.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples for AI Agents:
  # Single inline payload
  bean account create --json '{"name": "Assets:Cash", "currencies": ["USD"]}'
  
  # Batch STDIN insertion
  bean account list --format json | bean account create --json -
        """,
    )
    acc_create.add_argument("pos_ledger_file", type=Path, nargs="?", help="Path to ledger file")
    acc_create.add_argument("--name", "-n", help="Account name (e.g. Assets:Bank)")
    acc_create.add_argument(
        "--currency", "-c", action="append", default=[], help="Currencies (repeatable)"
    )
    acc_create.add_argument("--date", "-d", help="Open date (YYYY-MM-DD)")
    acc_create.add_argument("--json", "-j", help="JSON string data (or '-' to read from STDIN)")
    acc_create.set_defaults(func=account_create_cmd)

    # Commodity Subcommand
    comm_p = subparsers.add_parser("commodity", help="Manage commodities.")
    comm_subs = comm_p.add_subparsers(dest="comm_cmd", required=True)

    comm_create = comm_subs.add_parser(
        "create",
        help="Create a new commodity.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples for AI Agents:
  bean commodity create USD --name "US Dollar"
  bean commodity create --json '[{"currency": "BTC", "name": "Bitcoin"}]'
        """,
    )
    comm_create.add_argument("currency", nargs="?", help="Currency code (e.g. USD)")
    comm_create.add_argument("pos_ledger_file", type=Path, nargs="?", help="Path to ledger file")
    comm_create.add_argument("--name", "-n", help="Full name")
    comm_create.add_argument("--json", "-j", help="JSON string data (or '-' to read from STDIN)")
    comm_create.set_defaults(func=commodity_create_cmd)

    # Format
    format_p = subparsers.add_parser("format", help="Format ledger file(s)")
    format_p.add_argument("pos_ledger_file", type=Path, nargs="?", help="Path to ledger file")
    format_p.add_argument(
        "--recursive", "-r", action="store_true", help="Format all included files"
    )
    format_p.set_defaults(func=format_cmd)

    # Price
    price_p = subparsers.add_parser("price", help="Fetch and update prices")
    price_p.add_argument("pos_ledger_file", type=Path, nargs="?", help="Path to ledger file")
    price_p.add_argument("--update", "-u", action="store_true", help="Update prices in ledger")
    price_p.set_defaults(func=price_cmd)

    argcomplete.autocomplete(parser, validator=_completion_validator)

    parsed_args = parser.parse_args(args)
    if hasattr(parsed_args, "func"):
        parsed_args.func(parsed_args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
