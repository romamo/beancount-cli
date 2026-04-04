import os
import sys
from decimal import Decimal
from pathlib import Path

from rich.console import Console
from rich.table import Table

console = Console()
error_console = Console(stderr=True)


def read_json_input(json_data: str) -> str:
    """Read JSON from a string or from STDIN when json_data is '-'."""
    if json_data == "-":
        return sys.stdin.read()
    return json_data


def get_ledger_file(override: str | Path | None = None) -> Path:
    if override:
        return Path(override)
    env_file = os.environ.get("BEANCOUNT_FILE")
    if env_file:
        return Path(env_file)
    return Path("main.beancount")


def _is_table_format() -> bool:
    if "--format" in sys.argv:
        idx = sys.argv.index("--format")
        if idx + 1 < len(sys.argv) and sys.argv[idx + 1] in ("json", "csv"):
            return False
    for arg in sys.argv:
        if arg.startswith("--format="):
            val = arg.split("=")[1]
            if val in ("json", "csv"):
                return False
    return True


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
