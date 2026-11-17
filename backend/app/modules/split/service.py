"""Pure financial calculations for splitting a receipt."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

VND = Decimal(1)
ZERO = Decimal(0)


@dataclass(frozen=True)
class SplitAmounts:
    item_amount: Decimal
    fee_amount: Decimal
    final_amount: Decimal


def _validate_amount(value: Decimal, name: str) -> None:
    if not value.is_finite() or value < ZERO:
        raise ValueError(f"{name} must be a finite, non-negative amount")


def _round_vnd(value: Decimal) -> Decimal:
    return value.quantize(VND, rounding=ROUND_HALF_UP)


def calculate_split(
    item_amounts: Mapping[int, Decimal],
    selections: Mapping[int, Sequence[int]],
    payer_id: int,
    tax_amount: Decimal = ZERO,
    service_fee: Decimal = ZERO,
) -> dict[int, SplitAmounts]:
    """Split each selected item evenly and allocate tax/service by item value.

    All returned amounts are rounded to whole VND. Any remaining difference
    between rounded member amounts and the rounded receipt total is assigned
    to the payer's ``final_amount``.
    """
    if not item_amounts:
        raise ValueError("at least one item is required")
    _validate_amount(tax_amount, "tax_amount")
    _validate_amount(service_fee, "service_fee")

    if set(selections) != set(item_amounts):
        raise ValueError("each item must have exactly one selection entry")

    raw_item_amounts: dict[int, Decimal] = {}
    for item_id, amount in item_amounts.items():
        _validate_amount(amount, f"item_amounts[{item_id}]")
        user_ids = selections[item_id]
        if not user_ids:
            raise ValueError(f"item {item_id} must be selected by at least one user")
        if len(set(user_ids)) != len(user_ids):
            raise ValueError(f"item {item_id} has duplicate user selections")

        share = amount / len(user_ids)
        for user_id in user_ids:
            raw_item_amounts[user_id] = raw_item_amounts.get(user_id, ZERO) + share

    subtotal = sum(item_amounts.values(), ZERO)
    total_fees = tax_amount + service_fee
    if subtotal == ZERO and total_fees > ZERO:
        raise ValueError("cannot allocate VAT/service fees when item total is zero")

    user_ids = set(raw_item_amounts)
    user_ids.add(payer_id)
    item_totals = {
        user_id: _round_vnd(raw_item_amounts.get(user_id, ZERO))
        for user_id in user_ids
    }

    fee_totals = {user_id: ZERO for user_id in user_ids}
    if total_fees > ZERO:
        for user_id in user_ids:
            proportional_fee = total_fees * raw_item_amounts.get(user_id, ZERO) / subtotal
            fee_totals[user_id] = _round_vnd(proportional_fee)

    receipt_total = _round_vnd(subtotal + total_fees)
    final_totals = {
        user_id: item_totals[user_id] + fee_totals[user_id]
        for user_id in user_ids
    }
    final_totals[payer_id] = receipt_total - sum(
        amount for user_id, amount in final_totals.items() if user_id != payer_id
    )
    if final_totals[payer_id] < ZERO:
        raise ValueError("rounding would make the payer's final amount negative")

    return {
        user_id: SplitAmounts(
            item_amount=item_totals[user_id],
            fee_amount=fee_totals[user_id],
            final_amount=final_totals[user_id],
        )
        for user_id in sorted(user_ids)
    }
