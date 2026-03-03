import sys

import agentyper as typer

from beancount_cli import __version__
from beancount_cli.commands.account import app as acc_app
from beancount_cli.commands.commodity import app as comm_app
from beancount_cli.commands.report import app as report_app
from beancount_cli.commands.root import check, format_cmd, price, tree
from beancount_cli.commands.transaction import app as tx_app

app = typer.Agentyper(
    name="beancount-cli",
    version=__version__,
    help="Beancount CLI tool for managing ledgers.",
)

app.add_typer(report_app, name="report")
app.add_typer(tx_app, name="transaction")
app.add_typer(acc_app, name="account")
app.add_typer(comm_app, name="commodity")

app.command(name="check")(check)
app.command(name="tree")(tree)
app.command(name="format")(format_cmd)
app.command(name="price")(price)


def main(args=None):
    if args is not None:
        _old_argv = sys.argv
        sys.argv = ["bean"] + args
        try:
            app()
        finally:
            sys.argv = _old_argv
    else:
        app()


if __name__ == "__main__":
    main()
