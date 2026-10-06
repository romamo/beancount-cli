"""Regression tests for #33: a malformed new_transaction_file pattern refuses with LEDGER_INVALID."""

import json
import textwrap
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from cli_helpers import run

from beancount_cli.models import AmountModel, PostingModel, TransactionModel
from beancount_cli.services import InvalidLedgerOptionError, TransactionService

KNOWN = ["year", "month", "day", "payee", "slug"]
POSTINGS = (
    '{"account": "Expenses:Food", "units": {"number": 50, "currency": "USD"}}',
    '{"account": "Assets:Cash", "units": {"number": -50, "currency": "USD"}}',
)


def _ledger(tmp_path: Path, pattern: str) -> Path:
    path = tmp_path / "main.beancount"
    path.write_text(
        textwrap.dedent(f"""
        option "operating_currency" "USD"

        2020-01-01 open Assets:Cash
        2020-01-01 open Expenses:Food
        2020-01-01 custom "ledger" "new_transaction_file" "{pattern}"
        """)
    )
    return path


def _add(ledger: Path, *extra: str) -> tuple[int, dict, str]:
    argv = ["transaction", "add", "--file", str(ledger), "--date", "2024-01-15"]
    argv += ["--narration", "Groceries", "--payee", "Store"]
    for posting in POSTINGS:
        argv += ["--postings", posting]
    code, out, err = run(*argv, *extra)
    return code, json.loads(out), err


def _files(tmp_path: Path) -> list[Path]:
    return sorted(p for p in tmp_path.rglob("*") if p.is_file())


@pytest.mark.parametrize("dry_run", [False, True])
def test_unknown_placeholder_is_refused(tmp_path, dry_run):
    ledger = _ledger(tmp_path, "inbox/{week}.beancount")
    before = ledger.read_text()

    code, envelope, err = _add(ledger, *(["--dry-run"] if dry_run else []))

    assert code == 80
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "LEDGER_INVALID"
    assert "new_transaction_file" in envelope["error"]["message"]
    assert "{week}" in envelope["error"]["message"]
    context = envelope["error"]["context"]
    assert context["option"] == "new_transaction_file"
    assert context["placeholder"] == "week"
    assert context["known"] == KNOWN
    assert envelope["error"]["suggestion"]
    assert err == ""
    assert _files(tmp_path) == [ledger]
    assert ledger.read_text() == before


@pytest.mark.parametrize(
    ("pattern", "placeholder"),
    [("inbox/{year.beancount", None), ("inbox/{}.beancount", ""), ("inbox/{0}.beancount", "0")],
)
def test_malformed_pattern_is_refused(tmp_path, pattern, placeholder):
    ledger = _ledger(tmp_path, pattern)

    code, envelope, err = _add(ledger)

    assert code == 80
    assert envelope["error"]["code"] == "LEDGER_INVALID"
    assert envelope["error"]["context"]["option"] == "new_transaction_file"
    assert envelope["error"]["context"]["placeholder"] == placeholder
    assert envelope["error"]["context"]["known"] == KNOWN
    assert err == ""
    assert _files(tmp_path) == [ledger]


def test_exec_line_is_refused_the_same_way(tmp_path):
    ledger = _ledger(tmp_path, "inbox/{week}.beancount")
    line = {
        "_cmd": "transaction.add",
        "file": str(ledger),
        "date": "2024-01-15",
        "narration": "Groceries",
        "postings": [json.loads(p) for p in POSTINGS],
    }

    code, out, err = run("exec", stdin=json.dumps(line) + "\n")

    envelope = json.loads(out.splitlines()[0])
    assert envelope["error"]["code"] == "LEDGER_INVALID"
    assert envelope["meta"]["exit_code"] == 80
    assert envelope["error"]["context"]["placeholder"] == "week"
    assert code != 0
    assert err == ""
    assert _files(tmp_path) == [ledger]


def test_service_raises_instead_of_writing_raw_pattern(tmp_path):
    ledger = _ledger(tmp_path, "inbox/{week}.beancount")
    tx = TransactionModel(
        date=date(2024, 1, 15),
        narration="Groceries",
        postings=[
            PostingModel(
                account="Expenses:Food", units=AmountModel(number=Decimal(50), currency="USD")
            ),
            PostingModel(
                account="Assets:Cash", units=AmountModel(number=Decimal(-50), currency="USD")
            ),
        ],
    )

    with pytest.raises(InvalidLedgerOptionError) as excinfo:
        TransactionService(ledger).add_transaction(tx)

    assert excinfo.value.placeholder == "week"
    assert _files(tmp_path) == [ledger]


def test_known_placeholders_still_write(tmp_path):
    ledger = _ledger(tmp_path, "inbox/{year}-{month}-{day}_{payee}.beancount")

    code, envelope, _ = _add(ledger)

    assert code == 0
    written = tmp_path / "inbox" / "2024-01-15_Store.beancount"
    assert envelope["data"]["file"] == str(written.resolve())
    assert "Groceries" in written.read_text()
