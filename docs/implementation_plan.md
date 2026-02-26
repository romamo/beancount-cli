# Implementation Plan: `beancount-cli`

## Goal
Create a CLI tool and Python library (`beancount-cli`) to manage Beancount ledgers programmatically. The system will use Pydantic models for robust data handling and provide agent-friendly interfaces for common accounting tasks.

## 1. Data Models & Adapters
We will mirror Beancount's core `namedtuple` structures with Pydantic models to enable validation, JSON serialization, and easy integration with LLMs.

### Models (`src/beancount_cli/models.py`)
*   **`AmountModel`**: `number: Decimal`, `currency: str`
*   **`PostingModel`**:
    *   `account: str`
    *   `units: AmountModel`
    *   `cost: Optional[CostModel]`
    *   `price: Optional[AmountModel]`
    *   `meta: Dict[str, Any]`
*   **`TransactionModel`**:
    *   `date: date`
    *   `flag: str` (default `*` or `!`)
    *   `payee: Optional[str]`
    *   `narration: str`
    *   `tags: Set[str]`
    *   `links: Set[str]`
    *   `postings: List[PostingModel]`
    *   `meta: Dict[str, Any]`
*   **`AccountModel`**: `name: str`, `open_date: date`, `meta: Dict`
*   **`CommodityModel`**: `currency: str`, `date: date`, `meta: Dict`

### Adapters (`src/beancount_cli/adapters.py`)
*   `to_core_transaction(model: TransactionModel) -> beancount.core.data.Transaction`
*   `from_core_transaction(entry: beancount.core.data.Transaction) -> TransactionModel`
*   (Similar adapters for Postings, Amounts)

## 2. Service Interfaces
Services will encapsulate business logic, validation, and file I/O.

### `ValidationService`
*   **`validate_transaction(tx: TransactionModel, ledger: FavaLedger) -> ValidationResult`**
    *   Checks if all accounts in `tx.postings` exist in `ledger.accounts`.
    *   Checks if all commodities exist in `ledger.commodities`.
    *   Returns list of errors (missing accounts/commodities).

### `TransactionService`
*   **`draft_transaction(tx: TransactionModel, ledger_file: Path) -> None`**
    *   Sets flag to `!` (pending).
    *   Validates using `ValidationService`.
    *   Appends to the configured ledger file (see "Design Decisions").
    *   Optionally runs internal `beancheck` validation.
*   **`add_transaction(tx: TransactionModel, ledger_file: Path) -> None`**
    *   Sets flag to `*` (cleared).
    *   Performs full validation.
    *   Appends to ledger.

### `AccountService`
*   **`list_accounts(ledger: FavaLedger) -> List[AccountModel]`**
*   **`create_account(account: AccountModel, ledger_file: Path) -> None`**
    *   Checks if account exists.
    *   Appends `Open` directive.

### `CommodityService`
*   **`create_commodity(commodity: CommodityModel, ledger_file: Path) -> None`**

## 3. Configuration & Directives
We will use custom Beancount custom directives to configure the CLI behavior within the ledger itself.

*   `custom "fava-option" "insert-entry" "{regex}"` (Reuse Fava's existing option if possible, or define our own)
*   **Proposal**: `custom "cli-config" "new_transaction_file" "path/to/inbox.beancount"`
    *   Allows specifying a dedicated inbox file for new CLI-added transactions.

## 4. CLI Design
The CLI will use `click` or `typer`.

### structure
```bash
bean-cli transaction add --date 2024-03-19 --payee "Acme Corp" --narration "Salary" ...
bean-cli transaction draft ...
bean-cli account list
bean-cli account create --name "Assets:NewBank"
```

### Complex Input
For complex multi-leg transactions, the CLI will support:
1.  **JSON Input (Argument)**: `bean-cli transaction add --json '{"date": "...", "postings": [...]}'`
2.  **JSON Input (Stdin)**: `cat tx.json | bean-cli transaction add --json -` (Prevents shell escaping issues)
3.  **Interactive Mode**: Prompts for postings one by one.
4.  **File Input**: `bean-cli transaction add --file tx.json` (or `.beancount` snippet)

## 5. Additional Commands (Research)

### `bean-cli check`
*   **Goal**: Wrap `bean-check` functionality to validate the ledger.
*   **Implementation**: 
    *   Load the file using `beancount.loader.load_file()`.
    *   Capture `errors` list.
    *   Print formatted errors to stderr (filename:line: message).

### `bean-cli map` (Tree Traversal)
*   **Goal**: Visualize the tree of included Beancount files.
*   **Implementation**:
    *   Custom parser logic to find `include` directives.
    *   Recursively traverse files starting from `main.beancount`.
    *   Print a tree structure (like `tree` command) showing file paths.
    *   **Note**: Beancount loader flattens includes, so we need a custom recursive file reader or inspect the `options['include']` if available (it might not be preserved in structure). *Better approach*: Parse the file line-by-line looking for `include "..."` strings to build the tree without full Beancount loading (faster, preserves structure).

### `bean-cli report`
*   **Goal**: Simple text reports (balance sheet, holdings).
*   **Implementation**:
    *   **Balance Sheet**: Use `beancount.reports.balance.balance_sheet()`.
    *   **Holdings**: Iterate over `entries`, compute inventory using `beancount.core.inventory`, print content.
    *   **Trial Balance**: Sum all accounts.
    *   *Design*: `bean-cli report balances`, `bean-cli report holdings`.

### `bean-cli transaction list`
*   **Goal**: List transactions filtered by account or payee.
*   **Implementation**:
    *   Use `beancount.query.query_env` or directly iterate over `entries` (faster for simple filters).
    *   **Filters**: `--account <regex>`, `--payee <regex>`, `--tag <tag>`.
    *   **Output**: Print matching transactions using `beancount.parser.printer`.
    *   **Advanced**: Allow raw BQL queries via `--where "..."`.

## 6. Verification Plan
*   **Automated Tests**:
    *   Unit tests for Model <-> Core adapters.
    *   Unit tests for `ValidationService` (mocking the Ledger).
    *   Integration tests: Create a temporary Beancount file, run `add_transaction`, verify file content matches expected string.
*   **Manual Verification**:
    *   Run `bean-cli transaction add ...` and check the actual `.beancount` file.
    *   Open Fava to ensure the new transaction appears and balances.
