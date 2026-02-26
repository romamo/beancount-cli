# beancount-cli

A robust command-line interface and Python library for programmatically managing [Beancount](https://beancount.github.io/) ledgers. Designed for AI agents and automation workflows.

## Features

-   **Validation**: Wrap `bean-check` to validate ledgers programmatically.
-   **Visualization**: View the file inclusion tree (`tree` command).
-   **Transactions**:
    -   List transactions with regex filtering (account, payee, tags).
    -   Add transactions via CLI arguments or JSON (stdin supported).
    -   Draft mode support (flag `!`).
-   **Entities**:
    -   Manage Accounts (list, create).
    -   Manage Commodities (create).
    -   Manage Prices (fetch, update).
-   **Formatting**: Auto-format ledgers (`bean-format` wrapper).
-   **Reporting**: Generate simple balance and holding reports.
-   **Configuration**: Custom Beancount directives for routing new entries to specific files.

## Installation

Install using `uv` or `pip`:

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

The main command is `bean-cli`.

### Check Ledger

Validate your ledger file:

```bash
bean-cli check main.beancount
```

### Format Ledger

Format your ledger file in-place (uses `bean-format`):

```bash
bean-cli format main.beancount
```

### View Inclusion Tree

Visualize the tree of included files:

```bash
bean-cli tree main.beancount
```

### Reports

Generate specialized accounting reports with multi-currency support:

```bash
# Balance Sheet (Assets, Liabilities, Equity)
bean-cli report balance-sheet main.beancount

# Trial Balance (All accounts including Income/Expenses)
bean-cli report trial-balance main.beancount

# Holdings (Net worth per Asset account)
bean-cli report holdings main.beancount

# Audit a specific currency (Source of Exposure)
bean-cli report audit USD main.beancount
```

> [!TIP]
> Convenience aliases are supported: `bs` (balance-sheet) and `trial` (trial-balance).

#### Unified Currency Reporting

Use the `--convert` and `--valuation` flags for a consolidated view:

```bash
# View Trial Balance in USD using historical cost
bean-cli report trial main.beancount --convert USD --valuation cost

# View Balance Sheet in EUR using current market prices
bean-cli report bs main.beancount --convert EUR --valuation market
```

| Valuation | Description | Use Case |
| :--- | :--- | :--- |
| `market` (default) | Uses latest prices from the ledger. | Current **Net Worth** tracking. |
| `cost` | Uses historical price basis (`{}`). | **Accounting Verification** (proving balance). |

**List Transactions:**
```bash
bean-cli transaction list main.beancount --account "Assets:US:.*" --payee "Amazon"
```

**Add Transaction:**
```bash
# JSON via argument
bean-cli transaction add main.beancount --json '{"date": "2023-10-27", ...}'

# JSON via stdin (Recommended for complex data)
cat tx.json | bean-cli transaction add main.beancount --json -

# Create as Draft (!)
bean-cli transaction add main.beancount --json ... --draft
```

### Manage Accounts & Commodities

```bash
# List Accounts
bean-cli account list main.beancount

# Create Account
bean-cli account create main.beancount --name "Assets:NewBank" --currency "USD"

# Create Commodity
bean-cli commodity create "BTC" main.beancount --name "Bitcoin"

# Fetch Prices
bean-cli price main.beancount

# Update Prices (Append)
bean-cli price main.beancount --update
```

## AI Agent Integration

`beancount-cli` is specifically optimized for AI agents.

### Transaction Schema
Agents can dynamically retrieve the JSON schema for transactions to ensure valid data generation:

```bash
bean-cli transaction schema
```

### Complex Transaction Example
Agents should aim to generate JSON in this format for a standard purchase with multiple postings:

```json
{
  "date": "2023-10-27",
  "payee": "Amazon",
  "narration": "Office supplies",
  "postings": [
    {
      "account": "Expenses:Office:Supplies",
      "units": { "number": 45.99, "currency": "USD" }
    },
    {
      "account": "Liabilities:US:Chase:Slate",
      "units": { "number": -45.99, "currency": "USD" }
    }
  ]
}
```

### Scripting with `uv run`
For reliable cross-platform execution in agent workflows:
```bash
uv run bean-cli transaction add --json - < tx.json
```

## Configuration

### Ledger Discovery
`bean-cli` uses a 4-tier discovery logic to find your ledger file automatically:
1.  **Explicit Argument**: Passing the filename directly (e.g. `bean-cli check my.beancount`).
2.  **`BEANCOUNT_FILE`**: Direct path to a ledger file.
3.  **`BEANCOUNT_PATH`**: Looks for `main.beancount` inside this directory.
4.  **Local Directory**: Fallback to `./main.beancount`.

### Custom Directives
You can configure where new entries are written using custom directives in your Beancount file.

**Note:** `custom` directives require a date (e.g. `2023-01-01`).

```beancount
2023-01-01 custom "cli-config" "new_transaction_file" "inbox.beancount"
2023-01-01 custom "cli-config" "new_account_file" "accounts.beancount"
2023-01-01 custom "cli-config" "new_commodity_file" "commodities.beancount"
```

**Context-Aware Insertion:**
You can use placeholders to route transactions to dynamic paths:

```beancount
2023-01-01 custom "cli-config" "new_transaction_file" "{year}/{month}/txs.beancount"
```
Supported placeholders: `{year}`, `{month}`, `{day}`, `{payee}`, `{slug}`.

**Directory Mode (One file per transaction):**
If `new_transaction_file` points to a **directory**, `bean-cli` will create a new file for each transaction inside that directory, named with an ISO timestamp.

```beancount
2023-01-01 custom "cli-config" "new_transaction_file" "inbox/"
```

## Development

Run tests:

```bash
uv run pytest
```
