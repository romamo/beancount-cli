"""The treaty app every command registers on, with the types and exit codes they share."""

import datetime
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from treaty import App, Ctx, Exit, Flag, Format, ParseError, table

from beancount_cli import __version__
from beancount_cli.formatting import Table
from beancount_cli.models import (
    AccountName,
    CurrencyCode,
    RegexPattern,
    validate_account_name,
    validate_currency_code,
    validate_regex,
)

app = App("bean", version=__version__, description="Beancount CLI tool for managing ledgers.")
app.format(Format.CSV, render=table(","))


def _model_schema(cls: type[BaseModel]) -> dict[str, Any]:
    return cls.model_json_schema(mode="serialization")


def _model_dump(obj: BaseModel) -> object:
    return obj.model_dump(mode="json", by_alias=True)


app.output_adapter(BaseModel, schema=_model_schema, dump=_model_dump)
app.scalar(
    datetime.date,
    parse=datetime.date.fromisoformat,
    pattern=r"^\d{4}-\d{2}-\d{2}$",
    serialize=datetime.date.isoformat,
)
app.scalar(AccountName, parse=lambda value: AccountName(validate_account_name(value)))
app.scalar(CurrencyCode, parse=lambda value: CurrencyCode(validate_currency_code(value)))
app.scalar(RegexPattern, parse=lambda value: RegexPattern(validate_regex(value)))

app.exit_code(
    "LEDGER_INVALID",
    80,
    description="The ledger has errors (error.context.errors lists them) or a malformed option"
    " (error.context.option names it)",
    retryable=False,
    side_effects="none",
    suggestion="fix the listed directives and run bean check again",
)
app.exit_code(
    "TRANSACTION_INVALID",
    81,
    description="The transaction names an account that is not open or an undeclared currency, or its postings do not balance",
    retryable=False,
    side_effects="none",
)
app.exit_code(
    "QUERY_INVALID",
    82,
    description="The BQL --where clause could not be run",
    retryable=False,
    side_effects="none",
)
app.exit_code(
    "CURRENCY_REQUIRED",
    83,
    description="No --currency was given and the ledger declares no operating_currency",
    retryable=False,
    side_effects="none",
    suggestion="pass --currency CODE",
)
app.exit_code(
    "DIRECTIVES_INVALID",
    84,
    description="The input is not valid beancount directives",
    retryable=False,
    side_effects="none",
)
app.exit_code(
    "FORMAT_FAILED",
    85,
    description="bean-format could not format the ledger",
    retryable=False,
    side_effects="none",
)
app.exit_code(
    "CONVERSION_FAILED",
    86,
    description="An amount could not be converted to the --convert currency",
    retryable=False,
    side_effects="none",
    suggestion="add the missing price directives, or run without --convert",
)


@dataclass(frozen=True, slots=True, kw_only=True)
class LedgerArgs:
    """The ledger flag every command takes."""

    file: Path | None = Flag(
        default=None,
        short="f",
        description="Main beancount file; default ./main.beancount",
        env=("BEANCOUNT_FILE",),
    )


def ledger_path(file: Path | None, ctx: Ctx) -> Path:
    """Resolve the ledger a command reads, failing with NOT_FOUND when it does not exist."""
    path = file if file is not None else ctx.cwd / "main.beancount"
    if not path.is_file():
        raise Exit.NOT_FOUND(
            f"Ledger file not found: {path}",
            context={"file": str(path)},
            suggestion="pass --file PATH or set BEANCOUNT_FILE",
        )
    return path


def refuse_directory_target(target: Path | None) -> None:
    """Refuse a ``--target`` that names a directory, at parse time (exit 2): an args
    ``__post_init__`` calls it, so nothing has run yet."""
    if target is not None and target.is_dir():
        raise ParseError(
            f"--target names a directory, not a file: {target}",
            context={"field": "target", "file": str(target)},
            suggestion="pass a file path, e.g. --target DIR/transactions.beancount",
        )


def target_path(target: Path | None, *, flag: str = "--target") -> Path | None:
    """Check the directory of the file a write flag (``--target``, ``--output-file``)
    names exists before anything is written; it is never created."""
    if target is None:
        return None
    directory = target.parent
    if not directory.is_dir():
        raise Exit.NOT_FOUND(
            f"Directory of {flag} not found: {directory}",
            context={"file": str(directory)},
            suggestion=f"create {directory} first, or pass a {flag} in an existing directory",
        )
    return target


def render_rows(
    title: str, columns: Sequence[str], rows: Sequence[Sequence[str]], right: Sequence[str] = ()
) -> str:
    """An aligned text table with a title line, for plain renderers."""
    table = Table(title=title)
    for column in columns:
        table.add_column(column, justify="right" if column in right else "left")
    for row in rows:
        table.add_row(*row)
    return f"{table}\n"


def text(record: Mapping[str, Any], key: str) -> str:
    """A value of a rendered record as text: missing (cut by --fields) and null are empty."""
    value = record.get(key)
    return "" if value is None else str(value)
