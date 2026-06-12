import io
import json
import textwrap
from unittest.mock import patch

from beancount_cli.cli import main


def run_cli(*args):
    with patch("sys.stdout", new=io.StringIO()) as stdout:
        with patch("sys.stderr", new=io.StringIO()) as stderr:
            try:
                main(list(args))
                return 0, stdout.getvalue(), stderr.getvalue()
            except SystemExit as e:
                code = e.code if e.code is not None else 0
                return code, stdout.getvalue(), stderr.getvalue()


def test_check_command(temp_beancount_file):
    code, out, err = run_cli("check", str(temp_beancount_file))
    assert code in (0, None)
    assert "No errors found" in out


def test_transaction_list(temp_beancount_file):
    code, out, err = run_cli("transaction", "list", "--file", str(temp_beancount_file))
    assert code in (0, None)
    assert "Employer" in out


def test_transaction_list_fields(temp_beancount_file):
    code, out, err = run_cli(
        "transaction",
        "list",
        "--file",
        str(temp_beancount_file),
        "--format",
        "json",
        "--fields",
        "date,payee",
    )
    assert code in (0, None)
    data = json.loads(out)
    # Check that only date and payee are present (plus any standard agentyper wrapper)
    # If agentyper wraps it in {"ok": true, "data": [...]}:
    txs = data["data"]
    if isinstance(txs, list):
        for tx in txs:
            assert set(tx.keys()) == {"date", "payee"}
    else:
        assert set(txs.keys()) == {"date", "payee"}


def test_transaction_add_json(temp_beancount_file):
    postings = json.dumps(
        [
            {"account": "Assets:Cash", "units": {"number": -10, "currency": "USD"}},
            {"account": "Expenses:Food", "units": {"number": 10, "currency": "USD"}},
        ]
    )
    code, out, err = run_cli(
        "transaction",
        "add",
        "--file",
        str(temp_beancount_file),
        "--date",
        "2023-12-01",
        "--narration",
        "CLI Test",
        "--postings",
        postings,
    )
    assert code in (0, None)

    check_code, check_out, check_err = run_cli("check", str(temp_beancount_file))
    assert check_code in (0, None)


def test_account_create(temp_beancount_file):
    code, out, err = run_cli(
        "account",
        "create",
        "--file",
        str(temp_beancount_file),
        "--name",
        "Liabilities:CreditCard",
        "-c",
        "USD",
    )
    assert code in (0, None)
    assert "created" in out


def test_commodity_create(temp_beancount_file):
    code, out, err = run_cli(
        "commodity", "create", "ETH", "--file", str(temp_beancount_file), "--name", "Ethereum"
    )
    assert code in (0, None)
    assert "created" in out


def test_tree_command(temp_beancount_file):
    code, out, err = run_cli("tree", str(temp_beancount_file))
    assert code in (0, None)
    assert str(temp_beancount_file) in out


def test_report_aliases(temp_beancount_file):
    code, out, err = run_cli("report", "balance-sheet", "--file", str(temp_beancount_file))
    assert code in (0, None)
    assert "Balance Sheet" in out

    code, out, err = run_cli("report", "trial-balance", "--file", str(temp_beancount_file))
    assert code in (0, None)
    assert "Trial Balance" in out

    code, out, err = run_cli("tree", str(temp_beancount_file))
    assert code in (0, None)
    assert str(temp_beancount_file) in out


def test_report_holdings(temp_beancount_file):
    code, out, err = run_cli("report", "holdings", "--file", str(temp_beancount_file))
    assert code in (0, None)
    assert "Holdings" in out


def test_report_audit(tmp_path):
    path = tmp_path / "audit.beancount"
    path.write_text(
        textwrap.dedent(
            """
        option "operating_currency" "USD"
        2020-01-01 open Assets:Cash USD
        2020-01-01 open Expenses:Food USD
        
        2020-02-01 * "Store A" "Oldest"
          Expenses:Food          100 USD
          Assets:Cash           -100 USD

        2020-02-15 * "Store B" "Middle"
          Expenses:Food          200 USD
          Assets:Cash           -200 USD

        2020-03-01 * "Store C" "Newest"
          Expenses:Food          300 USD
          Assets:Cash           -300 USD
    """
        )
    )
    # Test all transactions (older to newest)
    code, out, err = run_cli("report", "audit", "--file", str(path), "--currency", "USD", "--all")
    assert code in (0, None)
    assert "Audit Report: USD" in out
    lines = [line for line in out.splitlines() if "Store" in line]
    assert len(lines) == 6
    assert "Store A" in lines[0]
    assert "Store B" in lines[2]
    assert "Store C" in lines[4]

    # Test limit (should show LAST 2 transactions in chronological order: Middle -> Newest)
    code, out, err = run_cli(
        "report", "audit", "--file", str(path), "--currency", "USD", "--limit", "2"
    )
    assert code in (0, None)
    lines = [line for line in out.splitlines() if "Store" in line]
    assert len(lines) == 4
    assert "Store B" in lines[0]
    assert "Store C" in lines[2]
    assert "Showing last 2 transactions" in out


def test_tx_schema():
    code, out, err = run_cli("transaction", "add", "--schema")
    assert code in (0, None)
    assert "properties" in out


def test_account_list(temp_beancount_file):
    code, out, err = run_cli("account", "list", "--file", str(temp_beancount_file))
    assert code in (0, None)
    assert "Assets:Cash" in out


def test_format_cmd(temp_beancount_file, monkeypatch):
    import subprocess

    def mock_run(*args, **kwargs):
        class MockResult:
            stdout = ""

        cmd_list = args[0]
        if "-o" in cmd_list:
            out_idx = cmd_list.index("-o") + 1
            with open(cmd_list[out_idx], "w") as f:
                f.write("; formatted content\n")
        return MockResult()

    monkeypatch.setattr(subprocess, "run", mock_run)
    code, out, err = run_cli("format", str(temp_beancount_file))
    assert code in (0, None)
    assert "Formatted" in out


def test_price_cmd(temp_beancount_file):
    # `price` is now a subcommand group; calling it without a subcommand shows help
    code, out, err = run_cli("price", "--help")
    assert code in (0, None)
    assert "check" in (out + err) or "fetch" in (out + err)


def test_missing_ledger_file(monkeypatch):
    import os

    if "BEANCOUNT_FILE" in os.environ:
        monkeypatch.delenv("BEANCOUNT_FILE")
    if "BEANCOUNT_PATH" in os.environ:
        monkeypatch.delenv("BEANCOUNT_PATH")

    code, out, err = run_cli("check", "doesnt_exist_file.beancount")
    assert code == 1  # EXIT_SYSTEM
    assert "Traceback" not in err


def test_report_holdings_help_hides_audit_only_flags():
    code, out, err = run_cli("report", "holdings", "--help")
    assert code in (0, None)
    assert "--limit" not in out
    assert "--all" not in out


def test_report_audit_help_shows_audit_only_flags():
    code, out, err = run_cli("report", "audit", "--help")
    assert code in (0, None)
    assert "--limit" in (out + err)
    assert "--all" in (out + err)
