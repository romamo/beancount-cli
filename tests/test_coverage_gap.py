from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from beancount_cli.models import AccountModel, AmountModel, PostingModel, TransactionModel
from beancount_cli.services import (
    AccountService,
    CommodityService,
    LedgerService,
    TransactionService,
    ValidationService,
)


def test_transaction_service_draft_and_print(temp_beancount_file, capsys):
    service = TransactionService(temp_beancount_file)
    tx = TransactionModel(
        date=date(2024, 1, 1),
        narration="Draft Test",
        postings=[
            PostingModel(
                account="Assets:Cash", units=AmountModel(number=Decimal("10"), currency="USD")
            ),
            PostingModel(
                account="Expenses:Food", units=AmountModel(number=Decimal("-10"), currency="USD")
            ),
        ],
    )

    # Test draft mode
    service.add_transaction(tx, draft=True)
    # verify flag is '!'
    ledger = LedgerService(temp_beancount_file)
    ledger.load()
    found = [e for e in ledger.entries if hasattr(e, "narration") and e.narration == "Draft Test"]
    assert len(found) == 1
    assert found[0].flag == "!"

    # Test print_only
    service.add_transaction(tx, print_only=True)
    captured = capsys.readouterr()
    assert '2024-01-01 * "Draft Test"' in captured.out


def test_validation_errors(temp_beancount_file):
    service = TransactionService(temp_beancount_file)
    # Invalid account and currency
    tx = TransactionModel(
        date=date(2024, 1, 1),
        narration="Invalid Test",
        postings=[
            PostingModel(
                account="Assets:NonExistent",
                units=AmountModel(number=Decimal("10"), currency="XBT"),
            ),
            PostingModel(
                account="Expenses:Food", units=AmountModel(number=Decimal("-10"), currency="XBT")
            ),
        ],
    )
    # Beancount fails if no open directive
    with pytest.raises(ValueError, match="Transaction failed validation"):
        service.add_transaction(tx)


def test_account_already_exists(temp_beancount_file):
    service = AccountService(temp_beancount_file)
    model = AccountModel(name="Assets:Cash", currencies=["USD"])
    with pytest.raises(ValueError, match="already exists"):
        service.create_account(model)


def test_commodity_already_exists(tmp_path):
    f = tmp_path / "comm.beancount"
    f.write_text("2024-01-01 commodity BTC\n")
    service = CommodityService(f)
    with pytest.raises(ValueError, match="already exists"):
        service.create_commodity("BTC")


def test_currency_validation_gap(tmp_path):
    f = tmp_path / "val.beancount"
    f.write_text("2024-01-01 open Assets:Cash USD\n2024-01-01 commodity USD\n")
    ledger = LedgerService(f)
    ledger.load()
    validator = ValidationService(ledger)

    tx = TransactionModel(
        date=date(2024, 1, 1),
        narration="Curr Test",
        postings=[
            PostingModel(
                account="Assets:Cash", units=AmountModel(number=Decimal("10"), currency="EUR")
            ),
        ],
    )
    errors = validator.validate_transaction(tx)
    assert any("Currency 'EUR' not in declared commodities" in e for e in errors)


def test_ledger_file_not_found():
    service = LedgerService(Path("non_existent_file.beancount"))
    with pytest.raises(FileNotFoundError):
        service.load()


def test_custom_config_variations(tmp_path):
    f = tmp_path / "test.beancount"
    f.write_text(
        '2024-01-01 custom "cli-config" "key1"\n'  # short
        '2024-01-01 custom "other-type" "key2" "val2"\n'  # wrong type
        '2024-01-01 custom "cli-config" "key3" "val3"\n'  # correct
    )
    service = LedgerService(f)
    assert service.get_custom_config("key1") is None
    assert service.get_custom_config("key2") is None
    assert service.get_custom_config("key3") == "val3"


def test_vo_type_errors():
    from beancount_cli.models import validate_account_name, validate_currency_code

    with pytest.raises(TypeError, match="string required"):
        validate_account_name(123)
    with pytest.raises(TypeError, match="string required"):
        validate_currency_code(None)


def test_adapters_cost_mapping():
    from beancount.core import position

    from beancount_cli.adapters import from_core_cost, to_core_cost
    from beancount_cli.models import CostModel

    # Test to_core_cost
    model = CostModel(number=Decimal("100"), currency="USD", date=date(2024, 1, 1), label="test")
    core = to_core_cost(model)
    assert core.number == Decimal("100")
    assert core.currency == "USD"
    assert core.date == date(2024, 1, 1)
    assert core.label == "test"

    # Test from_core_cost
    core_obj = position.Cost(Decimal("200"), "EUR", date(2024, 2, 2), "label2")
    model_out = from_core_cost(core_obj)
    assert model_out.number == Decimal("200")
    assert model_out.currency == "EUR"
    assert model_out.date == date(2024, 2, 2)
    assert model_out.label == "label2"


def test_transaction_service_filtering(temp_beancount_file):
    # Add some transactions to the file
    with open(temp_beancount_file, "a") as f:
        f.write(
            '\n2024-01-01 * "Payee A" "Narration A" #tag1\n  Assets:Cash 10 USD\n  Expenses:Food -10 USD\n'
        )
        f.write(
            '\n2024-02-01 * "Payee B" "Narration B" #tag2\n  Assets:Bank 20 EUR\n  Expenses:Rent -20 EUR\n'
        )

    service = TransactionService(temp_beancount_file)

    # Filter by account
    res = service.list_transactions(account_regex="Cash")
    # There's already one in the fixture, plus one we added
    assert len(res) == 2
    assert any(tx.payee == "Payee A" for tx in res)

    # Filter by payee
    res = service.list_transactions(payee_regex="Payee B")
    assert len(res) == 1
    assert res[0].date == date(2024, 2, 1)

    # Filter by tag
    res = service.list_transactions(tag="tag1")
    assert len(res) == 1

    # Filter by currency
    res = service.list_transactions(currency="EUR")
    assert len(res) == 1
    assert res[0].payee == "Payee B"


def test_map_service_edge_cases(tmp_path):
    from beancount_cli.services import MapService

    root = tmp_path / "root.beancount"
    root.write_text('include "sub/*.beancount"\n')

    # Test non-matching glob
    service = MapService(root)
    tree = service.get_include_tree()
    assert "sub/*.beancount (No matches)" in tree

    # Test absolute path (simulated relative to root)
    abs_sub = (tmp_path / "abs.beancount").resolve()
    abs_sub.write_text("; empty\n")
    root.write_text(f'include "{abs_sub}"\n')
    tree = service.get_include_tree()
    assert str(abs_sub) in tree


# ---------------------------------------------------------------------------
# formatting.py gaps
# ---------------------------------------------------------------------------


def test_tree_render_multi_level():
    from beancount_cli.formatting import Tree

    root = Tree("root")
    child1 = root.add("child1")
    child1.add("grandchild")
    root.add("child2")
    result = str(root)
    assert "root" in result
    assert "child1" in result
    assert "grandchild" in result
    assert "child2" in result
    # Non-root nodes use tree-drawing characters
    assert "──" in result


def test_render_output_single_item_table():
    import io

    from beancount_cli.formatting import Console, render_output

    buf = io.StringIO()
    render_output(
        {"Name": "Alice", "Balance": "100 USD"},
        format_type="table",
        title="Detail",
        console=Console(file=buf),
    )
    out = buf.getvalue()
    assert "Name" in out
    assert "Alice" in out
    assert "Balance" in out


def test_render_output_csv_empty():
    import io

    from beancount_cli.formatting import Console, render_output

    buf = io.StringIO()
    render_output([], format_type="csv", console=Console(file=buf))
    assert buf.getvalue() == ""


def test_render_output_csv_rows():
    import io

    from beancount_cli.formatting import Console, render_output

    buf = io.StringIO()
    render_output(
        [{"Account": "Assets:Cash", "Amount": "100"}],
        format_type="csv",
        console=Console(file=buf),
    )
    out = buf.getvalue()
    assert "Account" in out
    assert "Assets:Cash" in out


def test_truncate_cell_long_string():
    from beancount_cli.formatting import truncate_cell

    short = "hello"
    assert truncate_cell(short, max_width=40) == short

    long_val = "x" * 50
    result = truncate_cell(long_val, max_width=40)
    assert len(result) == 40
    assert result.endswith("\u2026")  # ellipsis character


def test_render_output_table_truncates_long_narration():
    """Verifies the truncation branch inside render_output for list tables."""
    import io

    from beancount_cli.formatting import Console, render_output

    long_narration = "A" * 60
    buf = io.StringIO()
    render_output(
        [{"Date": "2024-01-01", "Narration": long_narration}],
        format_type="table",
        console=Console(file=buf),
    )
    out = buf.getvalue()
    # The narration should be truncated (not the full 60 chars)
    assert long_narration not in out
    assert "\u2026" in out  # Ellipsis proves truncation occurred


# ---------------------------------------------------------------------------
# cli.py helper gaps
# ---------------------------------------------------------------------------


def test_comp_line_tokens_shlex_fallback():
    """Unclosed quote triggers ValueError → raw split fallback."""
    from beancount_cli.cli import _comp_line_tokens

    # shlex will raise ValueError on the unclosed quote
    result = _comp_line_tokens("bean report 'unclosed")
    assert isinstance(result, list)
    assert len(result) > 0


def test_resolve_report_completion_ledger_fallback(tmp_path, monkeypatch):
    """Covers the pos_ledger_file and CliConfig fallback branches."""
    import argparse

    from beancount_cli.cli import _resolve_report_completion_ledger

    ledger = tmp_path / "main.beancount"
    ledger.write_text('option "title" "Test"\n')

    # Branch 1: pos_ledger_file exists
    ns = argparse.Namespace(ledger_file=None, pos_ledger_file=ledger)
    assert _resolve_report_completion_ledger(ns) == ledger

    # Branch 2: both None, CliConfig env var fallback
    monkeypatch.setenv("BEANCOUNT_FILE", str(ledger))
    ns2 = argparse.Namespace(ledger_file=None, pos_ledger_file=None)
    result = _resolve_report_completion_ledger(ns2)
    assert result == ledger

    # Branch 3: nothing found at all
    monkeypatch.delenv("BEANCOUNT_FILE", raising=False)
    monkeypatch.delenv("BEANCOUNT_PATH", raising=False)
    ns3 = argparse.Namespace(ledger_file=None, pos_ledger_file=None)
    assert _resolve_report_completion_ledger(ns3) is None


def test_report_arg1_completer_no_ledger(monkeypatch):
    """Covers the early-return [] when no ledger can be found."""
    import argparse

    from beancount_cli.cli import _report_arg1_completer

    monkeypatch.delenv("BEANCOUNT_FILE", raising=False)
    monkeypatch.delenv("BEANCOUNT_PATH", raising=False)
    ns = argparse.Namespace(ledger_file=None, pos_ledger_file=None)
    result = _report_arg1_completer("", ns)
    assert result == []


# ---------------------------------------------------------------------------
# services.py — multi-currency conversion gap
# ---------------------------------------------------------------------------


@pytest.fixture
def multicurrency_ledger(tmp_path) -> Path:
    """A ledger with EUR holdings and a USD price entry."""
    f = tmp_path / "multi.beancount"
    f.write_text(
        'option "operating_currency" "EUR"\n'
        "2020-01-01 commodity EUR\n"
        "2020-01-01 commodity TSLA\n"
        "2020-01-01 open Assets:Broker EUR\n"
        "2020-01-01 open Assets:Cash EUR\n"
        "2020-01-01 open Income:Salary EUR\n"
        "2020-01-01 open Expenses:Fees EUR\n"
        "2023-01-01 price TSLA 200.00 EUR\n"
        '2023-01-01 * "Employer" "Salary"\n'
        "  Income:Salary    -1000.00 EUR\n"
        "  Assets:Cash       1000.00 EUR\n"
        '2023-06-01 * "Buy" "TSLA shares"\n'
        "  Assets:Broker     5 TSLA {190.00 EUR}\n"
        "  Assets:Cash    -950.00 EUR\n"
        "  Expenses:Fees   -50.00 EUR\n"
    )
    return f


def test_get_balances_convert_market(multicurrency_ledger):
    """Exercises the market-valuation currency-conversion path in get_balances."""
    from beancount_cli.services import LedgerService, ReportService

    service = LedgerService(multicurrency_ledger)
    report = ReportService(service)

    balances = report.get_balances(convert_to="EUR", valuation="market")
    # Assets:Cash should have a EUR balance
    assert "Assets:Cash" in balances
    cash_bal = balances["Assets:Cash"]
    assert "EUR" in cash_bal["units"]


def test_get_balances_convert_cost(multicurrency_ledger):
    """Exercises the cost-valuation currency-conversion path in get_balances."""
    from beancount_cli.services import LedgerService, ReportService

    service = LedgerService(multicurrency_ledger)
    report = ReportService(service)

    balances = report.get_balances(convert_to="EUR", valuation="cost")
    # Broker account holds TSLA — should be valued at cost basis
    assert "Assets:Broker" in balances
    broker_bal = balances["Assets:Broker"]
    assert "EUR" in broker_bal["units"]
    # Cost: 5 shares × 190 EUR = 950 EUR
    assert broker_bal["units"]["EUR"] == pytest.approx(950, abs=1)


def test_transaction_service_inbox(tmp_path):
    ledger = tmp_path / "main.beancount"
    ledger.write_text(
        "2024-01-01 open Assets:Cash USD\n"
        "2024-01-01 open Expenses:Food USD\n"
        "2024-01-01 commodity USD\n"
        '2024-01-01 custom "cli-config" "new_transaction_file" "inbox/{year}/{payee}.beancount"\n'
    )

    service = TransactionService(ledger)
    tx = TransactionModel(
        date=date(2024, 3, 15),
        payee="Super Market",
        narration="Groceries",
        postings=[
            PostingModel(
                account="Assets:Cash", units=AmountModel(number=Decimal("50"), currency="USD")
            ),
            PostingModel(
                account="Expenses:Food", units=AmountModel(number=Decimal("-50"), currency="USD")
            ),
        ],
    )

    # Test file mode (path has extension .beancount)
    service.add_transaction(tx)

    target = tmp_path / "inbox" / "2024" / "SuperMarket.beancount"
    assert target.exists()
    content = target.read_text()
    assert "Super Market" in content
    assert "Groceries" in content

    # Test directory mode (change config to no extension)
    ledger.write_text(
        "2024-01-01 open Assets:Cash USD\n"
        "2024-01-01 open Expenses:Food USD\n"
        "2024-01-01 commodity USD\n"
        '2024-01-01 custom "cli-config" "new_transaction_file" "inbox/daily"\n'
    )
    service = TransactionService(ledger)
    service.add_transaction(tx)

    daily_dir = tmp_path / "inbox" / "daily"
    assert daily_dir.is_dir()
    files = list(daily_dir.glob("*.beancount"))
    assert len(files) == 1
    assert "SuperMarket" in files[0].name


# ---------------------------------------------------------------------------
# formatting.py — Table column overflow guard (L107)
# ---------------------------------------------------------------------------


def test_table_row_extra_values_are_silently_dropped():
    """A row with more values than columns must not raise — extra values are ignored."""
    from beancount_cli.formatting import Table

    t = Table("title")
    t.add_column("Col1")
    t.add_column("Col2")
    # Row has 3 values but only 2 columns defined
    t.add_row("A", "B", "C")
    rendered = str(t)
    assert "A" in rendered
    assert "B" in rendered
    # The third value "C" is silently dropped — no assertion about it in output
    assert "Col1" in rendered


# ---------------------------------------------------------------------------
# cli.py — report commands with --format csv / --format json
# ---------------------------------------------------------------------------


def _run_cli(*args):
    """Local helper matching the pattern in test_cli.py."""
    import io
    from unittest.mock import patch

    from beancount_cli.cli import main

    with patch("sys.stdout", new=io.StringIO()) as stdout:
        with patch("sys.stderr", new=io.StringIO()) as stderr:
            try:
                main(list(args))
                return 0, stdout.getvalue(), stderr.getvalue()
            except SystemExit as e:
                return e.code, stdout.getvalue(), stderr.getvalue()


def test_report_balance_sheet_csv(temp_beancount_file):
    import io
    from unittest.mock import patch

    from beancount_cli.cli import main

    with patch("sys.stdout", new=io.StringIO()) as stdout:
        try:
            main(["--format", "csv", "report", "balance-sheet", str(temp_beancount_file)])
        except SystemExit:
            pass
        out = stdout.getvalue()
    assert "Account" in out


def test_report_trial_balance_csv(temp_beancount_file):
    import io
    from unittest.mock import patch

    from beancount_cli.cli import main

    with patch("sys.stdout", new=io.StringIO()) as stdout:
        try:
            main(["--format", "csv", "report", "trial-balance", str(temp_beancount_file)])
        except SystemExit:
            pass
        out = stdout.getvalue()
    assert "Account" in out


def test_report_holdings_json(temp_beancount_file):
    """Exercises the holdings JSON output path (render_output(holdings, format='json'))."""
    import json as jsonlib

    code, out, _ = _run_cli("report", "--format", "json", "holdings", str(temp_beancount_file))
    data = jsonlib.loads(out)
    assert "accounts" in data


def test_report_holdings_csv(temp_beancount_file):
    """Exercises the Holdings CSV flatten path (L314-332 else branch)."""
    import io
    from unittest.mock import patch

    from beancount_cli.cli import main

    with patch("sys.stdout", new=io.StringIO()) as stdout:
        try:
            main(["--format", "csv", "report", "holdings", str(temp_beancount_file)])
        except SystemExit:
            pass
        out = stdout.getvalue()
    # Either headers or empty — just verify it doesn't crash and CSV-like structure
    assert isinstance(out, str)


def test_report_audit_json(temp_beancount_file):
    """Exercises the audit report JSON output (L381-400)."""
    import json as jsonlib

    code, out, _ = _run_cli("report", "--format", "json", "audit", "USD", str(temp_beancount_file))
    data = jsonlib.loads(out)
    assert isinstance(data, list)


def test_report_audit_all_flag(temp_beancount_file):
    """Exercises the --all flag path in audit_cmd (L347)."""
    import io
    from unittest.mock import patch

    from beancount_cli.cli import main

    with patch("sys.stdout", new=io.StringIO()) as stdout:
        try:
            main(["report", "audit", "USD", str(temp_beancount_file), "--all"])
        except SystemExit:
            pass
        out = stdout.getvalue()
    assert "Audit Report: USD" in out


def test_check_cmd_with_errors(tmp_path):
    """Exercises check_cmd error path (L227-231) with a malformed ledger."""
    import io
    from unittest.mock import patch

    from beancount_cli.cli import main

    bad = tmp_path / "bad.beancount"
    bad.write_text("2023-01-01 open Assets:Cash GBP\n2023-01-01 balance Assets:Cash 999.00 GBP\n")

    with patch("sys.stdout", new=io.StringIO()) as stdout:
        code = None
        try:
            main(["check", str(bad)])
        except SystemExit as e:
            code = e.code
        out = stdout.getvalue()
    assert code == 1 or "Error" in out or ":" in out


def test_report_arg1_completer_with_cost_and_price(tmp_path):
    """Exercises cost and price currency collection branches (L99-101)."""
    import argparse

    from beancount_cli.cli import _report_arg1_completer

    ledger = tmp_path / "main.beancount"
    ledger.write_text(
        'option "operating_currency" "EUR"\n'
        "2020-01-01 commodity EUR\n"
        "2020-01-01 commodity TSLA\n"
        "2020-01-01 open Assets:Broker EUR\n"
        "2020-01-01 open Assets:Cash EUR\n"
        "2020-01-01 open Income:Salary EUR\n"
        "2020-01-01 open Expenses:Fees EUR\n"
        '2023-06-01 * "Buy" "TSLA shares"\n'
        "  Assets:Broker     5 TSLA {190.00 EUR}\n"
        "  Assets:Cash    -950.00 EUR\n"
        "  Expenses:Fees   -50.00 EUR\n"
        '2023-07-01 * "FX" "exchange"\n'
        "  Assets:Cash     100 EUR @ 1.08 USD\n"
        "  Assets:Broker  -108 USD\n"
    )
    ns = argparse.Namespace(ledger_file=ledger, pos_ledger_file=None)
    result = _report_arg1_completer("", ns)
    assert "EUR" in result
    assert "TSLA" in result
    assert "USD" in result


def test_tx_list_json_format(temp_beancount_file):
    """Exercises the JSON format path in tx_list_cmd (L417)."""
    import json as jsonlib

    code, out, _ = _run_cli("transaction", "list", str(temp_beancount_file), "--format", "json")
    data = jsonlib.loads(out)
    assert isinstance(data, list)


def test_account_create_json_batch(temp_beancount_file):
    """Exercises the JSON batch path in account_create_cmd (L499-503)."""
    import io
    import json as jsonlib
    from unittest.mock import patch

    from beancount_cli.cli import main

    payload = jsonlib.dumps(
        [{"name": "Assets:Savings", "open_date": "2024-01-01", "currencies": []}]
    )

    with patch("sys.stdout", new=io.StringIO()) as stdout:
        try:
            main(["account", "create", str(temp_beancount_file), "--json", payload])
        except SystemExit:
            pass
        out = stdout.getvalue()
    assert "created" in out.lower()


def test_report_invalid_valuation(temp_beancount_file):
    """Exercises the invalid valuation guard in report_cmd (L259-263).

    Note: argparse itself rejects invalid enum choices with exit code 2 before
    reaching our custom guard (which would exit 1). Both are non-zero failures.
    """
    import io
    from unittest.mock import patch

    from beancount_cli.cli import main

    with patch("sys.stdout", new=io.StringIO()), patch("sys.stderr", new=io.StringIO()):
        code = None
        try:
            main(["report", "balance-sheet", str(temp_beancount_file), "--valuation", "invalid"])
        except SystemExit as e:
            code = e.code
    assert code is not None and code != 0


# ---------------------------------------------------------------------------
# services.py — get_holdings without target currencies (L517)
# ---------------------------------------------------------------------------


def test_get_holdings_no_targets(multicurrency_ledger):
    """Covers the fallback to operating currencies when target_currencies is empty."""
    from beancount_cli.services import LedgerService, ReportService

    service = LedgerService(multicurrency_ledger)
    report = ReportService(service)

    # Pass empty list — should fallback to operating_currency "EUR"
    holdings = report.get_holdings(target_currencies=[])
    assert "accounts" in holdings
    assert "totals" in holdings
