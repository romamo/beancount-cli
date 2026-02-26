# Implementation Plan - Code Review findings and remediation for beancount-cli

## Goal
Improve code quality, type safety, and test coverage of the `beancount-cli` project, ensuring consistency in Value Object usage and addressing remaining static analysis findings.

## User Review Required

### Global Rules Check
- **Value Objects**: `AccountName` and `CurrencyCode` are well-implemented in `models.py`.
- **Namespace Pattern**: Used via `VO.Input`.
- **Fail Fast**: Mostly adhered to. Some warning prints in `services.py` for minor configuration issues are acceptable but could be more robust.
- **Mypy Compatibility**: Verified clean.

### Critical Issues
- None identified. The codebase is in a strong state.

### Architecture
- The separation between `models`, `services`, `adapters`, and `cli` is clean.
- `adapters` correctly uses `cast` where Beancount's lack of type stubs causes issues.

### Ambiguities
- Should CLI commands use `VO.Input` directly? (Proposed: Yes, for consistency and automatic validation if we were using a framework that supports it, though Typer handles them as strings).

## Static Analysis & Coverage

### Ruff/Mypy
- **Ruff**: 3 unused imports found.
- **Mypy**: Success (no issues).

### Test Coverage
- **Current**: 86% TOTAL.
- **Targets for improvement**:
    - `models.py`: 96% -> 100% (Missing `TypeError` coverage).
    - `adapters.py`: 91% -> 100% (Missing `Cost` mapping coverage).
    - `services.py`: 84% -> 90+% (Missing error paths and config edge cases).

## Proposed Changes

### 1. Fix Unused Imports
- Remove unused `AccountName` from `src/beancount_cli/services.py`.
- Remove unused `AccountName` and `CurrencyCode` from `tests/test_models.py`.

### 2. Enhancing CLI Type Hints (Refactoring)
- Update `src/beancount_cli/cli.py` to use `AccountName.Input` and `CurrencyCode.Input` in command arguments where appropriate for better documentation and consistency, even if Typer treats them as strings.

### 3. Coverage Improvements
- **`tests/test_models.py`**: Add tests passing non-string values to validators to cover the `TypeError` branches.
- **`tests/test_advanced.py`**: 
    - Add tests for `Cost` mapping in `adapters.py` (specifically with dates and labels).
    - Add tests for `TransactionService.list_transactions` filtering logic (account, payee, tag, currency).
    - Add tests for `MapService` with absolute paths and non-matching globs.
- **`tests/test_services.py`**: 
    - Add tests for `new_transaction_file` with placeholders and directory mode.
    - Add tests for `ReportService` valuation errors (forcing conversion failures).

## Verification Plan
1. Run `uv run ruff check .` to verify unused imports are gone.
2. Run `uv run pytest --cov=src` to verify coverage increases.
3. Manually verify CLI still works with the updated type hints.
