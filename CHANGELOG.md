# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
