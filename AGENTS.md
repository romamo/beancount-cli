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

### Advanced JSON Data Pipelines
- **Data Insertion**: Write commands (like `transaction add`, `account create`, `commodity create`) accept rigorous JSON payloads dynamically through STDIN (`--input -`).
- **Schema Discovery**: If you need to know the required JSON structure to insert a transaction via STDIN, DO NOT GUESS. Run:
   ```bash
   uv run bean transaction schema
   ``` 
   This will output the exact Pydantic boundary schema expected by the application.
- **Native BQL**: `transaction list` supports Beancount Query Language (BQL) directly via the `--where` flag (e.g., `uv run bean transaction list --where "account ~ 'Expenses'"`).
- **Unix Composability**: Use the global `--format` flag *before* the command to pipe outputs.
   - *Example Pipeline:* `uv run bean --format json account list | uv run bean account create --input -`
- **Batch Processing**: Never loop shell executions to insert items one-by-one! Construct a massive JSON array and pipe the entire array to `transaction add --input -` for instantaneous batch processing.

## 2. Adjusting an Account Balance (Pad + Balance)

Use `account pad-balance` when the user reports the current balance of an account and you need to record that fact without knowing the individual transactions that caused the change (e.g. "my Wise EUR balance is now 1777 EUR").

Beancount writes two directives: a `pad` entry (dated one day before the assertion by default) that auto-generates a catch-all transaction, and a `balance` entry that asserts the resulting amount.

### CLI flags

```
uv run bean account pad-balance \
  --account  <account>      # e.g. Assets:BE:Wise:EUR
  --amount   <number>       # e.g. 1777
  --currency <code>         # e.g. EUR
  --pad-account <account>   # e.g. Expenses:Other or Equity:Opening-Balances
  [--date    YYYY-MM-DD]    # balance assertion date, default: today
  [--pad-date YYYY-MM-DD]   # pad directive date, default: balance-date minus 1 day
  [--file    FILE]          # ledger file (or set BEANCOUNT_FILE)
```

**Both `--account` and `--pad-account` must already exist** (have an `Open` directive). Create them first with `account create` if needed.

### Example — user says "I spent some and have now Wise EUR 1777"

```bash
uv run bean account pad-balance \
  --account Assets:BE:Wise:EUR \
  --amount 1777 --currency EUR \
  --pad-account Expenses:Other
```

Produces in the ledger:
```
2026-06-01 pad Assets:BE:Wise:EUR Expenses:Other

2026-06-02 balance Assets:BE:Wise:EUR  1777 EUR
```

### JSON / pipeline form

```bash
echo '{
  "account": "Assets:BE:Wise:EUR",
  "amount": {"number": 1777, "currency": "EUR"},
  "pad_account": "Expenses:Other",
  "balance_date": "2026-06-02"
}' | uv run bean account pad-balance --input -
```

### When to use which pad account

| Situation | Recommended `--pad-account` |
|---|---|
| Unknown spending (fees, small purchases) | `Expenses:Other` |
| Opening / correcting an asset balance | `Equity:Opening-Balances` |
| Transfer from another tracked account | Use `transaction add` instead |
