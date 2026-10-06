"""Regression tests for #16: `transaction add` must refuse postings that don't balance."""

import json
import textwrap
from decimal import Decimal
from pathlib import Path

import pytest
from cli_helpers import call, run

from beancount_cli.models import AmountModel, CostModel, PostingModel, TransactionModel
from beancount_cli.services import LedgerService, TransactionService, ValidationService


@pytest.fixture
def ledger_file(tmp_path: Path) -> Path:
    path = tmp_path / "main.beancount"
    path.write_text(
        textwrap.dedent("""
        option "operating_currency" "USD"

        2020-01-01 open Assets:Cash
        2020-01-01 open Assets:EUR
        2020-01-01 open Assets:Broker
        2020-01-01 open Expenses:Food
        """)
    )
    return path


def _posting(
    account: str,
    number: str,
    currency: str,
    cost: tuple[str, str] | None = None,
    price: tuple[str, str] | None = None,
) -> PostingModel:
    return PostingModel(
        account=account,
        units=AmountModel(number=Decimal(number), currency=currency),
        cost=CostModel(number=Decimal(cost[0]), currency=cost[1]) if cost else None,
        price=AmountModel(number=Decimal(price[0]), currency=price[1]) if price else None,
    )


def _validate(ledger_file: Path, *postings: PostingModel) -> list[str]:
    tx = TransactionModel(date="2024-03-01", narration="Test", postings=list(postings))
    return ValidationService(LedgerService(ledger_file)).validate_transaction(tx)


def test_one_sided_transaction_is_refused(ledger_file):
    errors = _validate(ledger_file, _posting("Expenses:Food", "12.50", "USD"))
    assert errors == ["Transaction does not balance: (12.50 USD)"]


def test_transaction_off_by_a_cent_is_refused(ledger_file):
    errors = _validate(
        ledger_file,
        _posting("Expenses:Food", "50.00", "USD"),
        _posting("Assets:Cash", "-49.99", "USD"),
    )
    assert errors == ["Transaction does not balance: (0.01 USD)"]


def test_transaction_balanced_within_tolerance_passes(ledger_file):
    # Tolerance inferred from the 2-decimal leg is 0.005; the residual is 0.004.
    errors = _validate(
        ledger_file,
        _posting("Expenses:Food", "10.004", "USD"),
        _posting("Assets:Cash", "-10.00", "USD"),
    )
    assert errors == []


def test_transaction_balanced_at_cost_passes(ledger_file):
    errors = _validate(
        ledger_file,
        _posting("Assets:Broker", "10", "STOCK", cost=("15.00", "USD")),
        _posting("Assets:Cash", "-150.00", "USD"),
    )
    assert errors == []


def test_transaction_unbalanced_at_cost_is_refused(ledger_file):
    errors = _validate(
        ledger_file,
        _posting("Assets:Broker", "10", "STOCK", cost=("15.00", "USD")),
        _posting("Assets:Cash", "-140.00", "USD"),
    )
    assert errors == ["Transaction does not balance: (10.00 USD)"]


def test_transaction_balanced_at_price_passes(ledger_file):
    errors = _validate(
        ledger_file,
        _posting("Assets:Cash", "-100.00", "USD", price=("0.90", "EUR")),
        _posting("Assets:EUR", "90.00", "EUR"),
    )
    assert errors == []


def test_transaction_unbalanced_at_price_is_refused(ledger_file):
    errors = _validate(
        ledger_file,
        _posting("Assets:Cash", "-100.00", "USD", price=("0.90", "EUR")),
        _posting("Assets:EUR", "91.00", "EUR"),
    )
    assert errors == ["Transaction does not balance: (1.0000 EUR)"]


def test_multi_currency_transaction_balanced_per_currency_passes(ledger_file):
    errors = _validate(
        ledger_file,
        _posting("Expenses:Food", "50.00", "USD"),
        _posting("Assets:Cash", "-50.00", "USD"),
        _posting("Expenses:Food", "20.00", "EUR"),
        _posting("Assets:EUR", "-20.00", "EUR"),
    )
    assert errors == []


def test_multi_currency_transaction_reports_each_unbalanced_currency(ledger_file):
    errors = _validate(
        ledger_file,
        _posting("Expenses:Food", "50.00", "USD"),
        _posting("Assets:EUR", "-50.00", "EUR"),
    )
    assert len(errors) == 1
    assert errors[0].startswith("Transaction does not balance: (")
    assert "50.00 USD" in errors[0]
    assert "-50.00 EUR" in errors[0]


def test_unbalanced_transaction_is_not_written(ledger_file):
    before = ledger_file.read_text()
    tx = TransactionModel(
        date="2024-03-01",
        narration="Bad",
        postings=[_posting("Expenses:Food", "12.50", "USD")],
    )
    with pytest.raises(ValueError, match=r"Transaction does not balance: \(12\.50 USD\)"):
        TransactionService(ledger_file).add_transaction(tx)
    assert ledger_file.read_text() == before


def test_draft_keeps_warn_only_behaviour(ledger_file, capsys):
    tx = TransactionModel(
        date="2024-03-01",
        narration="Draft",
        postings=[_posting("Expenses:Food", "12.50", "USD")],
    )
    TransactionService(ledger_file).add_transaction(tx, draft=True)
    assert capsys.readouterr().err == ""
    assert '2024-03-01 ! "Draft"' in ledger_file.read_text()


def test_render_draft_returns_its_problems(ledger_file):
    tx = TransactionModel(
        date="2024-03-01",
        narration="Draft",
        postings=[_posting("Expenses:Food", "12.50", "USD")],
    )
    rendered = TransactionService(ledger_file).render_transaction(tx, draft=True)
    assert rendered.problems == ("Transaction does not balance: (12.50 USD)",)
    assert '2024-03-01 ! "Draft"' in rendered.entry


# #22: a draft's validation problems are envelope warnings, not ad hoc stderr lines


def _add_draft(ledger_file: Path, *postings: dict[str, object]):
    return call(
        "transaction.add",
        file=str(ledger_file),
        date="2024-03-01",
        narration="Draft",
        postings=list(postings),
        draft=True,
    )


def _leg(account: str, number: str) -> dict[str, object]:
    return {"account": account, "units": {"number": number, "currency": "USD"}}


def test_unbalanced_draft_warns_in_the_envelope(ledger_file):
    env = _add_draft(ledger_file, _leg("Assets:Cash", "-1"), _leg("Expenses:Food", "2"))
    assert env.exit_code == 0, env.error
    assert env.data["effect"] == "created"
    assert [(w.code, w.message) for w in env.warnings] == [
        ("TRANSACTION_DRAFT_INVALID", "Transaction does not balance: (1 USD)")
    ]
    assert '2024-03-01 ! "Draft"' in ledger_file.read_text()


def test_draft_with_two_problems_warns_twice(ledger_file):
    env = _add_draft(ledger_file, _leg("Assets:Missing", "-1"), _leg("Expenses:Food", "2"))
    assert env.exit_code == 0, env.error
    assert [(w.code, w.message) for w in env.warnings] == [
        (
            "TRANSACTION_DRAFT_INVALID",
            "Account 'Assets:Missing' does not exist (no Open directive).",
        ),
        ("TRANSACTION_DRAFT_INVALID", "Transaction does not balance: (1 USD)"),
    ]


def test_valid_draft_has_no_warnings(ledger_file):
    env = _add_draft(ledger_file, _leg("Assets:Cash", "-1"), _leg("Expenses:Food", "1"))
    assert env.exit_code == 0, env.error
    assert env.warnings == ()


def test_unbalanced_draft_warns_off_a_terminal_without_ad_hoc_lines(ledger_file):
    code, out, err = run(
        "transaction", "add", "-f", str(ledger_file), "--date", "2024-03-01",
        "--narration", "Draft", "--draft",
        "--postings", json.dumps(_leg("Assets:Cash", "-1")),
        "--postings", json.dumps(_leg("Expenses:Food", "2")),
    )  # fmt: skip
    assert code == 0, err
    assert "Transaction failed validation" not in err
    warnings = json.loads(out)["warnings"]
    assert [(w["code"], w["message"]) for w in warnings] == [
        ("TRANSACTION_DRAFT_INVALID", "Transaction does not balance: (1 USD)")
    ]


def test_exec_draft_line_warns(ledger_file):
    line = {
        "_cmd": "transaction.add",
        "file": str(ledger_file),
        "date": "2024-03-01",
        "narration": "Draft",
        "draft": True,
        "postings": [_leg("Assets:Cash", "-1"), _leg("Expenses:Food", "2")],
    }
    code, out, err = run("exec", stdin=json.dumps(line) + "\n")
    assert code == 0, err
    (result,) = [json.loads(r) for r in out.splitlines()]
    assert [(w["code"], w["message"]) for w in result["warnings"]] == [
        ("TRANSACTION_DRAFT_INVALID", "Transaction does not balance: (1 USD)")
    ]
    assert '2024-03-01 ! "Draft"' in ledger_file.read_text()
