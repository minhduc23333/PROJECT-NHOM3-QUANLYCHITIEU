"""Regression logic chia tiền (T05E186): kiểm tra TÍNH CHẤT của calc.py trên nhiều bộ dữ liệu ngẫu nhiên có seed cố định.

Bất biến cần luôn đúng:
  1. Σ final_amount = total_amount (không mất, không thừa một đồng).
  2. Mọi item_amount / fee_amount >= 0 và là số nguyên đồng (ràng buộc DB).
  3. Phần lẻ chỉ dồn cho người trả tiền, người khác không bị cộng thêm.
"""
import random
from decimal import Decimal

import pytest

from app.modules.split import calc

D = Decimal


def _case(rng):
    n_users = rng.randint(1, 6)
    users = list(range(1, n_users + 1))
    items = {i: D(rng.randint(1, 500) * rng.choice([1, 100, 1000])) for i in range(1, rng.randint(1, 12) + 1)}
    selectors = {i: rng.sample(users, rng.randint(1, n_users)) for i in items}   # mọi món có ít nhất 1 người chọn
    base = sum(items.values(), D(0))
    fee = D(rng.randint(0, int(base) // 4)) if rng.random() < 0.8 else D(0)
    discount = D(rng.randint(0, min(int(base), 5000))) if rng.random() < 0.5 else D(0)
    total = base + fee - discount
    return users, items, selectors, fee, discount, total


@pytest.mark.parametrize("seed", range(40))
def test_invariants_on_random_receipts(seed):
    rng = random.Random(seed)
    for _ in range(25):
        users, items, selectors, fee, discount, total = _case(rng)
        payer = rng.choice(users)
        shares = calc.assign_remainder(calc.compute_shares(items, selectors, fee, discount), payer, total)
        assert sum((s.final_amount for s in shares.values()), D(0)) == total
        for s in shares.values():
            assert s.item_amount >= 0 and s.fee_amount >= 0
            assert s.item_amount == s.item_amount.to_integral_value()
            assert s.fee_amount == s.fee_amount.to_integral_value()


def test_remainder_only_changes_the_payer():
    items, selectors = {1: D(100000)}, {1: [1, 2, 3]}          # 100.000 / 3 = 33.333,33...
    before = calc.compute_shares(items, selectors, D(0))
    after = calc.assign_remainder(before, payer_id=2, total_amount=D(100000))
    assert after[1].final_amount == before[1].final_amount == D(33333)
    assert after[3].final_amount == before[3].final_amount == D(33333)
    assert after[2].final_amount == D(33334)                    # người trả nhận phần lẻ 1 đồng


def test_discount_larger_than_fee_never_makes_negative_amounts():
    items, selectors = {1: D(50000), 2: D(30000)}, {1: [1], 2: [2]}
    shares = calc.compute_shares(items, selectors, fee_total=D(0), discount_amount=D(641))
    assert all(s.item_amount >= 0 and s.fee_amount >= 0 for s in shares.values())
    final = calc.assign_remainder(shares, payer_id=1, total_amount=D(80000) - D(641))
    assert sum((s.final_amount for s in final.values()), D(0)) == D(79359)


def test_unselected_item_goes_to_payer_so_total_still_matches():
    items, selectors = {1: D(60000), 2: D(40000)}, {1: [1]}     # món 2 chưa ai chọn
    final = calc.assign_remainder(calc.compute_shares(items, selectors, D(0)), payer_id=2, total_amount=D(100000))
    assert final[1].final_amount == D(60000) and final[2].final_amount == D(40000)


def test_tax_and_service_fee_are_proportional_to_item_share():
    items, selectors = {1: D(75000), 2: D(25000)}, {1: [1], 2: [2]}
    shares = calc.compute_shares(items, selectors, fee_total=D(10000))
    assert shares[1].fee_amount == D(7500) and shares[2].fee_amount == D(2500)


def test_total_smaller_than_shares_is_rejected_not_written():
    shares = calc.compute_shares({1: D(100000)}, {1: [1]}, D(0))
    with pytest.raises(ValueError):
        calc.assign_remainder(shares, payer_id=1, total_amount=D(99000))
