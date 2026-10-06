"""Tags and links come out sorted, whatever the process's PYTHONHASHSEED (#7)."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

TAGS = ["alpha", "beta", "delta", "eps", "gamma"]
LINKS = ["l1", "l2", "l3", "l4"]
SEEDS = ("1", "2", "3", "4")


def bean(seed: str, *args: str) -> str:
    env = {
        "PATH": os.environ["PATH"],
        "HOME": os.environ["HOME"],
        "BEAN_NO_UPDATE": "1",
        "PYTHONHASHSEED": seed,
    }
    result = subprocess.run(
        [sys.executable, "-m", "beancount_cli.cli", *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    return result.stdout


@pytest.fixture
def tagged_ledger(tmp_path: Path) -> Path:
    path = tmp_path / "main.beancount"
    path.write_text(
        textwrap.dedent("""
        option "operating_currency" "USD"
        2024-01-01 open Assets:Cash
        2024-01-01 open Expenses:Food
        2024-01-02 * "Store" "Groceries" #gamma #alpha #eps #beta #delta ^l3 ^l1 ^l4 ^l2
          Expenses:Food   1 USD
          Assets:Cash
        """)
    )
    return path


def test_transaction_list_tags_and_links_are_sorted(tagged_ledger):
    for seed in SEEDS:
        out = bean(seed, "transaction", "list", "--file", str(tagged_ledger))
        [tx] = json.loads(out)["data"]
        assert (tx["tags"], tx["links"]) == (TAGS, LINKS), f"PYTHONHASHSEED={seed}"


def test_transaction_list_csv_tags_and_links_are_sorted(tagged_ledger):
    outputs = {
        bean(
            seed,
            "transaction",
            "list",
            "--file",
            str(tagged_ledger),
            "--format",
            "csv",
            "--fields",
            "tags,links",
        )
        for seed in SEEDS
    }
    assert outputs == {f"tags,links\n{csv_cell(TAGS)},{csv_cell(LINKS)}\n"}


def test_transaction_add_tags_and_links_are_sorted(tagged_ledger):
    args = [
        "transaction",
        "add",
        "--file",
        str(tagged_ledger),
        "--dry-run",
        "--date",
        "2024-01-03",
        "--narration",
        "Snack",
    ]
    for tag in reversed(TAGS):
        args += ["--tags", tag]
    for link in reversed(LINKS):
        args += ["--links", link]
    for posting in (
        {"account": "Expenses:Food", "units": {"number": "1", "currency": "USD"}},
        {"account": "Assets:Cash", "units": {"number": "-1", "currency": "USD"}},
    ):
        args += ["--postings", json.dumps(posting)]
    for seed in SEEDS:
        data = json.loads(bean(seed, *args))["data"]
        assert (data["tags"], data["links"]) == (TAGS, LINKS), f"PYTHONHASHSEED={seed}"


def csv_cell(values: list[str]) -> str:
    return '"' + json.dumps(values, separators=(",", ":")).replace('"', '""') + '"'
