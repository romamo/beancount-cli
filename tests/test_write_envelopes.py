"""check, format and mutating commands answer with a JSON envelope in structured modes."""

import io
import json
from unittest.mock import patch

from beancount_cli.cli import main

POSTINGS = json.dumps(
    [
        {"account": "Expenses:Food", "units": {"number": "12.50", "currency": "USD"}},
        {"account": "Assets:Cash", "units": {"number": "-12.50", "currency": "USD"}},
    ]
)


def run_cli(*args, stdin=""):
    with (
        patch("sys.stdout", new=io.StringIO()) as stdout,
        patch("sys.stderr", new=io.StringIO()) as stderr,
        patch("sys.stdin", new=io.StringIO(stdin)),
    ):
        try:
            main(list(args))
            return 0, stdout.getvalue(), stderr.getvalue()
        except SystemExit as e:
            return (e.code or 0), stdout.getvalue(), stderr.getvalue()


def data_of(out):
    envelope = json.loads(out)
    assert envelope["ok"] is True
    return envelope["data"]


def test_account_create_dry_run_previews_without_writing(temp_beancount_file):
    before = temp_beancount_file.read_text()
    code, out, _ = run_cli(
        "account", "create", "-f", str(temp_beancount_file), "-n", "Assets:Bank", "--dry-run"
    )
    assert code == 0
    data = data_of(out)
    assert data["effect"] == "would_create"
    assert data["file"] is None
    assert "open Assets:Bank" in data["entry"]
    assert temp_beancount_file.read_text() == before


def test_account_create_table_mode_prints_message(temp_beancount_file):
    code, out, _ = run_cli(
        "account", "create", "-f", str(temp_beancount_file), "-n", "Assets:Bank", "-o", "table"
    )
    assert code == 0
    assert "Account Assets:Bank created in" in out


def test_transaction_add_writes_and_reports_file(temp_beancount_file):
    code, out, err = run_cli(
        "transaction", "add", "-f", str(temp_beancount_file),
        "--date", "2024-03-01", "--narration", "Lunch", "--postings", POSTINGS,
    )  # fmt: skip
    assert code == 0, err
    data = data_of(out)
    assert data["effect"] == "created"
    assert data["file"] == str(temp_beancount_file)
    assert data["narration"] == "Lunch"
    assert data["entry"] in temp_beancount_file.read_text()


def test_transaction_add_dry_run(temp_beancount_file):
    before = temp_beancount_file.read_text()
    code, out, err = run_cli(
        "transaction", "add", "-f", str(temp_beancount_file),
        "--date", "2024-03-01", "--narration", "Lunch", "--postings", POSTINGS, "--dry-run",
    )  # fmt: skip
    assert code == 0, err
    data = data_of(out)
    assert data["effect"] == "would_create"
    assert '2024-03-01 * "Lunch"' in data["entry"]
    assert temp_beancount_file.read_text() == before


def test_balance_and_pad_balance(temp_beancount_file):
    code, out, err = run_cli(
        "account", "balance", "-f", str(temp_beancount_file), "--account", "Assets:Cash",
        "--date", "2024-01-01", "--amount", "1000", "-c", "USD",
    )  # fmt: skip
    assert code == 0, err
    assert data_of(out)["effect"] == "created"

    code, out, err = run_cli(
        "account", "pad-balance", "-f", str(temp_beancount_file), "--account", "Assets:Cash",
        "--amount", "900", "-c", "USD", "--date", "2024-02-02", "--dry-run",
    )  # fmt: skip
    assert code == 0, err
    data = data_of(out)
    assert data["effect"] == "would_create"
    assert "pad Assets:Cash Expenses:Other" in data["entry"]
    assert "balance Assets:Cash" in data["entry"]


def test_format_noop_and_dry_run(temp_beancount_file):
    code, out, err = run_cli("format", str(temp_beancount_file))
    assert code == 0, err
    assert data_of(out)["effect"] == "updated"
    formatted = temp_beancount_file.read_text()

    code, out, err = run_cli("format", str(temp_beancount_file))
    assert code == 0, err
    assert data_of(out) == {"effect": "noop", "file": str(temp_beancount_file), "changed": False}

    messy = formatted + '\n2024-01-05 * "Misaligned"\n  Expenses:Food 1 USD\n  Assets:Cash -1 USD\n'
    temp_beancount_file.write_text(messy)
    code, out, err = run_cli("format", str(temp_beancount_file), "--dry-run")
    assert code == 0, err
    assert data_of(out)["effect"] == "would_update"
    assert temp_beancount_file.read_text() == messy


def test_exec_returns_mutating_results(temp_beancount_file):
    line = {"_cmd": "account.create", "file": str(temp_beancount_file), "name": "Assets:Exec"}
    code, out, err = run_cli("exec", "--dry-run", stdin=json.dumps(line) + "\n")
    assert code == 0, err
    result = json.loads(out.splitlines()[0])["result"]
    assert result["data"]["effect"] == "would_create"
    assert "open Assets:Exec" in result["data"]["entry"]
