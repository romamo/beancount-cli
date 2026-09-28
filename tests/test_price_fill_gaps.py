"""Regression tests for `price fetch --fill-gaps` (issue #9).

--fill-gaps must be forwarded to beanprice so interior gaps in a commodity's
price history are backfilled even when its latest price is already current.
"""

import textwrap
from datetime import date

import pytest
from beancount import loader

from beancount_cli.commands.price import _resolve_price_jobs


@pytest.fixture
def gapped_entries():
    entries, errors, _ = loader.load_string(
        textwrap.dedent("""
            option "operating_currency" "USD"

            2026-07-01 commodity ACME
              price: "USD:beanprice.sources.yahoo/ACME"

            2026-07-01 open Assets:Broker:ACME ACME
            2026-07-01 open Assets:Cash USD

            2026-07-01 * "Buy"
              Assets:Broker:ACME  10 ACME {100 USD}
              Assets:Cash        -1000 USD

            2026-07-15 price ACME 100 USD
            2026-09-28 price ACME 110 USD
        """)
    )
    assert not errors, errors
    return entries


def _acme_dates(jobs) -> set[date]:
    return {j.date for j in jobs if (j.base, j.quote) == ("ACME", "USD")}


def test_update_without_fill_gaps_skips_interior_gap(gapped_entries):
    jobs = _resolve_price_jobs(
        gapped_entries, date(2026, 9, 29), False, update=True, fill_gaps=False
    )
    assert _acme_dates(jobs) == set()


def test_fill_gaps_backfills_interior_gap(gapped_entries):
    jobs = _resolve_price_jobs(
        gapped_entries, date(2026, 9, 29), False, update=True, fill_gaps=True
    )
    dates = _acme_dates(jobs)
    assert date(2026, 7, 16) in dates
    assert date(2026, 9, 25) in dates
    # Existing prices and weekends are not refetched
    assert date(2026, 7, 15) not in dates
    assert date(2026, 9, 28) not in dates
    assert date(2026, 7, 18) not in dates
