from decimal import Decimal

import pytest

from app.modules.split.service import SplitAmounts, calculate_split


def test_split_shares_items_allocates_fees_and_assigns_rounding_to_payer():
    result = calculate_split(
        item_amounts={101: Decimal(10000), 102: Decimal(10000)},
        selections={101: [1, 2, 3], 102: [1, 2]},
        payer_id=1,
        tax_amount=Decimal(1000),
        service_fee=Decimal(500),
    )

    assert result == {
        1: SplitAmounts(Decimal(8333), Decimal(625), Decimal(8959)),
        2: SplitAmounts(Decimal(8333), Decimal(625), Decimal(8958)),
        3: SplitAmounts(Decimal(3333), Decimal(250), Decimal(3583)),
    }
    assert sum(amount.final_amount for amount in result.values()) == Decimal(21500)


def test_split_rounds_half_up_and_includes_payer_without_item_selection():
    result = calculate_split(
        item_amounts={1: Decimal(1), 2: Decimal("1.5")},
        selections={1: [2, 3, 4], 2: [5]},
        payer_id=1,
    )

    assert result[1] == SplitAmounts(Decimal(0), Decimal(0), Decimal(1))
    assert result[5].item_amount == Decimal(2)
    assert sum(amount.final_amount for amount in result.values()) == Decimal(3)


@pytest.mark.parametrize(
    "item_amounts,selections,kwargs",
    [
        ({1: Decimal(10)}, {1: []}, {}),
        ({1: Decimal(10)}, {1: [2, 2]}, {}),
        ({1: Decimal(0)}, {1: [2]}, {"tax_amount": Decimal(1)}),
        ({1: Decimal(-1)}, {1: [2]}, {}),
    ],
)
def test_split_rejects_invalid_financial_inputs(item_amounts, selections, kwargs):
    with pytest.raises(ValueError):
        calculate_split(item_amounts, selections, payer_id=2, **kwargs)
