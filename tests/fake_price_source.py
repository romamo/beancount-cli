"""A beanprice source whose behaviour is chosen by the ticker, for price fetch tests.

Tickers: OK returns a price, NODATA returns None, BROKEN raises OSError (a
transport failure), BUG raises RuntimeError (a programming error).
"""

import datetime
from decimal import Decimal

from beanprice import source


class Source(source.Source):
    def get_latest_price(self, ticker: str) -> source.SourcePrice | None:
        return self._price(ticker)

    def get_historical_price(
        self, ticker: str, time: datetime.datetime
    ) -> source.SourcePrice | None:
        return self._price(ticker)

    def _price(self, ticker: str) -> source.SourcePrice | None:
        match ticker:
            case "OK":
                now = datetime.datetime.now(datetime.timezone.utc)
                return source.SourcePrice(Decimal("1.5"), now, "USD")
            case "NODATA":
                return None
            case "BROKEN":
                raise OSError("connection reset by peer")
            case "BUG":
                raise RuntimeError("source bug")
        raise AssertionError(f"unknown test ticker {ticker}")
