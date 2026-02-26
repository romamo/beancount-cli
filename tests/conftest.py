import tempfile
import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def temp_beancount_file():
    """Returns a path to a temporary beancount file with some basic content."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".beancount", delete=False) as f:
        f.write(
            textwrap.dedent("""
            option "title" "Test Ledger"
            option "operating_currency" "USD"
            
            2020-01-01 open Assets:Cash USD
            2020-01-01 open Expenses:Food USD
            2020-01-01 open Income:Salary USD
            
            2023-01-01 * "Employer" "Salary"
              Income:Salary      -1000.00 USD
              Assets:Cash         1000.00 USD
        """)
        )
        path = Path(f.name)

    yield path

    # Cleanup
    if path.exists():
        path.unlink()


@pytest.fixture
def clean_ledger_file():
    """Returns a path to an empty temporary beancount file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".beancount", delete=False) as f:
        f.write('option "title" "Empty Ledger"\n')
        path = Path(f.name)

    yield path

    if path.exists():
        path.unlink()
