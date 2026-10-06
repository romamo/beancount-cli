# AGENTS.md - Beancount CLI Guide for AI End Agents

This document provides instructions for **AI Agents** operating the Beancount CLI to manage or query a user's accounting data. 

*(If you are an AI Coding Agent tasked with modifying the python source code of this repository, please refer to `CODING_AGENTS.md` instead).*

---

## 1. Operating Rules & Workflows

If you are executing shell commands to help a human analyze or modify their `main.beancount` ledger, adhere to the following operational rules:

### Core Configuration & Bootstrapping
- **Ledger Path**: The CLI requires a target `.beancount` file. Pass it with `--file /path/to/main.beancount` (or `-f`), or set `BEANCOUNT_FILE` (`BEAN_FILE` also works and wins when both are set). Without either, `./main.beancount` is used.
- **Flag Order**: A command's own flags (under `Flags` in its `--help`, such as `--file`/`-f`, `--limit`, `--dry-run`) go after the command path: `uv run bean account list --file main.beancount`. One before the command exits `2` with a suggestion showing the right order. Global flags (under `Global flags`, such as `--format`, `--fields`, `--schema`, `--max-output`, `--help`/`-h`) go before or after it.
- **Self Discovery**: `uv run bean manifest` describes every command, flag, output schema, and exit code in one JSON document. For one command, run `uv run bean <command> --schema`, or `--help` for prose.

### Available Capabilities (High-Level)
- **`account list/create/balance/pad-balance`**: List and open accounts, assert a balance, or adjust a balance using a Pad directive.
- **`transaction list/add`**: Query and insert accounting transactions.
- **`commodity list/create/check/import/export`**: Manage commodities. Use `check` to find used currencies missing a declaration.
- **`price check/check-anomalies/fetch`**: Manage price data and discovery.
   - `check`: Identify periods of missing price data for held assets. Supports `--rate (daily, weekday, weekly, monthly)`.
   - `fetch`: Wrapper for `bean-price` to fetch latest quotes. Supports `--update`, `--dry-run`, `--inactive`, and `--fill-gaps`.
- **`report`**: Generate detailed mathematical rollups (`balance-sheet`, `trial-balance`, `holdings`, `audit`).
- **`check/format/tree`**: Validate the ledger, keep its text formatted, and view its include tree.

### Output
- **JSON envelope**: When stdout is not a terminal, every command answers with one JSON object: `{"ok": true|false, "data": ..., "error": ..., "warnings": [...], "meta": {...}}`. Read results from `data` and failures from `error.code`; `meta.exit_code` repeats the exit code.
- **Effects**: Mutating commands report `data.effect`: `created`, `updated`, or `noop`, and `would_create` or `would_update` under `--dry-run` (then `meta.dry_run` is `true`). The written file is `data.file` and the directive text is `data.entry`.
- **Fewer tokens**: `--fields date,payee` keeps only those keys; `--format csv` or `--format tsv` writes lists as rows.
- **Lists are paginated**: `transaction list`, `account list`, `commodity list`, `commodity check`, `price check`, and `price check-anomalies` return 20 items by default. `meta.pagination.has_more` says whether more exist; pass `meta.pagination.next_cursor` as `--cursor`, or `--limit 0` for all.
- **Human display**: `--format plain` (the default at a terminal) prints tables. Only use it if you are dumping the output directly to the user's terminal.

### Advanced Data Pipelines
- **Native BQL**: `transaction list` supports Beancount Query Language (BQL) directly via the `--where` flag (e.g., `uv run bean transaction list --where "account ~ 'Expenses'"`).
- **Postings**: on the command line each `--postings` takes one posting as a JSON object; repeat the flag for each posting. In `exec` lines and `--raw-payload`, `postings` is a JSON array.
- **Batch Processing**: Never loop shell executions to insert items one-by-one! Use `bean exec` to dispatch a JSONL stream — one JSON object per line — that can mix any command type in a single pass:
   ```bash
   # Mixed-command JSONL stream written to the ledger
   cat commands.jsonl | uv run bean exec

   # Same stream, preview without writing
   cat commands.jsonl | uv run bean exec --dry-run
   ```
   Each line must have a `_cmd` field naming the command by its dotted path (e.g. `transaction.add`, `account.create`, `commodity.create`). The other keys are the command's arguments, named as its flags with `_` for `-` (`pad_account`, `dry_run`). Each line answers with its own JSON envelope; `meta._line` is the line number.

   **`transaction.add` example payload:**
   ```json
   {"_cmd": "transaction.add", "date": "2024-01-15", "narration": "Groceries", "payee": "Store", "postings": [{"account": "Expenses:Food", "units": {"number": 50, "currency": "USD"}}, {"account": "Assets:Cash", "units": {"number": -50, "currency": "USD"}}]}
   ```

### Exit Codes

Branch on the exit code or `error.code`, not on message text. Every command lists the codes it can return in `bean manifest` and `--schema`, keyed by number with a name. The name matches `error.code` for every code but `6`: the manifest names it `CONFLICT`, while the envelope's `error.code` is `ALREADY_EXISTS`.

| Code | `error.code` | Meaning | What to do |
|---|---|---|---|
| `0` | | Success | Continue |
| `1` | e.g. `GENERAL_ERROR` | Unexpected failure | Inspect the error; retrying unchanged will likely fail again |
| `2` | `ARG_ERROR` | Bad or missing argument, unknown flag or command; `error.errors` lists each problem with its `field` | Fix the input and reissue |
| `3` | `PARTIAL_FAILURE` | `price fetch` where some sources failed; the fetched prices are still written and in `data` | Retry only the jobs in `data.errors` |
| `5` | `NOT_FOUND` | Ledger file, account, or `commodities_file` does not exist | Fix the path or create the account |
| `6` | `ALREADY_EXISTS` (manifest name `CONFLICT`) | `account create` or `commodity create` for one that exists; `data` names the existing account or commodity | Nothing to do; it exists |
| `80` | `LEDGER_INVALID` | `check` found ledger errors (`error.context.errors` lists them), or `transaction add` found a malformed `new_transaction_file` pattern (`error.context` names the `option`, the `placeholder`, and the `known` ones) | Fix the ledger |
| `81` | `TRANSACTION_INVALID` | `transaction add` names an account that is not open or an undeclared currency, or its postings do not balance | Open the account, declare the commodity, or fix the amounts |
| `82` | `QUERY_INVALID` | `transaction list --where` with BQL that fails | Fix the query |
| `83` | `CURRENCY_REQUIRED` | `report audit` without `--currency` on a ledger with no operating currency | Pass `--currency` |
| `84` | `DIRECTIVES_INVALID` | `commodity import` input is not valid beancount | Fix the input |
| `85` | `FORMAT_FAILED` | `bean-format` failed | Fix the ledger syntax |
| `86` | `CONVERSION_FAILED` | A report could not convert to `--convert` | Add prices or drop `--convert` |

Before v0.6.0 (the move to treaty), a missing ledger exited `1`, ledger errors exited `2`, and a failure envelope had `"error": true`.

## 2. Adjusting an Account Balance (Pad + Balance)

Use `account pad-balance` when the user reports the current balance of an account and you need to record that fact without knowing the individual transactions that caused the change (e.g. "my Wise EUR balance is now 1777 EUR").

Beancount writes two directives: a `pad` entry (dated one day before the assertion by default) that auto-generates a catch-all transaction, and a `balance` entry that asserts the resulting amount.

### CLI flags

```
uv run bean account pad-balance \
  --account  <account>      # e.g. Assets:BE:Wise:EUR
  --amount   <number>       # e.g. 1777
  --currency <code>         # e.g. EUR
  [--pad-account <account>] # default: Expenses:Other
  [--date    YYYY-MM-DD]    # balance assertion date, default: today
  [--pad-date YYYY-MM-DD]   # pad directive date, default: balance-date minus 1 day
  [--file    FILE]          # ledger file (or set BEANCOUNT_FILE)
```

**`--account` must already exist** (have an `Open` directive). `--pad-account` defaults to `Expenses:Other` and does not need to pre-exist in the CLI — beancount will validate it when the ledger is next loaded.

### Example — user says "I spent some and have now Wise EUR 1777"

```bash
uv run bean account pad-balance \
  --account Assets:BE:Wise:EUR \
  --amount 1777 --currency EUR
```

Produces in the ledger:
```
2026-06-01 pad Assets:BE:Wise:EUR Expenses:Other

2026-06-02 balance Assets:BE:Wise:EUR  1777 EUR
```

### Via `bean exec` (batch / agent pipelines)

```bash
echo '{"_cmd": "account.pad-balance", "account": "Assets:BE:Wise:EUR", "amount": "1777", "currency": "EUR", "pad_account": "Expenses:Other", "date": "2026-06-02"}' \
  | uv run bean exec
```

### When to use which pad account

| Situation | Recommended `--pad-account` |
|---|---|
| Unknown spending (fees, small purchases) | `Expenses:Other` |
| Opening / correcting an asset balance | `Equity:Opening-Balances` |
| Transfer from another tracked account | Use `transaction add` instead |
