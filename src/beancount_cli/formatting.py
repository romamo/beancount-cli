"""Plain-text tables and trees for the commands' plain renderers."""


class Table:
    def __init__(self, title: str = ""):
        self.title = title
        self.columns: list[dict[str, str]] = []
        self.rows: list[list[str] | None] = []

    def add_column(self, name: str, justify: str = "left"):
        self.columns.append({"name": name, "justify": justify})

    def add_row(self, *args: str):
        self.rows.append(list(args))

    def add_section(self):
        # A section is a None row, never two in a row
        if self.rows and self.rows[-1] is not None:
            self.rows.append(None)

    def _cells(self, values: list[str], widths: list[int]) -> str:
        cells = []
        for value, width, column in zip(values, widths, self.columns, strict=False):
            cells.append(value.rjust(width) if column["justify"] == "right" else value.ljust(width))
        return " | ".join(cells).rstrip()

    def __str__(self):
        widths = [len(c["name"]) for c in self.columns]
        for row in self.rows:
            if row is not None:
                for i, value in enumerate(row[: len(widths)]):
                    widths[i] = max(widths[i], len(value))

        rule = "-+-".join("-" * w for w in widths)
        lines = [self.title] if self.title else []
        lines.append(self._cells([c["name"] for c in self.columns], widths))
        lines.append(rule)
        for row in self.rows:
            lines.append(rule if row is None else self._cells(row, widths))
        return "\n".join(lines)


class Tree:
    def __init__(self, label: str):
        self.label = label
        self.children: list[Tree] = []

    def add(self, label: str) -> Tree:
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
