# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
