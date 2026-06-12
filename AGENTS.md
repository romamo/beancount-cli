# AGENTS.md - Beancount CLI Guide for AI End Agents

This document provides instructions for **AI Agents** operating the Beancount CLI to manage or query a user's accounting data. 

*(If you are an AI Coding Agent tasked with modifying the python source code of this repository, please refer to `CODING_AGENTS.md` instead).*

---

## 1. Operating Rules & Workflows

If you are executing shell commands to help a human analyze or modify their `main.beancount` ledger, adhere to the following operational rules:

### Core Configuration & Bootstrapping
- **Ledger Path**: The CLI requires a target `.beancount` file. You can either pass it directly via `--file /path/to/main.beancount` or set the environment variable: `export BEANCOUNT_FILE=/path/to/main.beancount`.
- **Self Discovery**: If you are unsure about the available arguments for a command, ALWAYS run `uv run bean <command> --help` to read the descriptive schemas and examples embedded directly in the source code.

### Available Capabilities (High-Level)
- **`account list/create/pad-balance`**: Create and list chart of accounts, or adjust a balance using a Pad directive.
- **`transaction list/add`**: Query and batch insert accounting transactions.
- **`commodity list/create/check`**: Manage currency rules and commodities. Use `check` to find used currencies missing a declaration.
- **`price check/fetch`**: Manage price data and discovery.
   - `check`: Identify periods of missing price data for held assets. Supports `--rate (daily, weekday, weekly, monthly)`.
   - `fetch`: Wrapper for `bean-price` to fetch latest quotes. Supports `--update`, `--dry-run`, `--verbose`, `--inactive`, and `--update-fill-gaps`.
- **`report`**: Generate detailed mathematical rollups (`balance-sheet`, `trial-balance`, `holdings`, `audit`).
- **`format/tree`**: Maintain correct text indentation and view include trees.
- **Single Item Retrieval**: Use `--format json` when you require nested, hierarchical data structures.
- **Human Display**: The default format is `table`. Only use this if you are dumping the raw execution output directly to the user's terminal interface. 

### Advanced Data Pipelines
- **Schema Discovery**: If you need to know the exact parameters for a command, run:
   ```bash
   uv run bean transaction add --schema
   uv run bean account create --schema
   ```
   This outputs the JSON schema for every argument.
- **Native BQL**: `transaction list` supports Beancount Query Language (BQL) directly via the `--where` flag (e.g., `uv run bean transaction list --where "account ~ 'Expenses'"`).
- **Batch Processing**: Never loop shell executions to insert items one-by-one! Use `bean exec` to dispatch a JSONL stream — one JSON object per line — that can mix any command type in a single pass:
   ```bash
   # Mixed-command JSONL stream written to the ledger
   cat commands.jsonl | uv run bean exec

   # Same stream, preview without writing
   cat commands.jsonl | uv run bean exec --dry-run
   ```
   Each line must have a `_cmd` field (e.g. `transaction.add`, `account.create`, `commodity.create`). Use `_opts` for per-line flag overrides (e.g. `{"_opts": {"draft": true}}`). Pass `--ignore-errors` to continue on failures.

   Each processed line emits a structured JSON result to stdout:
   ```json
   {"ok": true,  "exit_code": 0, "line": 1, "cmd": "account.create", "result": {...}}
   {"ok": false, "exit_code": 5, "line": 2, "cmd": "transaction.add", "error": "..."}
   ```

   **`transaction.add` example payload:**
   ```json
   {"_cmd": "transaction.add", "date": "2024-01-15", "narration": "Groceries", "payee": "Store", "postings": [{"account": "Expenses:Food", "units": {"number": 50, "currency": "USD"}}, {"account": "Assets:Cash", "units": {"number": -50, "currency": "USD"}}]}
   ```

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
echo '{"_cmd": "account.pad-balance", "account": "Assets:BE:Wise:EUR", "amount": "1777", "currency": "EUR", "pad_account": "Expenses:Other", "balance_date": "2026-06-02"}' \
  | uv run bean exec
```

### When to use which pad account

| Situation | Recommended `--pad-account` |
|---|---|
| Unknown spending (fees, small purchases) | `Expenses:Other` |
| Opening / correcting an asset balance | `Equity:Opening-Balances` |
| Transfer from another tracked account | Use `transaction add` instead |
