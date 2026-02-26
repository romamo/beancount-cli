import pytest

from beancount_cli.services import TransactionService


def test_bql_filtering_basics(temp_beancount_file):
    service = TransactionService(temp_beancount_file)

    # 1. Filter by amount
    # temp_beancount_file has a Salary transaction of 1000 USD
    txs = service.list_transactions(bql_where="number > 500")
    assert len(txs) == 1
    assert txs[0].narration == "Salary"

    # 2. Filter by non-existent amount
    txs = service.list_transactions(bql_where="number > 2000")
    assert len(txs) == 0

    # 3. Filter by payee in BQL
    txs = service.list_transactions(bql_where='payee ~ "Employer"')
    assert len(txs) == 1
    assert txs[0].payee == "Employer"


def test_bql_combined_filtering(temp_beancount_file):
    """
    Test combining Python regex filters with BQL.
    """
    service = TransactionService(temp_beancount_file)

    # Regex for account + BQL for amount
    txs = service.list_transactions(account_regex="Assets:Cash", bql_where="number > 100")
    assert len(txs) == 1

    txs = service.list_transactions(
        account_regex="Assets:Cash",
        bql_where="ABS(number) < 100",  # Salary is 1000, so ABS(number) is 1000
    )
    assert len(txs) == 0


def test_bql_syntax_error(temp_beancount_file):
    service = TransactionService(temp_beancount_file)
    # Invalid BQL syntax
    with pytest.raises(ValueError, match="BQL query failed: syntax error"):
        service.list_transactions(bql_where="invalid logic here")
