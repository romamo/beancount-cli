# CODING_AGENTS.md - Development Rules for AI Coding Agents

If you are an AI agent analyzing, refactoring, or editing the Beancount CLI Python source code, you must strictly adhere to these engineering constraints:

### 1. Environment & Execution
- **Command Runner**: Always use `uv run` instead of `python` or `poetry` to execute commands.
- **Python Version**: Python 3.14 is required (`requires-python = ">=3.14"`); use 3.14 language features freely.
- **Temporary Files**: Always use a `tmp` folder in the current working directory for all temporary files.

### 2. Code Quality & Exception Handling
- **Fail Fast**: Strictly "fail fast". Never use `except Exception` or bare `except`. Do not swallow errors. Raise descriptive and strongly typed errors immediately upon encountering an invalid state.
- **Implementation**: Never add placeholders or `raise NotImplementedError()`. Always write full, production-ready code.
- **Validation**: Validation must be strict and fail immediately if input is malformed.

### 3. Type System & Domain Modeling
- **Avoid Primitive Obsession**: Use strict Value Objects (VO) instantiated via Pydantic instead of primitives (e.g., use `AccountName` and `CurrencyCode` domain types instead of just a primitive `str`).
- **Avoid Wide Typing**:
    - **Internal Logic**: Do not use wide unions (e.g., `date | str`) in internal logic; keep arguments strictly typed to the base VO.
    - **Boundaries**: Use unions only at the "System Boundaries" (e.g., CLI arguments, Pydantic initializers, JSON endpoint schemas).
- **DX Priority (Strict-yet-Flexible)**:
    - **Primitive-to-VO Coercion**: Models and Interfaces should accept primitives in type hints (`VO | str`) for better developer experience but normalize internally.
    - **Mypy Compatibility**: Use `TYPE_CHECKING` unions. To avoid "hiding" the base entity, prefer the **Namespace Pattern** (`VO.Input`) over generic names like `VOInput`.

### 4. Commands and Output
- The CLI is built on [treaty](https://github.com/romamo/treaty). Commands register on `app` from `beancount_cli.app`, take a frozen args dataclass extending `LedgerArgs`, and declare `danger_level`, `exit_codes`, and `examples`.
- Handlers return data (a dataclass or a pydantic model) and never print. treaty writes the JSON envelope; a `renderers={Format.PLAIN: ...}` function turns `data` into the text people see, using `render_rows()` or `formatting.Table`.
- Mutating commands return an `effect` (`created`, `updated`, `noop`, or `would_*` under `--dry-run`). Failures raise `Exit.<CODE>(...)` with a code listed in the command's `exit_codes`; app codes are declared in `app.py`.
- Run `uv run treaty audit beancount_cli.cli:app` after changing a command.

### 5. Testing & Quality
Always ensure changes are covered by running the complete quality suite before finalizing your step. There are no exceptions to failing checks:
```bash
uv run pytest
uv run ruff check .
uv run mypy src
```
