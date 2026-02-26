import datetime
import re
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated, Any

from pydantic import AfterValidator, BaseModel, Field


def validate_account_name(v: Any) -> str:
    """Validation logic for AccountName."""
    if not isinstance(v, str):
        raise TypeError("string required")
    if not re.match(r"^[A-Z][A-Za-z0-9\-]+(?::[A-Z][A-Za-z0-9\-]+)*$", v):
        raise ValueError(f"Invalid account name format: {v}")
    return v


def validate_currency_code(v: Any) -> str:
    """Validation logic for CurrencyCode."""
    if not isinstance(v, str):
        raise TypeError("string required")
    if not re.match(r"^[A-Z][A-Z0-9\'\.\_\-]{0,22}[A-Z0-9]$", v):
        raise ValueError(f"Invalid currency code format: {v}")
    return v


class AccountName(str):
    """Value Object for Beancount Account Names."""

    if TYPE_CHECKING:
        Input = Annotated[str | "AccountName", AfterValidator(validate_account_name)]
    else:
        Input = Annotated[str, AfterValidator(validate_account_name)]


class CurrencyCode(str):
    """Value Object for Beancount Currency Codes."""

    if TYPE_CHECKING:
        Input = Annotated[str | "CurrencyCode", AfterValidator(validate_currency_code)]
    else:
        Input = Annotated[str, AfterValidator(validate_currency_code)]


class AmountModel(BaseModel):
    """
    Represents a beancount.core.amount.Amount.
    """

    number: Decimal
    currency: CurrencyCode.Input


class CostModel(BaseModel):
    """
    Represents beancount.core.position.Cost (or CostSpec).
    """

    number: Decimal
    currency: CurrencyCode.Input
    date: datetime.date | None = None
    label: str | None = None


class PostingModel(BaseModel):
    """
    Represents a beancount.core.data.Posting.
    """

    account: AccountName.Input
    units: AmountModel
    cost: CostModel | None = None
    price: AmountModel | None = None
    flag: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class TransactionModel(BaseModel):
    """
    Represents a beancount.core.data.Transaction.
    """

    date: datetime.date

    flag: str = "*"
    payee: str | None = None
    narration: str
    tags: set[str] = Field(default_factory=set)
    links: set[str] = Field(default_factory=set)
    postings: list[PostingModel]
    meta: dict[str, Any] = Field(default_factory=dict)


class AccountModel(BaseModel):
    """
    Represents an Account (concept, usually from Open directive).
    """

    name: AccountName.Input
    open_date: datetime.date | None = None

    currencies: list[CurrencyCode.Input] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
