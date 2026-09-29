"""Regression tests for `price fetch` source errors (issue #10).

A source raising for one job must not abort the run: the error is recorded,
the remaining jobs are fetched and written, and the run exits with
PARTIAL_FAILURE.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import agentyper
import fake_price_source
import pytest
from beanprice import price as bp_price

from beancount_cli.commands.price import _fetch_price_job

TESTS_DIR = Path(__file__).parent

LEDGER = """
    option "operating_currency" "USD"

    2026-01-01 commodity GOOD
      price: "USD:fake_price_source/OK"
    2026-01-01 commodity FAIL
      price: "USD:fake_price_source/BROKEN"
    2026-01-01 commodity NONE
      price: "USD:fake_price_source/NODATA"

    2026-01-01 open Assets:Broker
    2026-01-01 open Equity:Opening

    2026-01-02 * "Buy"
      Assets:Broker   1 GOOD {1 USD}
      Assets:Broker   1 FAIL {1 USD}
      Assets:Broker   1 NONE {1 USD}
      Equity:Opening -3 USD
"""


def _run_fetch(tmp_path: Path, *args: str) -> subprocess.CompletedProcess:
    ledger = tmp_path / "main.beancount"
    ledger.write_text(textwrap.dedent(LEDGER))
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(TESTS_DIR), os.environ.get("PYTHONPATH", "")]),
        "TMPDIR": str(tmp_path),  # isolate the bean-price cache
    }
    env.pop("BEANCOUNT_FILE", None)
    return subprocess.run(
        [sys.executable, "-m", "beancount_cli.cli", "price", "fetch", str(ledger), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_source_error_does_not_abort_other_jobs(tmp_path):
    result = _run_fetch(tmp_path)

    assert result.returncode == agentyper.ExitCode.PARTIAL_FAILURE, result.stderr
    assert "price GOOD" in result.stdout
    assert "Error fetching prices" not in result.stderr
    assert "Skipped 1 jobs with source errors: FAIL" in result.stderr
    assert "connection reset by peer" in result.stderr
    assert "Skipped 1 jobs with no data from source: NONE" in result.stderr


def test_update_writes_prices_despite_source_error(tmp_path):
    result = _run_fetch(tmp_path, "--update")

    assert result.returncode == agentyper.ExitCode.PARTIAL_FAILURE, result.stderr
    ledger_text = (tmp_path / "main.beancount").read_text()
    assert "price GOOD" in ledger_text
    assert "price FAIL" not in ledger_text


def _job(ticker: str) -> bp_price.DatedPrice:
    return bp_price.DatedPrice(
        "X", "USD", None, [bp_price.PriceSource(fake_price_source, ticker, False)]
    )


def test_fetch_price_job_records_transport_error():
    assert _fetch_price_job(_job("BROKEN")) == (None, "connection reset by peer")


def test_fetch_price_job_propagates_unexpected_errors():
    with pytest.raises(RuntimeError, match="source bug"):
        _fetch_price_job(_job("BUG"))
