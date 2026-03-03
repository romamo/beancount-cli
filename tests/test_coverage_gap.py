import json as jsonlib

from beancount_cli.cli import main


def _run_cli(*args):
    import io
    from unittest.mock import patch

    with patch("sys.stdout", new=io.StringIO()) as stdout:
        with patch("sys.stderr", new=io.StringIO()) as stderr:
            try:
                main(list(args))
                return 0, stdout.getvalue(), stderr.getvalue()
            except SystemExit as e:
                code = e.code if e.code is not None else 0
                return code, stdout.getvalue(), stderr.getvalue()


def test_report_holdings_json(temp_beancount_file):
    """Exercises the holdings JSON output path (render_output(holdings, format='json'))."""
    code, out, _ = _run_cli("report", "holdings", str(temp_beancount_file), "--format", "json")
    data = jsonlib.loads(out)
    if isinstance(data, list):
        if data:
            assert "Account" in data[0]
    else:
        assert "Account" in data


def test_tx_list_json_format(temp_beancount_file):
    """Exercises the JSON format path in tx_list_cmd."""
    code, out, _ = _run_cli("transaction", "list", str(temp_beancount_file), "--format", "json")
    data = jsonlib.loads(out)
    assert isinstance(data, (list, dict))


def test_account_create_json_batch(temp_beancount_file):
    """Exercises the JSON batch path in account_create_cmd."""
    payload = jsonlib.dumps(
        [{"name": "Assets:Savings2", "open_date": "2024-01-01", "currencies": ["USD"]}]
    )
    code, out, err = _run_cli("account", "create", str(temp_beancount_file), "--json", payload)
    assert code in (0, None)


def test_check_cmd_with_errors(temp_beancount_file):
    # write corrupt data
    with open(temp_beancount_file, "a") as f:
        f.write("\n2022-01-01 INVALID_STATEMENT\n")
    code, out, err = _run_cli("check", str(temp_beancount_file))
    assert code != 0
    assert "Invalid" in out or "Invalid" in err or "syntax error" in out or "syntax error" in err


def test_report_audit_json(temp_beancount_file):
    code, out, err = _run_cli(
        "report", "audit", str(temp_beancount_file), "--currency", "USD", "--format", "json"
    )
    assert code == 0
    data = jsonlib.loads(out)
    assert isinstance(data, list)


def test_report_balance_sheet_csv(temp_beancount_file):
    code, out, err = _run_cli(
        "report", "balance-sheet", str(temp_beancount_file), "--format", "csv"
    )
    assert code == 0
    assert "Account" in out or "Account" in err


def test_report_trial_balance_csv(temp_beancount_file):
    code, out, err = _run_cli(
        "report", "trial-balance", str(temp_beancount_file), "--format", "csv"
    )
    assert code == 0
    assert "Account" in out or "Account" in err
