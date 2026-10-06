"""Regression tests for `price fetch` source errors (issue #10).

A source raising for one job must not abort the run: the error is recorded,
the remaining jobs are fetched and written, and the run exits with
PARTIAL_FAILURE.
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import fake_price_source
import pytest
from beancount import loader
from beancount.core import data
from beancount.parser import parser
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


def _run_fetch(
    tmp_path: Path, *args: str, ledger_text: str = LEDGER
) -> subprocess.CompletedProcess:
    ledger = tmp_path / "main.beancount"
    ledger.write_text(textwrap.dedent(ledger_text))
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

    assert result.returncode == 3, result.stderr
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "PARTIAL_FAILURE"
    assert envelope["error"]["message"].startswith("Skipped 1 jobs with source errors: FAIL")
    assert "connection reset by peer" in envelope["error"]["message"]
    data = envelope["data"]
    assert [p["currency"] for p in data["prices"]] == ["GOOD"]
    assert data["errors"] == [{"job": "FAIL on latest", "error": "connection reset by peer"}]
    assert data["no_data"] == ["NONE on latest"]
    assert "PRICES_NO_DATA" in [w["code"] for w in envelope["warnings"]]


def test_update_writes_prices_despite_source_error(tmp_path):
    result = _run_fetch(tmp_path, "--update")

    assert result.returncode == 3, result.stderr
    assert json.loads(result.stdout)["data"]["effect"] == "created"
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


GOOD_ONLY = """
    option "operating_currency" "USD"

    2026-01-01 commodity GOOD
      price: "USD:fake_price_source/OK"

    2026-01-01 open Assets:Broker
    2026-01-01 open Equity:Opening

    2026-01-02 * "Buy"
      Assets:Broker   1 GOOD {1 USD}
      Equity:Opening -1 USD
"""


def _assert_only_directives(stdout: str) -> None:
    entries, errors, _ = parser.parse_string(stdout)
    assert errors == []
    assert all(isinstance(e, data.Price) for e in entries)


@pytest.mark.parametrize("update", [False, True])
def test_plain_output_is_appendable_beancount(tmp_path, update):
    """#17: plain stdout holds only price directives; status lines go to stderr"""
    flags = ("--update",) if update else ()
    result = _run_fetch(tmp_path, "--format", "plain", "--verbose", *flags, ledger_text=GOOD_ONLY)

    assert result.returncode == 0, result.stderr
    _assert_only_directives(result.stdout)
    assert "price GOOD" in result.stdout
    if update:
        assert "Appended 1 new prices" in result.stderr


def test_plain_output_is_empty_when_nothing_is_new(tmp_path):
    ledger_text = GOOD_ONLY + "\n    2020-01-01 open Assets:Unused\n"
    ledger_text = ledger_text.replace('price: "USD:fake_price_source/OK"', "")
    result = _run_fetch(tmp_path, "--format", "plain", "--verbose", ledger_text=ledger_text)

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert "No new prices found." in result.stderr


def test_plain_dry_run_is_beancount_comments(tmp_path):
    """#23: the dry-run job list stays on stdout, but as comments that load cleanly"""
    result = _run_fetch(
        tmp_path, "--dry-run", "--format", "plain", "--verbose", ledger_text=GOOD_ONLY
    )

    assert result.returncode == 0, result.stderr
    entries, errors, _ = loader.load_string(result.stdout)
    assert errors == []
    assert entries == []
    assert all(line.startswith(";") for line in result.stdout.splitlines())
    assert "; Dry run: 1 jobs generated." in result.stdout
    assert "fake_price_source(OK)" in result.stdout


def test_json_dry_run_lists_jobs_unprefixed(tmp_path):
    result = _run_fetch(tmp_path, "--dry-run", "--format", "json", ledger_text=GOOD_ONLY)

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)["data"]
    assert data["effect"] == "would_create"
    assert len(data["jobs"]) == 1
    assert data["jobs"][0].startswith("GOOD /USD")
