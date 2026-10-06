"""--target in a missing directory, or naming a directory, fails before anything is written."""

import json
from pathlib import Path

import pytest
from cli_helpers import call, run

LEDGER = """\
2020-01-01 open Assets:Cash USD
2020-01-01 open Expenses:Food USD
"""

POSTINGS = [
    {"account": "Assets:Cash", "units": {"number": "-1", "currency": "USD"}},
    {"account": "Expenses:Food", "units": {"number": "1", "currency": "USD"}},
]

COMMANDS: dict[str, dict[str, object]] = {
    "transaction.add": {"date": "2024-01-01", "narration": "T", "postings": POSTINGS},
    "account.create": {"name": "Assets:Bank"},
    "account.balance": {
        "account": "Assets:Cash",
        "date": "2024-01-01",
        "amount": "0",
        "currency": "USD",
    },
    "account.pad-balance": {
        "account": "Assets:Cash",
        "amount": "5",
        "currency": "USD",
        "date": "2024-01-02",
    },
}


@pytest.fixture
def ledger(tmp_path: Path) -> Path:
    path = tmp_path / "main.beancount"
    path.write_text(LEDGER)
    return path


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_target_in_missing_directory_is_not_found(command: str, ledger: Path, tmp_path: Path):
    missing = tmp_path / "nodir"
    before = ledger.read_bytes()
    env = call(command, file=str(ledger), target=str(missing / "x.beancount"), **COMMANDS[command])
    assert env.exit_code == 5, env.error
    assert env.error is not None
    assert env.error.code == "NOT_FOUND"
    assert env.error.context["file"] == str(missing)
    assert str(missing) in env.error.message
    assert ledger.read_bytes() == before
    assert not missing.exists()


@pytest.mark.parametrize("command", sorted(COMMANDS))
def test_target_naming_a_directory_is_an_argument_error(command: str, ledger: Path, tmp_path: Path):
    directory = tmp_path / "adir"
    directory.mkdir()
    before = ledger.read_bytes()
    env = call(command, file=str(ledger), target=str(directory), **COMMANDS[command])
    assert env.exit_code == 2, env.error
    assert env.error is not None
    assert env.error.code == "ARG_ERROR"
    assert ledger.read_bytes() == before
    assert list(directory.iterdir()) == []


def test_target_in_existing_directory_is_written(ledger: Path, tmp_path: Path):
    target = tmp_path / "x.beancount"
    env = call(
        "transaction.add", file=str(ledger), target=str(target), **COMMANDS["transaction.add"]
    )
    assert env.exit_code == 0, env.error
    assert env.data["file"] == str(target)
    assert env.data["entry"] in target.read_text()


def test_exec_line_with_missing_target_directory(ledger: Path, tmp_path: Path):
    missing = tmp_path / "nodir"
    before = ledger.read_bytes()
    lines = [
        {"_cmd": command, "file": str(ledger), "target": str(missing / "x.beancount"), **args}
        for command, args in sorted(COMMANDS.items())
    ]
    stdin = "".join(json.dumps(line) + "\n" for line in lines)
    _, out, err = run("exec", "--ignore-errors", stdin=stdin)
    results = [json.loads(line) for line in out.splitlines()]
    assert len(results) == len(lines), err
    for result in results:
        assert result["error"]["code"] == "NOT_FOUND", result
        assert result["error"]["context"]["file"] == str(missing)
    assert ledger.read_bytes() == before
