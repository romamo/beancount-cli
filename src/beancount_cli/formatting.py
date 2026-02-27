import csv
import io
import json
import re
import sys
from typing import Any, TextIO


def apply_tags(s: str) -> str:
    msg = str(s)
    # Simple replacement dictionary
    colors = {
        "[red]": "\033[91m",
        "[/red]": "\033[0m",
        "[green]": "\033[92m",
        "[/green]": "\033[0m",
        "[yellow]": "\033[93m",
        "[/yellow]": "\033[0m",
        "[blue]": "\033[94m",
        "[/blue]": "\033[0m",
        "[cyan]": "\033[96m",
        "[/cyan]": "\033[0m",
        "[bold]": "\033[1m",
        "[/bold]": "\033[0m",
        "[dim]": "\033[2m",
        "[/dim]": "\033[0m",
        "[bold blue]": "\033[1m\033[94m",
        "[/bold blue]": "\033[0m",
    }
    for tag, ansi in colors.items():
        msg = msg.replace(tag, ansi)
    return msg


def strip_tags(s: str) -> str:
    return re.sub(r"\[/?.*?\]", "", str(s))


class Console:
    def __init__(self, file: TextIO | None = None):
        self.file = file

    def print(self, msg: Any = ""):
        out_file = self.file or sys.stdout
        if isinstance(msg, Table) or isinstance(msg, Tree):
            print(apply_tags(str(msg)), file=out_file)
            return
        print(apply_tags(str(msg)), file=out_file)


class Table:
    def __init__(self, title: str = ""):
        self.title = title
        self.columns: list[dict[str, str]] = []
        self.rows: list[list[Any] | None] = []

    def add_column(self, name: str, style: str = "", justify: str = "left"):
        self.columns.append({"name": name, "style": style, "justify": justify})

    def add_row(self, *args):
        self.rows.append(list(args))

    def add_section(self):
        # We represent sections as a None row if last row wasn't None
        if self.rows and self.rows[-1] is not None:
            self.rows.append(None)

    def __str__(self):
        # Calculate col widths based on raw string length (ignoring color tags)
        col_widths = [len(c["name"]) for c in self.columns]
        for row in self.rows:
            if row is not None:
                for i, col_val in enumerate(row):
                    if i < len(col_widths):
                        col_widths[i] = max(col_widths[i], len(strip_tags(col_val)))

        lines = []
        if self.title:
            lines.append(self.title)

        # Header
        header_cells = []
        for i, c in enumerate(self.columns):
            w = col_widths[i]
            val = c["name"]
            if c["style"]:
                val = f"[{c['style']}]{val}[/{c['style']}]"

            p_val = strip_tags(val)
            pad = w - len(p_val)
            if c["justify"] == "right":
                header_cells.append((" " * pad) + val)
            else:
                header_cells.append(val + (" " * pad))

        lines.append(" | ".join(header_cells))
        lines.append("-+-".join("-" * w for w in col_widths))

        for row in self.rows:
            if row is None:
                lines.append("-+-".join("-" * w for w in col_widths))
                continue

            row_cells = []
            for i, col_val in enumerate(row):
                if i >= len(self.columns):
                    break
                w = col_widths[i]
                c = self.columns[i]
                val = str(col_val)
                p_val = strip_tags(val)
                pad = w - len(p_val)
                if c["justify"] == "right":
                    row_cells.append((" " * pad) + val)
                else:
                    row_cells.append(val + (" " * pad))
            lines.append(" | ".join(row_cells))
        return "\n".join(lines)


class Tree:
    def __init__(self, label: str):
        self.label = label
        self.children: list[Tree] = []

    def add(self, label: str) -> "Tree":
        t = Tree(label)
        self.children.append(t)
        return t

    def _render(self, prefix: str = "", is_last: bool = True, is_root: bool = True) -> list[str]:
        lines = []
        if is_root:
            lines.append(self.label)
        else:
            lines.append(prefix + ("└── " if is_last else "├── ") + self.label)
            prefix += "    " if is_last else "│   "

        for i, child in enumerate(self.children):
            child_is_last = i == len(self.children) - 1
            lines.extend(child._render(prefix, child_is_last, is_root=False))
        return lines

    def __str__(self):
        return "\n".join(self._render())


def truncate_cell(value: str, max_width: int = 40) -> str:
    if len(value) <= max_width:
        return value
    return value[: max_width - 1] + "…"


def render_output(
    data: list[dict[str, Any]] | dict[str, Any],
    format_type: str = "table",
    title: str = "",
    console: Console | None = None,
) -> None:
    """
    Renders pure data structures into the specified format (table, json, csv).
    """
    out_console = console or Console()

    # Handle single item format (turn into list for table/csv processing, or format as key-value)
    data_list: list[dict[str, Any]]
    if isinstance(data, dict):
        is_single_item = True
        data_list = [data]
    else:
        is_single_item = False
        data_list = data

    if format_type == "json":
        out_console.print(json.dumps(data, indent=2, default=str))
        return

    if format_type == "csv":
        if not data_list:
            return

        output = io.StringIO()
        fieldnames = list(data_list[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()

        for row in data_list:
            writer.writerow({k: str(v) if v is not None else "" for k, v in row.items()})

        out_console.print(output.getvalue().strip())
        return

    # default to table format
    if is_single_item:
        # Key-Value fallback for single item
        table = Table(title=f"[bold]{title}[/bold]" if title else "")
        table.add_column("Key", style="cyan")
        table.add_column("Value")
        for k, v in data_list[0].items():
            table.add_row(k, str(v) if v is not None else "")
        out_console.print(table)
        return

    table = Table(title=f"[bold]{title}[/bold]" if title else "")
    if not data_list:
        out_console.print(table)
        return

    headers = list(data_list[0].keys())
    for key in headers:
        # Give some styling to particular columns
        style = ""
        if key in ["Account", "Account Name"]:
            style = "cyan"
        elif key == "Date":
            style = "green"
        table.add_column(key, style=style)

    for row in data_list:
        table_row = []
        for k, v in row.items():
            val = str(v) if v is not None else ""

            # Smart truncation for list tables
            # Don't truncate accounts or IDs
            if "Account" not in k and "ID" not in k and "id" not in k and "Date" not in k:
                strip_val = strip_tags(val)
                if len(strip_val) > 40:
                    val = truncate_cell(val, 40)
            table_row.append(val)
        table.add_row(*table_row)

    out_console.print(table)
