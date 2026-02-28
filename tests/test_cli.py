import io
import json
from argparse import Namespace
from unittest.mock import patch

from beancount_cli.cli import (
    _completion_validator,
    _file_option_already_present,
    _report_arg1_completer,
    main,
)


def run_cli(*args):
    with patch("sys.stdout", new=io.StringIO()) as stdout:
        with patch("sys.stderr", new=io.StringIO()) as stderr:
            try:
                main(list(args))
                return 0, stdout.getvalue(), stderr.getvalue()
            except SystemExit as e:
                return e.code, stdout.getvalue(), stderr.getvalue()


def test_check_command(temp_beancount_file):
    code, out, err = run_cli("check", str(temp_beancount_file))
    assert code in (0, None)
    assert "No errors found" in out


def test_transaction_list(temp_beancount_file):
    code, out, err = run_cli("transaction", "list", str(temp_beancount_file))
    assert code in (0, None)
    assert "Employer" in out


def test_transaction_add_json(temp_beancount_file):
    payload = {
        "date": "2023-12-01",
        "narration": "CLI Test",
        "postings": [
            {"account": "Assets:Cash", "units": {"number": -10, "currency": "USD"}},
            {"account": "Expenses:Food", "units": {"number": 10, "currency": "USD"}},
        ],
    }
    code, out, err = run_cli(
        "transaction", "add", str(temp_beancount_file), "--json", json.dumps(payload)
    )
    assert code in (0, None)

    check_code, check_out, check_err = run_cli("check", str(temp_beancount_file))
    assert check_code in (0, None)


def test_account_create(temp_beancount_file):
    code, out, err = run_cli(
        "account",
        "create",
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
        "commodity", "create", "ETH", str(temp_beancount_file), "--name", "Ethereum"
    )
    assert code in (0, None)
    assert "created" in out


def test_tree_command(temp_beancount_file):
    code, out, err = run_cli("tree", str(temp_beancount_file))
    assert code in (0, None)
    assert str(temp_beancount_file) in out


def test_report_aliases(temp_beancount_file):
    code, out, err = run_cli("report", "balance", str(temp_beancount_file))
    assert code in (0, None)
    assert "Balance Sheet" in out

    code, out, err = run_cli("report", "trial", str(temp_beancount_file))
    assert code in (0, None)
    assert "Trial Balance" in out

    code, out, err = run_cli("tree", str(temp_beancount_file))
    assert code in (0, None)
    assert str(temp_beancount_file) in out


def test_report_holdings(temp_beancount_file):
    code, out, err = run_cli("report", "holdings", str(temp_beancount_file))
    assert code in (0, None)
    assert "Holdings" in out


def test_report_audit(temp_beancount_file):
    code, out, err = run_cli("report", "audit", "USD", str(temp_beancount_file))
    assert code in (0, None)
    assert "Audit Report: USD" in out


def test_tx_schema():
    code, out, err = run_cli("transaction", "schema")
    assert code in (0, None)
    assert "title" in out


def test_account_list(temp_beancount_file):
    code, out, err = run_cli("account", "list", str(temp_beancount_file))
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


def test_price_cmd(temp_beancount_file, monkeypatch):
    import subprocess

    def mock_run(*args, **kwargs):
        class MockResult:
            stdout = "2024-01-01 price AAPL 150.00 USD"

        return MockResult()

    monkeypatch.setattr(subprocess, "run", mock_run)
    code, out, err = run_cli("price", str(temp_beancount_file))
    assert code in (0, None)
    assert "2024-01-01" in out

    code, out, err = run_cli("price", str(temp_beancount_file), "--update")
    assert code in (0, None)
    assert "Appended" in out


def test_missing_ledger_file(monkeypatch):
    import os

    if "BEANCOUNT_FILE" in os.environ:
        monkeypatch.delenv("BEANCOUNT_FILE")
    if "BEANCOUNT_PATH" in os.environ:
        monkeypatch.delenv("BEANCOUNT_PATH")

    code, out, err = run_cli("check")
    assert code == 1
    assert "Error: No ledger file found" in out


def test_report_audit_currency_completion_from_ledger(temp_beancount_file):
    parsed_args = Namespace(report_type="audit", ledger_file=temp_beancount_file, arg1=None, arg2=None)
    completions = _report_arg1_completer("U", parsed_args)
    assert "USD" in completions


def test_file_option_policy_detects_existing_flag():
    assert _file_option_already_present("bean --file main.beancount report audit")
    assert _file_option_already_present("bean -f main.beancount report audit")
    assert not _file_option_already_present("bean report audit")


def test_completion_validator_hides_duplicate_file_option(monkeypatch):
    monkeypatch.setenv("COMP_LINE", "bean --file main.beancount ")
    assert not _completion_validator("--file", "--")
    assert not _completion_validator("-f", "-")
    assert _completion_validator("--format", "--")
