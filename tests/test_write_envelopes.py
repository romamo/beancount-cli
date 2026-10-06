"""check, format and the mutating commands answer with an effect-tagged envelope."""

import json

from cli_helpers import call, run

POSTINGS = [
    {"account": "Expenses:Food", "units": {"number": "12.50", "currency": "USD"}},
    {"account": "Assets:Cash", "units": {"number": "-12.50", "currency": "USD"}},
]


def test_account_create_dry_run_previews_without_writing(temp_beancount_file):
    before = temp_beancount_file.read_text()
    env = call("account.create", file=str(temp_beancount_file), name="Assets:Bank", dry_run=True)
    assert env.exit_code == 0
    assert env.data["effect"] == "would_create"
    assert env.data["file"] is None
    assert "open Assets:Bank" in env.data["entry"]
    assert temp_beancount_file.read_text() == before


def test_account_create_plain_prints_message(temp_beancount_file):
    code, out, err = run(
        "account", "create", "-f", str(temp_beancount_file), "-n", "Assets:Bank",
        "--format", "plain",
    )  # fmt: skip
    assert code == 0, err
    assert out == f"Account Assets:Bank created in {temp_beancount_file}.\n"


def test_transaction_add_writes_and_reports_file(temp_beancount_file):
    env = call(
        "transaction.add",
        file=str(temp_beancount_file),
        date="2024-03-01",
        narration="Lunch",
        postings=POSTINGS,
    )
    assert env.exit_code == 0, env.error
    assert env.data["effect"] == "created"
    assert env.data["file"] == str(temp_beancount_file)
    assert env.data["narration"] == "Lunch"
    assert env.data["entry"] in temp_beancount_file.read_text()


def test_transaction_add_dry_run(temp_beancount_file):
    before = temp_beancount_file.read_text()
    env = call(
        "transaction.add",
        file=str(temp_beancount_file),
        date="2024-03-01",
        narration="Lunch",
        postings=POSTINGS,
        dry_run=True,
    )
    assert env.exit_code == 0, env.error
    assert env.data["effect"] == "would_create"
    assert '2024-03-01 * "Lunch"' in env.data["entry"]
    assert temp_beancount_file.read_text() == before


def test_balance_and_pad_balance(temp_beancount_file):
    env = call(
        "account.balance",
        file=str(temp_beancount_file),
        account="Assets:Cash",
        date="2024-01-01",
        amount="1000",
        currency="USD",
    )
    assert env.exit_code == 0, env.error
    assert env.data["effect"] == "created"

    env = call(
        "account.pad-balance",
        file=str(temp_beancount_file),
        account="Assets:Cash",
        amount="900",
        currency="USD",
        date="2024-02-02",
        dry_run=True,
    )
    assert env.exit_code == 0, env.error
    assert env.data["effect"] == "would_create"
    assert env.data["balance_date"] == "2024-02-02"
    assert "pad Assets:Cash Expenses:Other" in env.data["entry"]
    assert "balance Assets:Cash" in env.data["entry"]


def test_format_noop_and_dry_run(temp_beancount_file):
    env = call("format", ledger_file=str(temp_beancount_file))
    assert env.exit_code == 0, env.error
    assert env.data["effect"] == "updated"
    formatted = temp_beancount_file.read_text()

    env = call("format", ledger_file=str(temp_beancount_file))
    assert env.data == {"effect": "noop", "file": str(temp_beancount_file), "changed": False}

    messy = formatted + '\n2024-01-05 * "Misaligned"\n  Expenses:Food 1 USD\n  Assets:Cash -1 USD\n'
    temp_beancount_file.write_text(messy)
    env = call("format", ledger_file=str(temp_beancount_file), dry_run=True)
    assert env.data["effect"] == "would_update"
    assert temp_beancount_file.read_text() == messy


def test_commodity_import_from_stdin(tmp_path):
    ledger = tmp_path / "main.beancount"
    commodities = tmp_path / "commodities.beancount"
    commodities.write_text("2020-01-01 commodity USD\n")
    ledger.write_text(
        'include "commodities.beancount"\n2020-01-01 custom "ledger" "commodities_file" "commodities.beancount"\n'
    )
    stdin = '2020-01-01 commodity BTC\n  name: "Bitcoin"\n2020-01-01 commodity USD\n'
    code, out, err = run("commodity", "import", "-f", str(ledger), stdin=stdin)
    assert code == 0, err
    data = json.loads(out)["data"]
    assert data["effect"] == "created"
    assert data["results"] == [
        {"currency": "BTC", "action": "added"},
        {"currency": "USD", "action": "skipped"},
    ]
    assert "commodity BTC" in commodities.read_text()


def test_commodity_import_rejects_bad_input(temp_beancount_file):
    code, out, _ = run("commodity", "import", "-f", str(temp_beancount_file), stdin="garbage\n")
    assert code == 84
    assert json.loads(out)["error"]["code"] == "DIRECTIVES_INVALID"


def test_exec_returns_mutating_results(temp_beancount_file):
    lines = [
        {"_cmd": "account.create", "file": str(temp_beancount_file), "name": "Assets:Exec"},
        {
            "_cmd": "transaction.add",
            "file": str(temp_beancount_file),
            "date": "2024-01-15",
            "narration": "Groceries",
            "postings": POSTINGS,
        },
    ]
    stdin = "".join(json.dumps(line) + "\n" for line in lines)
    code, out, err = run("exec", "--dry-run", stdin=stdin)
    assert code == 0, err
    results = [json.loads(line) for line in out.splitlines()]
    assert [r["data"]["effect"] for r in results] == ["would_create", "would_create"]
    assert "open Assets:Exec" in results[0]["data"]["entry"]
