"""Run bean commands in-process, the way exec and agents do."""

import io
import os

from treaty import Envelope

from beancount_cli.cli import app

# The whole environment of each call: PATH for bean-format, no BEANCOUNT_FILE from the shell
ENV = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"], "BEAN_NO_UPDATE": "1"}


def call(path: str, **arguments: object) -> Envelope:
    """Run a command by its dotted path with JSON-style arguments and return its envelope."""
    return app.call(path, arguments, env=ENV)


def run(*argv: str, stdin: str = "") -> tuple[int, str, str]:
    """Run a command line off a terminal and return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    code = app.run(
        list(argv), stdin=io.StringIO(stdin), stdout=out, stderr=err, env=ENV, isatty=False
    )
    return code, out.getvalue(), err.getvalue()
