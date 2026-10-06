from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from treaty import Arg, Ctx, Exit, Flag, Format, Out

from beancount_cli.app import LedgerArgs, app, ledger_path
from beancount_cli.formatting import Tree
from beancount_cli.services import LedgerService, MapService


@dataclass(frozen=True, slots=True)
class FileArgs(LedgerArgs):
    ledger_file: Path | None = Arg(default=None, description="Ledger file; overrides --file")


@dataclass(frozen=True, slots=True)
class LedgerError:
    location: str | None
    message: str


@dataclass(frozen=True, slots=True)
class CheckResult:
    file: Path
    valid: bool
    errors: list[LedgerError] = Out(default_factory=list, ordered=True)


def render_check(data: Mapping[str, Any]) -> str:
    return "No errors found.\n"


@app.command(
    "check",
    description="Validate the ledger file",
    danger_level="safe",
    exit_codes=["NOT_FOUND", "LEDGER_INVALID"],
    examples=[
        ("Validate the ledger", "bean check main.beancount"),
        ("Validate the ledger BEANCOUNT_FILE names", "bean check"),
    ],
    renderers={Format.PLAIN: render_check},
)
def check(args: FileArgs, ctx: Ctx) -> CheckResult:
    actual_file = ledger_path(args.ledger_file or args.file, ctx)
    service = LedgerService(actual_file)
    service.load()

    errors = [
        LedgerError(
            location=f"{e.source['filename']}:{e.source['lineno']}" if e.source else None,
            message=e.message,
        )
        for e in service.errors
    ]
    if errors:
        raise Exit.LEDGER_INVALID(
            f"{len(errors)} errors in {actual_file}",
            context={
                "file": str(actual_file),
                "errors": [{"location": e.location, "message": e.message} for e in errors],
            },
            data=CheckResult(file=actual_file, valid=False, errors=errors),
        )
    return CheckResult(file=actual_file, valid=True)


@dataclass(frozen=True, slots=True)
class IncludedFile:
    path: str
    parent: str
    depth: int


@dataclass(frozen=True, slots=True)
class IncludeTree:
    file: Path
    includes: list[IncludedFile] = Out(default_factory=list, ordered=True)


def _flatten(tree: dict[str, Any], parent: str, depth: int) -> list[IncludedFile]:
    files = []
    for path, children in tree.items():
        files.append(IncludedFile(path=path, parent=parent, depth=depth))
        files.extend(_flatten(children, path, depth + 1))
    return files


def render_tree(data: Mapping[str, Any]) -> str:
    root = Tree(str(data.get("file", "")))
    nodes = {root.label: root}
    for included in data.get("includes", []):
        nodes[included["path"]] = nodes[included["parent"]].add(included["path"])
    return f"{root}\n"


@app.command(
    "tree",
    description="Show the tree of included files, depth first",
    danger_level="safe",
    exit_codes=["NOT_FOUND"],
    examples=[("Show what main.beancount includes", "bean tree main.beancount")],
    renderers={Format.PLAIN: render_tree},
)
def tree(args: FileArgs, ctx: Ctx) -> IncludeTree:
    actual_file = ledger_path(args.ledger_file or args.file, ctx)
    include_tree = MapService(actual_file).get_include_tree()
    return IncludeTree(file=actual_file, includes=_flatten(include_tree, str(actual_file), 0))


@dataclass(frozen=True, slots=True)
class FormatArgs(FileArgs):
    dry_run: bool = Flag(default=False, description="Report whether the file would change")


@dataclass(frozen=True, slots=True)
class Formatted:
    effect: Literal["updated", "noop", "would_update"]
    file: Path
    changed: bool


def render_format(data: Mapping[str, Any]) -> str:
    file = data.get("file", "")
    match data.get("effect"):
        case "noop":
            return f"{file} is already formatted.\n"
        case "would_update":
            return f"Would format {file}.\n"
        case _:
            return f"Formatted {file}\n"


@app.command(
    "format",
    description="Format the ledger file with bean-format",
    danger_level="mutating",
    exit_codes=["NOT_FOUND", "FORMAT_FAILED"],
    external=False,
    examples=[
        ("Format the ledger in place", "bean format main.beancount"),
        ("Check whether it needs formatting", "bean format main.beancount --dry-run"),
    ],
    renderers={Format.PLAIN: render_format},
)
def format_cmd(args: FormatArgs, ctx: Ctx) -> Formatted:
    actual_file = ledger_path(args.ledger_file or args.file, ctx)
    done = ctx.run(["bean-format", "-c", "50", str(actual_file)], check=False)
    if done.returncode != 0:
        raise Exit.FORMAT_FAILED(
            f"bean-format failed: {done.stderr.strip()}",
            context={"file": str(actual_file), "returncode": done.returncode},
        )

    changed = done.stdout != actual_file.read_text()
    if not changed:
        return Formatted(effect="noop", file=actual_file, changed=False)
    if args.dry_run:
        return Formatted(effect="would_update", file=actual_file, changed=True)
    actual_file.write_text(done.stdout)
    return Formatted(effect="updated", file=actual_file, changed=True)
