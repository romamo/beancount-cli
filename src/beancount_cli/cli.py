from beancount_cli.app import app
from beancount_cli.commands import account, commodity, price, report, root, transaction

# Each module registers its commands on ``app`` when imported
__all__ = ["account", "app", "commodity", "main", "price", "report", "root", "transaction"]


def main() -> None:
    app.main()


if __name__ == "__main__":
    main()
