from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from beancount_cli.models import (
    AmountModel,
    PostingModel,
    TransactionModel,
    validate_account_name,
    validate_currency_code,
)


def test_amount_model():
    amt = AmountModel(number=Decimal("100.50"), currency="USD")
    assert amt.number == Decimal("100.50")
    assert amt.currency == "USD"


def test_posting_model():
    amt = AmountModel(number=Decimal("100"), currency="USD")
    post = PostingModel(account="Assets:Cash", units=amt)
    assert post.account == "Assets:Cash"
    assert post.units.number == 100


def test_transaction_model():
    tx = TransactionModel(date=date(2023, 1, 1), narration="Test Tx", postings=[])
    assert tx.date == date(2023, 1, 1)
    assert tx.flag == "*"
    assert tx.payee is None


def test_account_name_validation():
    # Valid
    assert validate_account_name("Assets:Cash") == "Assets:Cash"

    # Invalid
    with pytest.raises(ValueError, match="Invalid account name format"):
        validate_account_name("assets:cash")

    with pytest.raises(ValueError, match="Invalid account name format"):
        validate_account_name("Assets::Cash")


def test_currency_code_validation():
    # Valid
    assert validate_currency_code("USD") == "USD"
    assert validate_currency_code("AAPL") == "AAPL"

    # Invalid
    with pytest.raises(ValueError, match="Invalid currency code format"):
        validate_currency_code("usd")

    with pytest.raises(ValueError, match="Invalid currency code format"):
        validate_currency_code("VERYLONGONECURRENCYNAMEWHICHISOVER24CHARS")


def test_model_validation_integration():
    # Should work via Pydantic
    with pytest.raises(ValidationError):
        AmountModel(number=Decimal("10"), currency="usd")

    with pytest.raises(ValidationError):
        PostingModel(account="assets:cash", units=AmountModel(number=Decimal("10"), currency="USD"))
