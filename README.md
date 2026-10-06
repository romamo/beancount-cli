# beancount-cli

A robust command-line interface and Python library for programmatically managing [Beancount](https://beancount.github.io/) ledgers. Designed for AI agents and automation workflows.

## Features

-   **Validation**: Wrap `bean-check` to validate ledgers programmatically.
-   **Visualization**: View the file inclusion tree (`tree` command).
-   **Transactions**:
    -   List transactions with regex filtering (account, payee, tags) or a BQL `--where` clause.
    -   Add transactions with typed postings; draft mode support (flag `!`).
-   **Entities**:
    -   Manage Accounts (list, create, balance assertion, pad to a balance).
    -   Manage Commodities (list, create, check undeclared, import, export).
    -   Manage Prices (check gaps and anomalies, fetch/update via bean-price).
-   **Formatting**: Auto-format ledgers (`bean-format` wrapper).
-   **Reporting**: Generate balance, holding, and audit reports with multi-currency conversion.
-   **Agent-ready**: Built on [treaty](https://github.com/romamo/treaty): every command answers with a JSON envelope when piped, declares its exit codes, and is listed in `bean manifest`.
-   **JSONL Stream Execution**: `bean exec` dispatches a mixed-command JSONL stream to the ledger; `--dry-run` previews the result without writing.
-   **Configuration**: Custom Beancount directives for routing new entries to specific files.

## Installation

Requires Python 3.14 or newer. Install using `uv` or `pip`:

```bash
uv pip install beancount-cli
# or
pip install beancount-cli
```

For development:

```bash
uv sync
```

## Usage

### Output Formats

At a terminal, commands print text tables (`plain`). When stdout is piped, or with `--format json`, they print a JSON envelope: `{"ok", "data", "error", "warnings", "meta"}`.

```bash
# Human-readable table
bean report balance-sheet

# Structural JSON (for jq or other scripts)
bean account list --format json

# CSV, or tab-separated values
bean transaction list --format csv
bean transaction list --format tsv

# Only some fields
bean transaction list --fields date,payee,narration
```

A command's own flags go after the command: `bean account list --file main.beancount`, not `bean --file main.beancount account list`. Global flags such as `--format` and `--fields` go before or after it; `--help` lists both kinds.

List commands (`transaction list`, `account list`, `commodity list`, `price check`) return 20 items at a time. `--limit 0` returns all of them, and `--cursor` with `meta.pagination.next_cursor` the next page.

### Check Ledger

Validate your ledger file:

```bash
bean check main.beancount
```

### Format Ledger

Format your ledger file in-place (uses `bean-format`):

```bash
bean format main.beancount
bean format main.beancount --dry-run   # report whether it would change
```

### View Inclusion Tree

Visualize the tree of included files:

```bash
bean tree main.beancount
```

### Reports

Generate specialized accounting reports with multi-currency support:

```bash
# Balance Sheet (Assets, Liabilities, Equity)
bean report balance-sheet -f main.beancount

# Trial Balance (All accounts including Income/Expenses)
bean report trial-balance -f main.beancount

# Holdings (Net worth per Asset account)
bean report holdings -f main.beancount

# Audit a specific currency (Source of Exposure)
bean report audit -f main.beancount --currency USD
```

#### Unified Currency Reporting

Use the `--convert` and `--valuation` flags for a consolidated view:

```bash
# View Trial Balance in USD using historical cost
bean report trial-balance --convert USD --valuation cost

# View Balance Sheet in EUR using current market prices
bean report balance-sheet --convert EUR --valuation market
```

| Valuation | Description | Use Case |
| :--- | :--- | :--- |
| `market` (default) | Uses latest prices from the ledger | Current **Net Worth** tracking |
| `cost` | Uses historical price basis (`{}`) | **Accounting Verification** (proving balance) |

### Transactions

**List Transactions:**
```bash
bean transaction list --account "Assets:US:.*" --payee "Amazon"
bean transaction list --where "account ~ 'Expenses'"
```

**Add Transaction:** each `--postings` takes one posting as a JSON object; repeat it for every posting.
```bash
bean transaction add --date 2023-10-27 --payee Amazon --narration "Office supplies" \
  --postings '{"account": "Expenses:Office:Supplies", "units": {"number": 45.99, "currency": "USD"}}' \
  --postings '{"account": "Liabilities:US:Chase:Slate", "units": {"number": -45.99, "currency": "USD"}}'

# Create as Draft (!), tagged
bean transaction add ... --draft --tags office

# Preview the entry without writing it
bean transaction add ... --dry-run
```

The whole transaction can also travel as one JSON object, with `postings` as an array:

```bash
bean transaction add --raw-payload "$(cat tx.json)"
```

### JSONL Stream Execution

Use `bean exec` to dispatch a mixed-command JSONL stream (one JSON object per line) to the ledger in a single pass.

Each line must contain a `_cmd` field naming a command by its dotted path (`transaction.add`, `account.create`, `commodity.create`, etc.); the other keys are its arguments, named as the flags are, with `_` for `-`. Each line answers with its own JSON envelope.

```bash
# Write a mixed stream to the ledger
cat commands.jsonl | bean exec

# Preview without writing
cat commands.jsonl | bean exec --dry-run
```

Example JSONL line:
```json
{"_cmd": "transaction.add", "draft": true, "date": "2024-01-01", "narration": "Buy coffee", "postings": [{"account": "Expenses:Food", "units": {"number": 5, "currency": "USD"}}, {"account": "Assets:Cash", "units": {"number": -5, "currency": "USD"}}]}
```

### Manage Accounts & Commodities

The creation commands (`transaction add`, `account create`, `commodity create`) take `--target` to override the destination file and `--dry-run` to preview the entry.

**Accounts:**
```bash
# List accounts
bean account list

# Create account; repeat --currency for more
bean account create --name "Assets:NewBank" --currency USD

# Add a balance assertion
bean account balance --account Assets:Bank --date 2024-01-01 --amount 1000 --currency USD

# Bring an account to a balance; the difference is booked to Expenses:Other
bean account pad-balance --account Assets:Bank --amount 1777 --currency EUR
```

**Commodities:**
```bash
# List all declared commodities
bean commodity list

# List by asset class
bean commodity list --asset-class stock

# Find currencies used in transactions but missing a commodity directive
bean commodity check

# Create a commodity
bean commodity create BTC --name "Bitcoin"

# Import directives from stdin or a file into the commodities_file
cat registry.beancount | bean commodity import
bean commodity import --input-file registry.beancount
```

**Prices:**
```bash
# Check for periods of missing price data
bean price check

# Check with weekly rate and 14-day tolerance
bean price check --rate weekly --tolerance 14

# List the fetch jobs without fetching
bean price fetch --dry-run

# Fetch and write new prices to the ledger
bean price fetch --update
```

`beancount-cli` is specifically optimized for AI agents, providing both operational guidance and machine-readable interfaces.

### Agent Documentation
We provide specialized documentation for different types of AI interactions:
- [**AGENTS.md**](./AGENTS.md): Guide for **AI End Agents** operating the CLI (exit codes, batch workflows, schemas).
- [**CODING_AGENTS.md**](./CODING_AGENTS.md): Mandatory rules for **AI Coding Agents** modifying the source code (Value Objects, Fail-Fast rules, type safety).

### Schemas
Agents can retrieve the arguments and output schema of any command, or of all of them at once:

```bash
bean transaction add --schema
bean manifest
```

## Configuration

### Ledger Discovery
`bean` finds your ledger file in this order:
1.  **Explicit Argument**: The positional file of `check`, `tree`, `format`, and `price fetch` (e.g. `bean check my.beancount`).
2.  **`--file` / `-f`**: Accepted by every command.
3.  **`BEAN_FILE`**, then **`BEANCOUNT_FILE`**: Path to a ledger file.
4.  **Local Directory**: Fallback to `./main.beancount`.

### Custom Directives
You can configure where new entries are written using custom directives in your Beancount file.

**Note:** `custom` directives require a date (e.g. `2023-01-01`).

```beancount
2023-01-01 custom "ledger" "new_transaction_file" "inbox.beancount"
2023-01-01 custom "ledger" "new_account_file" "accounts.beancount"
2023-01-01 custom "ledger" "new_commodity_file" "commodities.beancount"
2023-01-01 custom "ledger" "commodities_file" "commodities.beancount"
```

**Context-Aware Insertion:**
You can use placeholders to route transactions to dynamic paths:

```beancount
2023-01-01 custom "ledger" "new_transaction_file" "{year}/{month}/txs.beancount"
```
Supported placeholders: `{year}`, `{month}`, `{day}`, `{payee}`, `{slug}`. Any other placeholder, a positional `{}`, or an unmatched brace makes `transaction add` exit `80` (`LEDGER_INVALID`) without writing anything.

**Directory Mode (One file per transaction):**
If `new_transaction_file` points to a **directory**, `bean` will create a new file for each transaction inside that directory, named with an ISO timestamp.

```beancount
2023-01-01 custom "ledger" "new_transaction_file" "inbox/"
```

### Tab Completion

`bean completion` writes the completion script for your shell:

```bash
# Bash
source <(bean completion bash --format plain)

# Zsh
source <(bean completion zsh --format plain)
```

## Development

Run tests:

```bash
uv run pytest
```
