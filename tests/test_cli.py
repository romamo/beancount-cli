import json
import textwrap

from cli_helpers import call, run

POSTINGS = [
    {"account": "Assets:Cash", "units": {"number": "-10", "currency": "USD"}},
    {"account": "Expenses:Food", "units": {"number": "10", "currency": "USD"}},
]


def test_check_command(temp_beancount_file):
    env = call("check", ledger_file=str(temp_beancount_file))
    assert env.exit_code == 0
    assert env.data == {"file": str(temp_beancount_file), "valid": True, "errors": []}

    code, out, _ = run("check", str(temp_beancount_file), "--format", "plain")
    assert code == 0
    assert out == "No errors found.\n"


def test_check_reports_ledger_errors(temp_beancount_file):
    with open(temp_beancount_file, "a") as f:
        f.write("\n2022-01-01 INVALID_STATEMENT\n")
    env = call("check", ledger_file=str(temp_beancount_file))
    assert env.exit_code == 80
    assert env.error.code == "LEDGER_INVALID"
    assert env.data["valid"] is False
    assert env.data["errors"]
    assert env.error.context["errors"] == env.data["errors"]


def test_missing_ledger_file_is_not_found(tmp_path):
    env = call("check", ledger_file=str(tmp_path / "nope.beancount"))
    assert env.exit_code == 5
    assert env.error.code == "NOT_FOUND"
    assert env.error.message.startswith("Ledger file not found")


def test_file_defaults_to_beancount_file_env(temp_beancount_file):
    code, out, err = run("account", "list")
    assert code == 5, err

    from beancount_cli.cli import app

    env = app.call("account.list", {}, env={"BEANCOUNT_FILE": str(temp_beancount_file)})
    assert env.exit_code == 0
    assert [a["name"] for a in env.data] == ["Assets:Cash", "Expenses:Food", "Income:Salary"]


def test_global_flags_go_anywhere_command_flags_after(temp_beancount_file):
    # AGENTS.md "Flag Order": global flags before the command are accepted
    code, out, err = run("--format", "json", "account", "list", "--file", str(temp_beancount_file))
    assert code == 0, err
    assert json.loads(out)["ok"] is True

    # A command's own flag before the command exits 2
    code, out, _ = run("--file", str(temp_beancount_file), "account", "list")
    assert code == 2
    env = json.loads(out)
    assert env["error"]["code"] == "ARG_ERROR"
    assert env["error"]["context"]["flag"] == "--file"


def test_missing_required_flag_names_it_as_typed():
    # Issue #7: the error names --name as it is typed, not the field name
    code, out, _ = run("account", "create")
    assert code == 2
    env = json.loads(out)
    assert env["error"]["code"] == "ARG_ERROR"
    assert env["error"]["message"] == "Missing required option --name/-n"
    assert env["error"]["context"]["missing"] == ["name"]
    assert env["meta"]["exit_code"] == 2

    # The human rendering adds the flag's help row, a usage line, and a --help pointer
    code, out, err = run("--format", "plain", "account", "create")
    assert code == 2
    assert out == ""
    assert err == (
        "bean: ARG_ERROR: Missing required option --name/-n\n"
        "  --name, -n  Account name (e.g. Assets:Bank) (required)\n"
        "usage: bean account create --name <name> [options]\n"
        "Run 'bean account create --help' for all options.\n"
    )


def test_transaction_list(temp_beancount_file):
    env = call("transaction.list", file=str(temp_beancount_file))
    assert env.exit_code == 0
    assert [tx["payee"] for tx in env.data] == ["Employer"]
    # Postings keep their ledger order
    assert [p["account"] for p in env.data[0]["postings"]] == ["Income:Salary", "Assets:Cash"]


def test_transaction_list_fields(temp_beancount_file):
    code, out, err = run(
        "transaction", "list", "--file", str(temp_beancount_file), "--fields", "date,payee"
    )
    assert code == 0, err
    assert json.loads(out)["data"] == [{"date": "2023-01-01", "payee": "Employer"}]


def test_transaction_list_bad_query(temp_beancount_file):
    env = call("transaction.list", file=str(temp_beancount_file), where="bogus ~~ 1")
    assert env.exit_code == 82
    assert env.error.code == "QUERY_INVALID"


def test_transaction_list_unknown_bql_column_is_query_invalid(temp_beancount_file):
    # beanquery raises CompilationError (not a ValueError) for a column it does not know
    env = call("transaction.list", file=str(temp_beancount_file), where="foo = 1")
    assert env.exit_code == 82
    assert env.error.code == "QUERY_INVALID"


def test_transaction_list_bad_regex_is_arg_error(temp_beancount_file):
    for flag in ("payee", "account"):
        env = call("transaction.list", file=str(temp_beancount_file), **{flag: "("})
        assert env.exit_code == 2
        assert env.error.errors[0]["field"] == flag


def test_transaction_add(temp_beancount_file):
    env = call(
        "transaction.add",
        file=str(temp_beancount_file),
        date="2023-12-01",
        narration="CLI Test",
        postings=POSTINGS,
        tags=["food"],
    )
    assert env.exit_code == 0, env.error
    assert env.data["effect"] == "created"
    assert env.data["tags"] == ["food"]
    assert call("check", ledger_file=str(temp_beancount_file)).exit_code == 0


def test_transaction_add_postings_on_argv(temp_beancount_file):
    code, out, err = run(
        "transaction", "add", "--file", str(temp_beancount_file),
        "--date", "2023-12-01", "--narration", "Argv",
        "--postings", json.dumps(POSTINGS[0]), "--postings", json.dumps(POSTINGS[1]),
    )  # fmt: skip
    assert code == 0, err
    data = json.loads(out)["data"]
    assert [p["account"] for p in data["postings"]] == ["Assets:Cash", "Expenses:Food"]


def test_transaction_add_rejects_bad_account(temp_beancount_file):
    env = call(
        "transaction.add",
        file=str(temp_beancount_file),
        date="2023-12-01",
        narration="Bad",
        postings=[{"account": "cash", "units": {"number": "1", "currency": "USD"}}],
    )
    assert env.exit_code == 2
    assert env.error.errors[0]["field"] == "postings[0].account"


def test_transaction_add_refuses_unbalanced_postings(temp_beancount_file):
    # Regression for #16: a one-sided transaction used to be written with exit 0.
    before = temp_beancount_file.read_text()
    env = call(
        "transaction.add",
        file=str(temp_beancount_file),
        date="2024-03-01",
        narration="Bad",
        postings=[{"account": "Expenses:Food", "units": {"number": "12.50", "currency": "USD"}}],
    )
    assert env.exit_code == 81
    assert env.error.code == "TRANSACTION_INVALID"
    assert "Transaction does not balance: (12.50 USD)" in env.error.message
    assert temp_beancount_file.read_text() == before


def test_account_create(temp_beancount_file):
    env = call(
        "account.create", file=str(temp_beancount_file), name="Liabilities:Card", currency=["USD"]
    )
    assert env.exit_code == 0
    assert env.data["effect"] == "created"
    assert env.data["name"] == "Liabilities:Card"
    assert env.data["currencies"] == ["USD"]
    assert env.data["file"] == str(temp_beancount_file)
    assert "open Liabilities:Card" in env.data["entry"]


def test_account_create_existing_is_conflict(temp_beancount_file):
    env = call("account.create", file=str(temp_beancount_file), name="Assets:Cash")
    assert env.exit_code == 6
    assert env.error.code == "ALREADY_EXISTS"


def test_account_create_with_date_and_currencies(temp_beancount_file):
    code, out, err = run(
        "account", "create", "-f", str(temp_beancount_file), "-n", "Assets:Savings",
        "-d", "2024-01-01", "-c", "USD", "-c", "EUR",
    )  # fmt: skip
    assert code == 0, err
    data = json.loads(out)["data"]
    assert data["open_date"] == "2024-01-01"
    assert data["currencies"] == ["EUR", "USD"]


def test_account_balance_on_unknown_account(temp_beancount_file):
    env = call(
        "account.balance",
        file=str(temp_beancount_file),
        account="Assets:Nope",
        date="2024-01-01",
        amount="1",
        currency="USD",
    )
    assert env.exit_code == 5
    assert env.error.code == "NOT_FOUND"


def test_commodity_create(temp_beancount_file):
    env = call("commodity.create", currency="ETH", file=str(temp_beancount_file), name="Ethereum")
    assert env.exit_code == 0
    assert env.data["effect"] == "created"
    assert env.data["currency"] == "ETH"
    assert env.data["meta"] == {"name": "Ethereum"}

    again = call("commodity.create", currency="ETH", file=str(temp_beancount_file))
    assert again.exit_code == 6


def test_tree_command(temp_beancount_file):
    env = call("tree", ledger_file=str(temp_beancount_file))
    assert env.exit_code == 0
    assert env.data == {"file": str(temp_beancount_file), "includes": []}

    code, out, _ = run("tree", str(temp_beancount_file), "--format", "plain")
    assert code == 0
    assert out == f"{temp_beancount_file}\n"


def test_tree_lists_includes_depth_first(tmp_path):
    (tmp_path / "a.beancount").write_text('include "b.beancount"\n')
    (tmp_path / "b.beancount").write_text("")
    (tmp_path / "main.beancount").write_text('include "a.beancount"\n')
    env = call("tree", ledger_file=str(tmp_path / "main.beancount"))
    assert [(f["path"], f["depth"]) for f in env.data["includes"]] == [
        (str(tmp_path / "a.beancount"), 0),
        (str(tmp_path / "b.beancount"), 1),
    ]


def test_report_balance_sheet(temp_beancount_file):
    env = call("report.balance-sheet", file=str(temp_beancount_file))
    assert env.exit_code == 0
    assert {"account": "Assets:Cash", "units": {"USD": "1000.00"}, "cost": {"USD": "1000.00"}} in (
        env.data["accounts"]
    )

    code, out, _ = run(
        "report", "balance-sheet", "-f", str(temp_beancount_file), "--format", "plain"
    )
    assert code == 0
    assert out.startswith("Balance Sheet\n")


def test_report_trial_balance(temp_beancount_file):
    env = call("report.trial-balance", file=str(temp_beancount_file))
    assert env.exit_code == 0
    assert env.data["net_positions"] == [
        {
            "currency": "USD",
            "debit": "1000.00",
            "credit": "-1000.00",
            "net": "0.00",
            "balanced": True,
        }
    ]

    code, out, _ = run(
        "report", "trial-balance", "-f", str(temp_beancount_file), "--format", "plain"
    )
    assert code == 0
    assert "Trial Balance" in out
    assert "✓ Balanced" in out


def test_report_holdings(temp_beancount_file):
    env = call("report.holdings", file=str(temp_beancount_file))
    assert env.exit_code == 0
    assert env.data["currencies"] == ["USD"]
    assert env.data["accounts"][0]["account"] == "Assets:Cash"

    code, out, _ = run("report", "holdings", "-f", str(temp_beancount_file), "--format", "plain")
    assert code == 0
    assert "Holdings" in out


AUDIT_LEDGER = """
    option "operating_currency" "USD"
    2020-01-01 open Assets:Cash USD
    2020-01-01 open Expenses:Food USD

    2020-02-01 * "Store A" "Oldest"
      Expenses:Food          100 USD
      Assets:Cash           -100 USD

    2020-02-15 * "Store B" "Middle"
      Expenses:Food          200 USD
      Assets:Cash           -200 USD

    2020-03-01 * "Store C" "Newest"
      Expenses:Food          300 USD
      Assets:Cash           -300 USD
"""


def test_report_audit(tmp_path):
    path = tmp_path / "audit.beancount"
    path.write_text(textwrap.dedent(AUDIT_LEDGER))

    code, out, err = run(
        "report", "audit", "--file", str(path), "--currency", "USD", "--all", "--format", "plain"
    )
    assert code == 0, err
    assert "Audit Report: USD" in out
    lines = [line for line in out.splitlines() if "Store" in line]
    assert len(lines) == 6
    assert "Store A" in lines[0]
    assert "Store B" in lines[2]
    assert "Store C" in lines[4]

    # The last 2 transactions, oldest first
    code, out, err = run(
        "report", "audit", "--file", str(path), "--currency", "USD", "--limit", "2",
        "--format", "plain",
    )  # fmt: skip
    assert code == 0, err
    lines = [line for line in out.splitlines() if "Store" in line]
    assert len(lines) == 4
    assert "Store B" in lines[0]
    assert "Store C" in lines[2]
    assert "Showing last 2 transactions" in out

    env = call("report.audit", file=str(path), limit=2)
    assert env.data["currency"] == "USD"
    assert env.data["limited"] is True
    assert [p["description"] for p in env.data["postings"]] == ["Store B: Middle"] * 2 + [
        "Store C: Newest"
    ] * 2


def test_report_audit_needs_a_currency(clean_ledger_file):
    env = call("report.audit", file=str(clean_ledger_file))
    assert env.exit_code == 83
    assert env.error.code == "CURRENCY_REQUIRED"


def test_tx_schema():
    code, out, _ = run("transaction", "add", "--schema")
    assert code == 0
    assert "postings" in json.loads(out)["data"]["parameters"]


def test_account_list(temp_beancount_file):
    code, out, _ = run("account", "list", "--file", str(temp_beancount_file), "--format", "plain")
    assert code == 0
    assert "Assets:Cash" in out


def test_price_group_help():
    code, _, err = run("price", "--help")
    assert code == 0
    assert "check" in err and "fetch" in err


def test_report_audit_help_shows_its_flags():
    code, _, err = run("report", "audit", "--help")
    assert code == 0
    assert "--limit" in err
    assert "--all" in err


def test_account_list_csv(temp_beancount_file):
    code, out, err = run("account", "list", "-f", str(temp_beancount_file), "--format", "csv")
    assert code == 0, err
    assert out.splitlines()[0] == "name,open_date,currencies,meta"


def test_non_tty_default_is_json_envelope(temp_beancount_file):
    code, out, err = run("report", "balance-sheet", "--file", str(temp_beancount_file))
    assert code == 0, err
    assert json.loads(out)["ok"] is True
