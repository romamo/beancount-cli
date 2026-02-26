from datetime import date

from beancount.core import amount, data, position

from beancount_cli.models import (
    AccountName,
    AmountModel,
    CostModel,
    CurrencyCode,
    PostingModel,
    TransactionModel,
)


def to_core_amount(model: AmountModel) -> amount.Amount:
    return amount.Amount(model.number, str(model.currency))


def from_core_amount(core: amount.Amount) -> AmountModel:
    from decimal import Decimal
    from typing import cast

    return AmountModel(
        number=cast(Decimal, core.number), currency=CurrencyCode(cast(str, core.currency))
    )


def to_core_cost(model: CostModel | None) -> position.Cost | None:
    if model is None:
        return None
    # Note: CostSpec and Cost have different fields. Assuming we deal with Cost (resolved) mostly,
    # but for new transactions it might be CostSpec.
    # For now, let's map to Cost if possible, or support CostSpec if needed.
    # Beancount Cost namedtuple: number, currency, date, label
    from typing import cast

    return position.Cost(model.number, str(model.currency), cast(date, model.date), model.label)


def from_core_cost(core: position.Cost | None) -> CostModel | None:
    if core is None:
        return None
    return CostModel(
        number=core.number, currency=CurrencyCode(core.currency), date=core.date, label=core.label
    )


def to_core_posting(model: PostingModel) -> data.Posting:
    units = to_core_amount(model.units)
    cost = to_core_cost(model.cost)
    price = to_core_amount(model.price) if model.price else None

    return data.Posting(
        account=str(model.account),
        units=units,
        cost=cost,
        price=price,
        flag=model.flag,
        meta=model.meta,
    )


def from_core_posting(core: data.Posting) -> PostingModel:
    from typing import cast

    return PostingModel(
        account=AccountName(core.account),
        units=from_core_amount(cast(amount.Amount, core.units)),
        cost=from_core_cost(cast(position.Cost | None, core.cost)),
        price=from_core_amount(cast(amount.Amount, core.price)) if core.price else None,
        flag=core.flag or "",
        meta=core.meta or {},
    )


def to_core_transaction(model: TransactionModel) -> data.Transaction:
    postings = [to_core_posting(p) for p in model.postings]
    return data.Transaction(
        meta=model.meta or {},
        date=model.date,
        flag=model.flag,
        payee=model.payee,
        narration=model.narration,
        tags=frozenset(model.tags) if model.tags else frozenset(),
        links=frozenset(model.links) if model.links else frozenset(),
        postings=postings,
    )


def from_core_transaction(core: data.Transaction) -> TransactionModel:
    return TransactionModel(
        date=core.date,
        flag=core.flag or "",
        payee=core.payee,
        narration=core.narration or "",
        tags=set(core.tags) if core.tags else set(),
        links=set(core.links) if core.links else set(),
        postings=[from_core_posting(p) for p in core.postings],
        meta=core.meta or {},
    )
