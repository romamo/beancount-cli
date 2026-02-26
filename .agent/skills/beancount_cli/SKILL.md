---
name: Beancount CLI
description: Manage Beancount ledgers, add transactions, checking balances, and validating files.
---

# Beancount CLI

This skill allows you to interact with Beancount ledgers using the `bean-cli` command-line tool. You can add transactions, list accounts, check for errors, and generate simple reports.

## Prerequisites

The `beancount-cli` package must be installed in the environment or available via `uv run`.

## Usage

All commands are run using `bean-cli`.

### Check Ledger Validity

Validate the ledger file for errors.

```bash
bean-cli check
```

### Map Include Structure

Visualize the file inclusion tree.

```bash
bean-cli map
```

### List Transactions

List transactions with optional filters.

```bash
# List all
bean-cli transaction list

# Filter by account regex
bean-cli transaction list --account "Assets:US:.*"

# Filter by payee
bean-cli transaction list --payee "Amazon"
```

### Add Transaction

Add a new transaction to the ledger. You can provide JSON input.

**JSON Format:**
```json
{
  "date": "2023-10-27",
  "payee": "Coffee Shop",
  "narration": "Coffee",
  "postings": [
    { "account": "Expenses:Food:Coffee", "units": { "number": 5.50, "currency": "USD" } },
    { "account": "Assets:Cash", "units": { "number": -5.50, "currency": "USD" } }
  ]
}
```

**Command:**
```bash
# Via argument
bean-cli transaction add --json '{"date": "...", ...}'

# Via stdin (Recommended for complex JSON)
echo '{"date": "...", ...}' | bean-cli transaction add --json -
```

Use `--draft` to mark it as pending (`!`).

### Manage Accounts

```bash
# List accounts
bean-cli account list

# Create account
bean-cli account create --name "Assets:NewBank" --currency "USD"
```

### Reports

```bash
bean-cli report balances
bean-cli report holdings
```

## Configuration

The CLI looks for a `main.beancount` file in the current directory or the file specified by `BEANCOUNT_FILE` environment variable.
