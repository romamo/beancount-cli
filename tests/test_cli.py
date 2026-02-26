import json

from typer.testing import CliRunner

from beancount_cli.cli import app

runner = CliRunner()


def test_check_command(temp_beancount_file):
    # Pass file via positional arg
    result = runner.invoke(app, ["check", str(temp_beancount_file)])
    assert result.exit_code == 0
    assert "No errors found" in result.stdout


def test_transaction_list(temp_beancount_file):
    # Positional arg
    result = runner.invoke(app, ["transaction", "list", str(temp_beancount_file)])
    assert result.exit_code == 0
    assert "Employer" in result.stdout


def test_transaction_add_json(temp_beancount_file):
    payload = {
        "date": "2023-12-01",
        "narration": "CLI Test",
        "postings": [
            {"account": "Assets:Cash", "units": {"number": -10, "currency": "USD"}},
            {"account": "Expenses:Food", "units": {"number": 10, "currency": "USD"}},
        ],
    }
    # Positional arg for add
    result = runner.invoke(
        app, ["transaction", "add", str(temp_beancount_file), "--json", json.dumps(payload)]
    )
    assert result.exit_code == 0

    # Verify via check
    check_res = runner.invoke(app, ["check", str(temp_beancount_file)])
    assert check_res.exit_code == 0


def test_account_create(temp_beancount_file):
    result = runner.invoke(
        app,
        [
            "account",
            "create",
            str(temp_beancount_file),
            "--name",
            "Liabilities:CreditCard",
            "--currency",
            "USD",
        ],
    )
    assert result.exit_code == 0
    assert "created" in result.stdout


def test_commodity_create(temp_beancount_file):
    # check if currency is first arg
    result = runner.invoke(
        app, ["commodity", "create", "ETH", str(temp_beancount_file), "--name", "Ethereum"]
    )
    assert result.exit_code == 0
    assert "created" in result.stdout


def test_tree_command(temp_beancount_file):
    # Test that tree works
    result = runner.invoke(app, ["tree", str(temp_beancount_file)])
    assert result.exit_code == 0
    assert str(temp_beancount_file) in result.stdout


def test_report_aliases(temp_beancount_file):
    # Test balance alias
    res1 = runner.invoke(app, ["report", "balance", str(temp_beancount_file)])
    assert res1.exit_code == 0
    assert "Balance Sheet" in res1.stdout
    assert "Assets:Cash" in res1.stdout

    # Test trial alias
    res2 = runner.invoke(app, ["report", "trial", str(temp_beancount_file)])
    assert res2.exit_code == 0
    assert "Trial Balance" in res2.stdout

    # Test tree command
    res3 = runner.invoke(app, ["tree", str(temp_beancount_file)])
    assert res3.exit_code == 0
    assert str(temp_beancount_file) in res3.stdout


def test_report_holdings(temp_beancount_file):
    result = runner.invoke(app, ["report", "holdings", str(temp_beancount_file)])
    assert result.exit_code == 0
    assert "Holdings" in result.stdout


def test_report_audit(temp_beancount_file):
    result = runner.invoke(app, ["report", "audit", "USD", str(temp_beancount_file)])
    assert result.exit_code == 0
    assert "Audit Report: USD" in result.stdout


def test_tx_schema():
    result = runner.invoke(app, ["transaction", "schema"])
    assert result.exit_code == 0
    assert "title" in result.stdout


def test_account_list(temp_beancount_file):
    result = runner.invoke(app, ["account", "list", str(temp_beancount_file)])
    assert result.exit_code == 0
    assert "Assets:Cash" in result.stdout


def test_format_cmd(temp_beancount_file, monkeypatch):
    import subprocess

    def mock_run(*args, **kwargs):
        class MockResult:
            stdout = ""

        # Write to the temp file so shutil.move has something
        # args[0] is the command list: ["bean-format", "-c", "50", "-o", str(tmp_path), str(ledger_file)]
        cmd_list = args[0]
        if "-o" in cmd_list:
            out_idx = cmd_list.index("-o") + 1
            with open(cmd_list[out_idx], "w") as f:
                f.write("; formatted content\n")
        return MockResult()

    monkeypatch.setattr(subprocess, "run", mock_run)
    result = runner.invoke(app, ["format", str(temp_beancount_file)])
    assert result.exit_code == 0
    assert "Formatted" in result.stdout


def test_price_cmd(temp_beancount_file, monkeypatch):
    import subprocess

    def mock_run(*args, **kwargs):
        class MockResult:
            stdout = "2024-01-01 price AAPL 150.00 USD"

        return MockResult()

    monkeypatch.setattr(subprocess, "run", mock_run)
    result = runner.invoke(app, ["price", str(temp_beancount_file)])
    assert result.exit_code == 0
    assert "2024-01-01" in result.stdout

    # Test update flag
    result_update = runner.invoke(app, ["price", str(temp_beancount_file), "--update"])
    assert result_update.exit_code == 0
    assert "Appended" in result_update.stdout


def test_missing_ledger_file(monkeypatch):
    import os

    if "BEANCOUNT_FILE" in os.environ:
        monkeypatch.delenv("BEANCOUNT_FILE")
    if "BEANCOUNT_PATH" in os.environ:
        monkeypatch.delenv("BEANCOUNT_PATH")
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1
    assert "Error: No ledger file found" in result.stdout
