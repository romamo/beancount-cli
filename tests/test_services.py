from datetime import date
from decimal import Decimal

from beancount_cli.models import AccountModel, AmountModel, PostingModel, TransactionModel
from beancount_cli.services import (
    AccountService,
    CommodityService,
    LedgerService,
    TransactionService,
)


def test_ledger_service_load(temp_beancount_file):
    service = LedgerService(temp_beancount_file)
    service.load()
    assert len(service.entries) > 0
    accounts = service.get_accounts()
    assert "Assets:Cash" in accounts


def test_add_transaction(temp_beancount_file):
    service = TransactionService(temp_beancount_file)

    tx = TransactionModel(
        date=date(2023, 10, 1),
        narration="Test Add",
        postings=[
            PostingModel(
                account="Expenses:Food", units=AmountModel(number=Decimal("50.00"), currency="USD")
            ),
            PostingModel(
                account="Assets:Cash", units=AmountModel(number=Decimal("-50.00"), currency="USD")
            ),
        ],
    )

    service.add_transaction(tx)

    # Reload and verify
    ledger = LedgerService(temp_beancount_file)
    ledger.load()
    # Find the new transaction
    found = False
    for e in ledger.entries:
        if hasattr(e, "narration") and e.narration == "Test Add":
            found = True
            break
    assert found


def test_create_account(temp_beancount_file):
    service = AccountService(temp_beancount_file)
    model = AccountModel(name="Assets:NewBank", currencies=["USD"])
    service.create_account(model)

    ledger = LedgerService(temp_beancount_file)
    ledger.load()
    accounts = ledger.get_accounts()
    assert "Assets:NewBank" in accounts


def test_create_commodity(temp_beancount_file):
    service = CommodityService(temp_beancount_file)
    service.create_commodity("BTC", name="Bitcoin")

    ledger = LedgerService(temp_beancount_file)
    ledger.load()
    commodities = ledger.get_commodities()
    assert "BTC" in commodities


def test_add_transaction_directory_mode(tmp_path):
    # Setup: Create a directory for transactions
    # Use tmp_path to ensure clean state
    ledger_file = tmp_path / "main.beancount"
    tx_dir = tmp_path / "tx_inbox"
    tx_dir.mkdir()

    ledger_file.write_text(
        'option "title" "Test"\n'
        'option "operating_currency" "USD"\n'
        "2020-01-01 open Assets:Cash USD\n"
        "2020-01-01 open Expenses:Food USD\n"
        f'2020-01-01 custom "cli-config" "new_transaction_file" "{tx_dir.name}"'
    )

    service = TransactionService(ledger_file)

    tx = TransactionModel(
        date=date(2023, 11, 1),
        narration="Dir Test",
        postings=[
            PostingModel(
                account="Expenses:Food", units=AmountModel(number=Decimal("15.00"), currency="USD")
            ),
            PostingModel(
                account="Assets:Cash", units=AmountModel(number=Decimal("-15.00"), currency="USD")
            ),
        ],
    )

    service.add_transaction(tx)

    # Verify a file was created in tx_dir
    files = list(tx_dir.glob("*.beancount"))
    assert len(files) == 1
    content = files[0].read_text()
    assert "Dir Test" in content


def test_report_balances(temp_beancount_file):
    service = TransactionService(temp_beancount_file)
    tx = TransactionModel(
        date=date(2023, 11, 1),
        narration="Report Test",
        postings=[
            PostingModel(
                account="Expenses:Food", units=AmountModel(number=Decimal("10.00"), currency="USD")
            ),
            PostingModel(
                account="Assets:Cash", units=AmountModel(number=Decimal("-10.00"), currency="USD")
            ),
        ],
    )
    service.add_transaction(tx)

    from beancount_cli.services import LedgerService, ReportService

    ledger_service = LedgerService(temp_beancount_file)
    report_service = ReportService(ledger_service)

    balances = report_service.get_balances()
    assert "Assets:Cash" in balances
    # Fixture starts with 1000, we subtracted 10
    assert balances["Assets:Cash"]["units"]["USD"] == Decimal("990.00")
    assert "Expenses:Food" in balances
    assert balances["Expenses:Food"]["units"]["USD"] == Decimal("10.00")


def test_holdings_in_target_currency_equal_position_amount(tmp_path):
    """When an asset is held in the report currency, Value and Cost equal the position.

    For positions already in the target currency (e.g. EUR asset with report in EUR),
    market value and cost basis must both equal the position amount. They must not
    be doubled by counting the position both as "in target" and again after conversion.
    """
    ledger_file = tmp_path / "ledger.beancount"
    position_amount = "1000.00"
    ledger_file.write_text(
        'option "title" "Holdings test"\n'
        'option "operating_currency" "EUR"\n'
        "2020-01-01 open Assets:Fixed:Item EUR\n"
        "2022-01-01 * \"Acquired\" \"Item\"\n"
        f"  Assets:Fixed:Item    {position_amount} EUR\n"
        f"  Equity:Opening      -{position_amount} EUR\n"
    )
    from beancount_cli.services import LedgerService, ReportService

    ledger_service = LedgerService(ledger_file)
    ledger_service.load()
    report_service = ReportService(ledger_service)
    expected = Decimal(position_amount)

    for valuation in ("market", "cost"):
        holdings = report_service.get_holdings(
            valuation=valuation, target_currencies=["EUR"]
        )
        assert "accounts" in holdings
        assert "Assets:Fixed:Item" in holdings["accounts"]
        acc = holdings["accounts"]["Assets:Fixed:Item"]
        assert acc["market_values"]["EUR"] == expected, (
            f"valuation={valuation}: market value should equal position ({expected})"
        )
        assert acc["cost_basis"]["EUR"] == expected, (
            f"valuation={valuation}: cost basis should equal position ({expected})"
        )
    assert holdings["totals"]["EUR"]["market"] == expected
    assert holdings["totals"]["EUR"]["cost"] == expected
