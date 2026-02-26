# Beancount Ecosystem Analysis

This document details the data models, interfaces, and data flow within the Beancount ecosystem (Beancount, Beangulp, Beanprice, Beangrow, Fava) to support the development of a CLI tool and agent skills.

## 1. Beancount (Core)

**Role**: The core double-entry bookkeeping system. It parses text files into Python objects (`entries`) and provides basic query capabilities.

### Core Data Models
Beancount data is primarily represented as a list of `Directive` objects.
*   **Transaction**: The central object.
    *   `date`: `datetime.date`
    *   `payee`: `str` or `None`
    *   `narration`: `str`
    *   `tags`: `set(str)`
    *   `links`: `set(str)`
    *   `postings`: `list[Posting]`
    *   `meta`: `dict` (metadata)
*   **Posting**: A single leg of a transaction.
    *   `account`: `str` (Account name)
    *   `units`: `Amount` (number, currency)
    *   `cost`: `Cost` or `CostSpec` (cost basis)
    *   `price`: `Amount` (market price at transaction)
    *   `meta`: `dict`
*   **Balance**: Assertion of an account's balance.
*   **Price**: Market price entry (`date`, `currency`, `amount`).

### Interfaces
*   **Loading**: `beancount.loader.load_file(filename)` returns `(entries, errors, options)`.
*   **Printing**: `beancount.parser.printer.format_entry(entry)` converts a Python object back to Beancount syntax string.
*   **Querying**: `beancount.query` module allows executing SQL-like queries on `entries`.

### Adding/Editing Data
*   **Add**: The standard way is to append formatted text strings to the `.beancount` file.
*   **Edit**: Editing existing entries programmatically is complex because round-tripping (parse -> modify -> print) often loses formatting/comments.
*   **Safe Edit Strategy**:
    1.  Parse file.
    2.  Find target entry (e.g., via metadata ID).
    3.  Generate new text representation.
    4.  Replace the specific block in the file (requires line number tracking from parser).

## 2. Beangulp (Importing)

**Role**: Framework for extracting transactions from external files (PDFs, CSVs).

### Core Interfaces
*   **Importer Protocol** (`beangulp.Importer`):
    *   `identify(filepath) -> bool`: Returns `True` if the importer handles this file.
    *   `extract(filepath, existing_entries) -> entries`: Parses the file and returns a list of *new* Beancount directives.
    *   `account(filepath) -> str`: Returns the associated Beancount account.
    *   `filename(filepath) -> str`: Returns a standardized filename for archiving.

### Capabilities
*   **Extraction**: Does not modify files. It reads external data and produces in-memory Beancount entries.
*   **Deduplication**: `extract.py` provides logic to compare extracted entries against `existing_entries` to avoid duplicates (using a date window).

## 3. Beanprice (Prices)

**Role**: Fetching historical and current market prices.

### Core Interfaces
*   **Source Protocol** (`beanprice.Source`):
    *   `get_latest_price(ticker) -> SourcePrice`
    *   `get_historical_price(ticker, time) -> SourcePrice`
    *   `get_prices_series(ticker, start, end) -> list[SourcePrice]`
*   **SourcePrice**: NamedTuple `(price: Decimal, time: datetime, quote_currency: str)`.

### Capabilities
*   **Fetching**: Connects to APIs (Yahoo, AlphaVantage, etc.).
*   **Output**: Typically prints `Price` directives to stdout, which can be redirected to a file.

## 4. Beangrow (Portfolio Analysis)

**Role**: Calculating investment returns (IRR, Dietz) and analyzing portfolio performance.

### Core Data Models
*   **AccountData**: Aggregates all data for a specific investment account.
    *   `cash_flows`: List of `CashFlow`
    *   `transactions`: List of `Transaction`
    *   `balance`: `Inventory` (current holdings)
*   **CashFlow**: Simplified structure for return calculations.
    *   `date`, `amount`, `is_dividend`, `source` (e.g., "cash", "dividend", "buy").
*   **InvestmentConfig**: Protobuf-based configuration defining asset classes, accounts, and strategy.

### Capabilities
*   **Transformation**: Converts standard Beancount `Transaction` entries into `CashFlow`s based on "Signatures" (patterns of postings, e.g., "Asset + Cash = Buy").
*   **Reporting**: Outputs returns, PnL, and performance headers.

## 5. Fava (User Interface)

**Role**: Web-based visualization and editor.

### Core Interfaces
*   **FavaLedger**: The main entry point. Wraps `beancount.loader` and provides high-level accessors.
    *   `all_entries`: Raw list of directives.
    *   `entries_by_type`: Grouped by type (Transaction, Price, etc.).
    *   `get_filtered(...)`: Returns a `FilteredLedger` based on time/account/tags.
*   **Watcher**: Monitors files for changes to trigger reloads.

### Capabilities
*   **Read**: Extremely powerful filtering and aggregation (Trees, inventories).
*   **Edit**: Fava has basic editing capabilities (editing source file content directly in browser). It does not expose a high-level "update transaction" Python API for external tools; it relies on text editing.

## 6. Integration with Other Tools (Ghostfolio)

*   **Pydantic-Ghostfolio**: Maps data to Ghostfolio's import format.
    *   `GhostfolioExport`: Root object containing `activities` and `accounts`.
    *   `Activity`: Represents a trade (`BUY`, `SELL`, `DIVIDEND`).
    *   **Mapping**: A Beancount `Transaction` (buy stock) maps to a Ghostfolio `Activity` (type=BUY).

## Recommendations for CLI/Agent Tool

1.  **Reading Data**: Use `beancount.loader.load_file` to get the full state. Use `beangrow` libraries if you need investment-specific views (returns, cash flows).
2.  **Writing Data**:
    *   For **Append** (new transactions): Generate string using `printer.format_entry` and append to the main file.
    *   For **Edit**: Use the `meta` fields (line numbers) provided by the parser to locate the text block in the file. Read the file, replace the lines with the new formatted entry.
3.  **Importing**: Reuse `beangulp.Importer` classes if they exist. The CLI should act as a runner that calls `importer.extract()` and then formats/saves the result.
4.  **Prices**: Use `beanprice` as a library to fetch prices if needed, or simply run it as a subprocess.

## 7. Architectural Insights (from Design Doc)

*   **Immutability**: Core data structures (`Transaction`, `Posting`, `Amount`) are immutable `namedtuple`s. To "modify" them, create new instances using `._replace()`.
*   **Stream Processing**: Beancount is designed as a pipeline. Loops over the list of directives are the standard way to implement features (plugins, validation, reporting).
*   **Parser/Printer Round-trip**: The system is designed so that `print(parse(text))` ideally returns valid Beancount text, but whitespace/comments may be lost. This confirms that "editing" by parsing -> modifying object -> printing is risky for preserving user formatting.
*   **DisplayContext**: To render numbers correctly (e.g., 2 decimal places for USD, 0 for JPY), you must use the `DisplayContext` object collected during parsing. It tracks the precision used in the input file.
*   **No "Virtual" Postings**: Unlike Ledger, Beancount enforces strict double-entry balancing for *every* transaction.
*   **Two-Phase Loading**:
    1.  **Parsing**: Text -> Incomplete Directives.
    2.  **Loading/Interpolation**: Incomplete Directives + Inventory State -> Complete Directives (e.g., filling in missing cost basis).
    *   *Implication*: When analyzing data, ensure you are working with the *loaded* (complete) entries, not just raw parsed ones.

## 8. Strategy: Core Models vs. Pydantic

You are **not required** to use Pydantic models for Beancount development, but they are highly recommended for modern agent/CLI tools. Beancount's core uses `namedtuple`s, which are lightweight but lack runtime validation and JSON serialization (critical for LLMs/APIs).

### Decision Guide

| Feature | Beancount Core (`namedtuple`) | Pydantic Models |
| :--- | :--- | :--- |
| **Native Compatibility** | **High**. Required by `loader`, `printer`, plugins. | **Low**. Requires conversion to/from core models. |
| **Validation** | **Low**. Relies on loader pipeline checks. | **High**. Runtime type checking & constraints. |
| **Serialization** | **Low**. `printer` outputs text, not JSON. | **High**. Native `.model_dump_json()` support. |
| **Agent/LLM Integration** | **Difficult**. LLMs need JSON schemas (OpenAPI). | **Excellent**. Pydantic models generate schemas automatically. |

### Recommendation: Hybrid Approach

1.  **Internal/Agent Layer**: Define Pydantic models that mirror core structures (e.g., `TransactionModel`, `PostingModel`) to interface with the LLM or API. This gives you validation and schema generation.
2.  **IO/Storage Layer**: Write adapter functions to convert Pydantic models -> Core `namedtuple`s for saving/printing, and Core `namedtuple`s -> Pydantic models for reading/analysis.
3.  **Do NOT replace Core**: You cannot "replace" the core models if you want to use existing Beancount libraries (`beangulp`, `fava`, `beanprice`). You must interoperate with them.
