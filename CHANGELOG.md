# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Built on treaty instead of agentyper** (treaty 1.0.0rc30 or newer). Every command now answers with treaty's envelope (`ok`, `data`, `error`, `warnings`, `meta`), and `bean manifest` describes every command, flag, output schema, and exit code. `exec`, `--schema`, `--fields`, `--dry-run`, and `--idempotency-key` come from treaty.
- **Flags go after the command**: `bean account list --format json`, not `bean --format json account list`. `--format` takes `plain` (the default at a terminal), `json`, `jsonl`, `ndjson`, `csv`, and `tsv`; `table`, `-o`/`--output`, and `--json` are gone.
- **Exit codes**: a missing ledger file or account exits `5` (`NOT_FOUND`, was `1`); an existing account or commodity exits `6` (`ALREADY_EXISTS`); ledger errors from `check` exit `80` (`LEDGER_INVALID`, was `2`). New codes `81` to `86` name invalid transactions, BQL queries, commodity input, formatting, currency conversion, and a missing audit currency. AGENTS.md lists them all.
- **Errors are in the envelope**: a failure is `{"ok": false, "error": {"code", "message", ...}}` on stdout, and `check`'s ledger errors are in `error.context.errors` and `data.errors`.
- `transaction add --postings` takes one posting as a JSON object and is repeated for each posting, and each posting is validated before anything runs, so a bad account name exits `2` naming `postings[N].account`. `--tags` and `--links` are repeated too, one value each, instead of a JSON array. `exec` lines and `--raw-payload` still carry `postings` as an array. `--print` is gone; use `--dry-run`.
- `account create --currency` is repeated for each currency (was comma-separated), and `--date` sets the open date in `exec` lines as `date` (was `open_date`). `account pad-balance` takes its assertion date as `date` in `exec` lines (was `balance_date`).
- List commands (`transaction list`, `account list`, `commodity list`, `commodity check`, `price check`, `price check-anomalies`) return 20 items per page; `--limit 0` returns all, and `--cursor` the next page.
- Reports have typed output: `balance-sheet` and `trial-balance` return `accounts` (with `units` and `cost` per currency) and `net_positions`; `holdings` returns `accounts`, `totals`, and `currencies`; `audit` returns `postings` with `limited` and `transactions`. The `Units USD`-style keys are gone.
- `tree` returns the included files as a flat, depth-first list (`path`, `parent`, `depth`) instead of nested objects.
- `price fetch` returns the same shape on every path (`effect`, `file`, `written`, `redundant`, `jobs`, `prices`, `no_data`, `errors`), its messages are envelope warnings (`PRICES_NO_DATA`, `PRICES_REDUNDANT`, `PRICE_META_MISSING`), and a source error exits `3` with the fetched prices in `data`. Its output is marked as external content. `--format plain` prints only the price directives, so it can be appended to a price file; its status lines go to stderr under `--verbose` (#17).
- `commodity import` reads `--input-file` or stdin through treaty, and `commodity export` is a mutating command with `--dry-run` that reports `created`, `updated`, or `noop`.
- `commodity import` without `--dry-run` on a ledger with no `custom "ledger" "commodities_file"` writes nothing and reports `noop` with the directives in `entry` (was `would_create`, or `would_update` when it would overwrite) (#24)
- `format` reads `bean-format`'s output directly instead of through a temporary file; its unused `--recursive` flag is gone.
- Shell completion comes from `bean completion bash|zsh` instead of argcomplete.
- `BEAN_FILE` is read before `BEANCOUNT_FILE`, which keeps working.

### Fixed
- `transaction list --where` with a BQL column or function beanquery does not know exits `82` (`QUERY_INVALID`) instead of crashing, and an invalid `--payee` or `--account` regex exits `2` (`ARG_ERROR`) naming the flag.
- README documented `custom "cli-config"` directives, but the CLI reads `custom "ledger"`. It also listed report aliases, a `transaction schema` command, and a `BEANCOUNT_PATH` lookup that do not exist.
- `transaction add` (and `transaction.add` lines in `exec`) refuses postings whose weights don't balance with `TRANSACTION_INVALID` (exit `81`), with the same message `bean check` gives (e.g. `Transaction does not balance: (12.50 USD)`), instead of writing a transaction that breaks the ledger. Weights count cost and price, and the tolerance is inferred as beancount does. `--draft` still writes it with a warning (#16)

## [0.5.0] - 2026-09-30

### Changed
- **Requires Python 3.14 or newer** (was 3.10). pip and uv refuse to install on older interpreters; stay on beancount-cli 0.4.0 there. This prepares the move to treaty, which is 3.14-only.
- CI and the publish workflow run on Python 3.14; `.python-version` pins 3.14 for local development.
- Requires agentyper 0.1.22+ (was pinned to exactly 0.1.21), so beancount-cli installs alongside tools that need 0.1.22, such as ibkr-converter. Under `--format json`, errors raised through agentyper (e.g. `check` on a missing ledger) are now a failure envelope on stdout (`{"ok": false, "error": {...}}`) with a one-line `Error: ...` on stderr, instead of an `{"error": true, ...}` object on stderr.

## [0.4.0] - 2026-09-30

### Changed
- `check`, `format` and the mutating commands (`account create/balance/pad-balance`, `transaction add`, `commodity create/import`, `price fetch`) return a JSON envelope in `json`/`jsonl`/`csv` mode, including when piped. Mutating results carry `effect` (`created`, `updated`, `noop`, or `would_create`/`would_update` on a dry run), the written `file`, and the directive text as `entry`. Table/plain output keeps the human messages.
- `format` is declared mutating (it rewrites the ledger), gains `--dry-run`, and reports `noop` when the file is already formatted.
- `exec` now receives the results of mutating lines, including dry-run previews.

### Fixed
- `format` no longer leaks a temp file on failure, and a missing ledger or missing `bean-format` gives a structured error instead of a traceback.
- `commodity create` for an existing commodity gives a structured error (exit 2) instead of a traceback.
- `commodity import` parse errors are reported as a structured error on stderr instead of text on stdout.

## [0.3.1] - 2026-09-30

### Fixed
- `--output json`, `-o json`, `--json`, the non-TTY default, and `exec` now return the same structured data as `--format json` (model fields such as `open_date`) instead of table rows (`Open Date`). Only the hidden `--format` flag used to count.
- `report *`, `commodity check`, `price check` and `tree` print a JSON envelope when stdout is not a terminal, as `--help` documents; pass `-o table` for the table.
- `tree` JSON output includes the root ledger file.

## [0.3.0] - 2026-09-29

### Changed
- Upgraded `agentyper` to `0.1.21`.
- Exit codes follow the CLI Agent Spec: validation errors (e.g. `check` finding ledger errors) now exit `2` instead of `3`, and a partial `price fetch` failure exits `3` instead of `2`.
- `--format json` keeps list results as arrays: a query matching one item returns `"data": [{...}]` instead of a bare object.

## [0.2.17] - 2026-09-28

### Changed
- CLI program name is now `bean` (shown in `--help` and `--version`).

### Fixed
- `price fetch --fill-gaps` now backfills interior gaps instead of behaving like `--update`; requires `beanprice2>=2.1.2`.
- `price fetch` keeps running when one price source raises: failed jobs are reported, fetched prices are still written, and the run exits with a partial-failure code.
- `price fetch` no longer crashes in the "Skipped N jobs" summary when a source returns no data.
- `commodity import --target` no longer crashes when the target is given as a path string.
- `price check-anomalies --help` no longer crashes on Python 3.14 (unescaped `%` in help text).

## [0.2.16] - 2026-06-12

### Changed
- Upgraded `agentyper` to `0.1.17`.

## [0.2.15] - 2026-06-12

### Changed
- Upgraded `agentyper` to `0.1.16`, which provides `bean exec` as a built-in JSONL batch command (replaces the custom implementation).
- Replaced `--input` / `-i` JSON-stdin flags with individual CLI flags on `transaction add`, `account create`, `account balance`, `account pad-balance`, and `commodity create`.
- `bean exec` now maps JSONL payload fields to individual command flags automatically via agentyper's built-in dispatch.

### Removed
- `--input` / `-i` flag removed from all mutating commands; use `bean exec` for batch pipelines.

## [0.2.14] - 2026-06-02

### Added
- `account pad-balance`: insert a `pad` + `balance` directive pair directly into the ledger.

### Changed
- `--stdin` flag renamed to `--input` across all commands that read from standard input.

## [0.2.13] - 2026-04-17

### Added
- `price check`: detect anomalous pricing situations in addition to missing price gaps.
- `transaction list --fields`: limit JSON output to a selected comma-separated subset of fields.

### Changed
- Upgraded `agentyper` to `0.1.12`.

### Fixed
- `report audit`: sort entries chronologically from oldest to newest.
- `price fetch`: remove the non-functional `--held` behavior.

## [0.2.12] - 2026-04-08

### Fixed
- `price fetch --update`: cap `date_last` to yesterday (today exclusive) to avoid fetching intraday prices while the market is still open.

## [0.2.11] - 2026-04-07

### Fixed
- `price fetch`: use `[tool.uv.sources]` git override for `beanprice` so the romamo fork is installed correctly; PyPI metadata keeps `beanprice>=2.1.0` for compatibility.

## [0.2.10] - 2026-04-07

### Changed
- `price fetch`: use `romamo/beanprice` fork via `[tool.uv.sources]` git override; PyPI metadata retains `beanprice>=2.1.0` for compatibility.
- `price fetch --update`: include today's date in the fetch window (`date_last` is exclusive, so now passes `today + 1`).

### Added
- `price fetch -vv`: log each redundant fetched price at DEBUG level so skipped prices are visible.

## [0.2.9] - 2026-04-05

### Fixed
- Smoke test: check stderr as well as stdout when probing `--help` output, fixing false negatives in isolated environments.

## [0.2.8] - 2026-04-04

### Added
- `commodity list`: List all declared commodities, with optional `--asset-class` filter.
- `commodity check`: Identify currencies used in transactions that are missing a `commodity` directive.
- `price check`: Identify periods of missing price data for held assets. Supports `--rate` (daily, weekday, weekly, monthly) and `--tolerance` (days before flagging a gap).
- `price fetch`: Fetch latest quotes via the `bean-price` library with `--update`, `--fill-gaps`, `--dry-run`, `--inactive`, and `--verbose` options.
- `account balance`: Add a `balance` assertion directive to the ledger via `--json`.
- `--target` flag on `transaction add`, `account create`, and `commodity create` to override the destination file, bypassing config-driven routing.
- Structured JSON error output for `check --format json` with typed `error_type` and `exit_code` fields.

### Changed
- `price` is now a subcommand group (`price check`, `price fetch`), replacing the former single `price` command.
- `check` now exits with code `2` on missing/unreadable files (system error) and code `1` on validation errors, instead of raising an uncaught exception.

## [0.2.6] - 2026-03-03

### Changed
- Refactored `cli.py` into multiple smaller sub-modules (`account`, `commodity`, `report`, `transaction`, `common`, `root`) for better maintainability.
- Migrated argument parsing from `argparse` to `agentyper` for better output formatting.

## [0.2.5] - 2026-03-02

### Added
- Comprehensive test coverage for previously untested edge cases in CLI, services, and models.
- Dedicated `tests/test_coverage_gap.py` to identify and fill testing gaps.

## [0.2.4] - 2026-03-02

### Changed
- Improved CLI subcommand descriptions and argument parsing.
- Refined configuration discovery and default handling.
- Enhanced Ledger and Report services with better error messages.

### Added
- Expanded unit tests for CLI, config, and models.
- Documentation updates for better ergonomics.

## [0.2.3] - 2026-03-01

### Fixed
- Fixed Ruff linting and formatting issues in CLI source code.
- Cleaned up unused imports in configuration module.
- Synchronized versioning across metadata files.

## [0.2.2] - 2026-03-01

### Fixed
- Fixed ledger discovery via environment variables `BEANCOUNT_FILE` and `BEANCOUNT_PATH`.
- Fixed CLI argument parsing to allow global flags (`--file`, `--format`) to be placed after subcommands.

### Added
- Improved `.env` file support for configuration.

## [0.2.1] - 2026-02-27

### Added
- Added `--version` flag to the CLI for easier version tracking.
- Implemented a comprehensive smoke test suite in `tests/smoke_test.py`.

### Changed
- Bumped minimum Python version to 3.10 to support PEP 604 union types (`|` syntax).
- Updated CI workflow to test against Python 3.10 through 3.15.
- Fixed import sorting in `cli.py` to comply with Ruff rules.
- Dropped support for Python 3.9.

## [0.2.0] - 2026-02-27

### Changed
- Renamed the CLI entry point from `beancount-cli` to `bean` for better ergonomics and branding.
- Enhanced CLI help descriptions and examples for better AI agent discoverability.
- Separated documentation for user-facing agents (`AGENTS.md`) and coding/development agents (`CODING_AGENTS.md`).
- Added strict type validation and Pydantic schema discovery.

## [0.1.0] - Initial Release


### Added
- Core Beancount CLI functionality.
- Commands for adding transactions, checking balances, and more.
- Built-in type hints and validation using Pydantic V2.
