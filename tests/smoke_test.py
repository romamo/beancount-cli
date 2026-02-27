import subprocess
import sys
import tempfile
from pathlib import Path


def test_smoke():
    """
    Basic smoke test to ensure the CLI is functional and can be imported.
    """
    print("Running smoke test...")

    # 1. Check help command
    # Using sys.executable -m to ensure we test the current environment
    result = subprocess.run(
        [sys.executable, "-m", "beancount_cli.cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "Beancount CLI tool" in result.stdout

    # 2. Check version command
    result = subprocess.run(
        [sys.executable, "-m", "beancount_cli.cli", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "beancount-cli" in result.stdout

    # 3. Check transaction schema command
    result = subprocess.run(
        [sys.executable, "-m", "beancount_cli.cli", "transaction", "schema"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "TransactionModel" in result.stdout

    # 4. Check with a minimal ledger file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".beancount", delete=False) as f:
        f.write('2023-01-01 open Assets:Cash USD\n')
        temp_path = Path(f.name)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "beancount_cli.cli", "check", str(temp_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0
        assert "No errors found" in result.stdout
    finally:
        if temp_path.exists():
            temp_path.unlink()

    print("Smoke test passed.")


if __name__ == "__main__":
    try:
        test_smoke()
    except AssertionError as e:
        print(f"Smoke test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
