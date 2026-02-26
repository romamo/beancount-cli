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
