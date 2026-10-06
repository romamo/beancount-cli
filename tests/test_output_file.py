"""--output-file in a missing directory fails before anything is written (#32)."""

import json
from pathlib import Path

import pytest
from cli_helpers import run

LEDGER = """\
2020-01-01 commodity USD
2020-01-01 open Assets:Cash USD
"""

STDIN = {"export": "", "import": "2020-01-01 commodity EUR\n"}


@pytest.fixture
def ledger(tmp_path: Path) -> Path:
    path = tmp_path / "main.beancount"
    path.write_text(LEDGER)
    return path


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("command", sorted(STDIN))
def test_output_file_in_missing_directory_is_not_found(
    command: str, dry_run: bool, ledger: Path, tmp_path: Path
):
    missing = tmp_path / "nodir"
    before = ledger.read_bytes()
    flags = ["--dry-run"] if dry_run else []
    code, out, err = run(
        "commodity",
        command,
        "--file",
        str(ledger),
        "--output-file",
        str(missing / "c.beancount"),
        *flags,
        stdin=STDIN[command],
    )
    envelope = json.loads(out)
    assert code == 5, err
    assert envelope["meta"]["exit_code"] == 5
    assert envelope["error"]["code"] == "NOT_FOUND"
    assert envelope["error"]["context"]["file"] == str(missing)
    assert envelope["error"]["message"] == f"Directory of --output-file not found: {missing}"
    assert "--output-file" in envelope["error"]["suggestion"]
    assert ledger.read_bytes() == before
    assert not missing.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["main.beancount"]


def test_export_output_file_in_existing_directory_is_written(ledger: Path, tmp_path: Path):
    output = tmp_path / "c.beancount"
    code, out, err = run("commodity", "export", "--file", str(ledger), "--output-file", str(output))
    envelope = json.loads(out)
    assert code == 0, err
    assert envelope["data"]["effect"] == "created"
    assert "commodity USD" in output.read_text()
