import json
import subprocess
import sys
import tempfile
from pathlib import Path


def bean(*args: str) -> subprocess.CompletedProcess:
    # Using sys.executable -m to ensure we test the current environment
    return subprocess.run(
        [sys.executable, "-m", "beancount_cli.cli", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_smoke():
    """The CLI imports, describes itself, and checks a ledger."""
    result = bean("--help")
    assert result.returncode == 0
    assert "Beancount CLI tool" in result.stderr

    result = bean("--version")
    assert result.returncode == 0
    assert json.loads(result.stdout)["data"]["name"] == "bean"

    result = bean("transaction", "add", "--schema")
    assert result.returncode == 0
    assert "properties" in result.stdout

    result = bean("manifest")
    assert result.returncode == 0
    assert "transaction.add" in json.loads(result.stdout)["data"]["commands"]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".beancount", delete=False) as f:
        f.write("2023-01-01 open Assets:Cash USD\n")
        temp_path = Path(f.name)

    try:
        result = bean("check", str(temp_path))
        assert result.returncode == 0
        assert json.loads(result.stdout)["data"]["valid"] is True
    finally:
        temp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    test_smoke()
    print("Smoke test passed.")
