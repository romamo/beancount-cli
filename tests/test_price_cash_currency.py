"""Tests for cash-currency price job supplementation.

beanprice silently drops declared (base, quote) pairs when the commodity is
held as cash because get_commodity_lifetimes records holdings as (base, None)
while currency_map uses (base, quote). _get_cash_currency_jobs detects and
fills this gap.
"""

import textwrap
from datetime import date

import pytest
from beancount import loader

from beancount_cli.commands.price import _get_cash_currency_jobs, _resolve_price_jobs


def _load(text: str):
    entries, errors, _ = loader.load_string(textwrap.dedent(text))
    assert not errors, errors
    return entries


@pytest.fixture
def cash_cad_entries():
    return _load("""
        option "operating_currency" "USD"

        2020-01-01 commodity CAD
          price: "USD:beanprice.sources.yahoo/CADUSD=X"

        2020-01-01 open Assets:Cash:CAD CAD
        2020-01-01 open Equity:Opening

        2020-01-15 * "Opening balance"
          Assets:Cash:CAD  1000 CAD
          Equity:Opening  -1000 CAD

        2020-02-01 price CAD 0.75 USD
    """)


def test_cash_currency_gets_jobs(cash_cad_entries):
    date_last = date(2020, 3, 1)
    inactive_jobs = _resolve_price_jobs(
        cash_cad_entries, date_last, True, update=True, fill_gaps=False
    )
    jobs = _get_cash_currency_jobs(cash_cad_entries, date_last, inactive_jobs)
    pairs = {(j.base, j.quote) for j in jobs}
    assert ("CAD", "USD") in pairs


def test_cash_currency_jobs_respect_existing_price(cash_cad_entries):
    # With --update and an existing price on 2020-02-01, no job should be generated
    # for date_last=2020-02-01 itself (already up-to-date).
    date_last = date(2020, 2, 1)
    inactive_jobs = _resolve_price_jobs(
        cash_cad_entries, date_last, True, update=True, fill_gaps=False
    )
    jobs = _get_cash_currency_jobs(cash_cad_entries, date_last, inactive_jobs)
    # date_last equals the existing price date, so beanprice considers it up-to-date.
    cad_jobs = [j for j in jobs if j.base == "CAD" and j.quote == "USD"]
    assert cad_jobs == []


def test_truly_inactive_commodity_excluded():
    """A declared commodity that was never transacted should not appear in cash jobs."""
    entries = _load("""
        option "operating_currency" "USD"

        2020-01-01 commodity CAD
          price: "USD:beanprice.sources.yahoo/CADUSD=X"

        2020-01-01 commodity EUR
          price: "USD:beanprice.sources.yahoo/EURUSD=X"

        2020-01-01 open Assets:Cash:CAD CAD
        2020-01-01 open Equity:Opening

        2020-01-15 * "Opening balance"
          Assets:Cash:CAD  1000 CAD
          Equity:Opening  -1000 CAD
    """)
    date_last = date(2020, 3, 1)
    inactive_jobs = _resolve_price_jobs(entries, date_last, True, update=True, fill_gaps=False)
    jobs = _get_cash_currency_jobs(entries, date_last, inactive_jobs)
    pairs = {(j.base, j.quote) for j in jobs}
    assert ("CAD", "USD") in pairs
    assert ("EUR", "USD") not in pairs


def test_no_cash_currencies_returns_empty():
    """When no cash holdings exist, returns empty list."""
    entries = _load("""
        option "operating_currency" "USD"

        2020-01-01 commodity AAPL
          price: "USD:beanprice.sources.yahoo/AAPL"

        2020-01-01 open Assets:Broker
        2020-01-01 open Equity:Opening

        2020-01-15 * "Buy AAPL"
          Assets:Broker  10 AAPL {150 USD}
          Equity:Opening
    """)
    date_last = date(2020, 3, 1)
    inactive_jobs = _resolve_price_jobs(entries, date_last, True, update=True, fill_gaps=False)
    jobs = _get_cash_currency_jobs(entries, date_last, inactive_jobs)
    assert jobs == []


def test_at_date_path(cash_cad_entries):
    """The non-update (at_date) path also returns jobs for cash currencies."""
    date_last = date(2020, 3, 1)
    inactive_jobs = _resolve_price_jobs(
        cash_cad_entries, date_last, True, update=False, fill_gaps=False
    )
    jobs = _get_cash_currency_jobs(cash_cad_entries, date_last, inactive_jobs)
    pairs = {(j.base, j.quote) for j in jobs}
    assert ("CAD", "USD") in pairs
