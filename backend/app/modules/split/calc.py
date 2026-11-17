"""Thuật toán chia tiền (hàm thuần, không đụng DB nên test được độc lập).

Quy tắc:
  * Món có k người chọn → mỗi người trả line_total / k.
  * Thuế + phí dịch vụ chia theo TỈ LỆ phần món của từng người trên tổng tạm tính (subtotal).
  * Mỗi người làm tròn XUỐNG tới đồng. Phần lẻ còn thiếu (so với total_amount) dồn hết cho
    NGƯỜI TRẢ TIỀN (cộng vào fee_amount của người đó) → Σ final_amount luôn = total_amount.
  * Dùng Fraction để không mất độ chính xác trước khi làm tròn.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction

ZERO = Decimal(0)


@dataclass
class Share:
    item_amount: Decimal = ZERO
    fee_amount: Decimal = ZERO

    @property
    def final_amount(self) -> Decimal:
        return self.item_amount + self.fee_amount


def compute_shares(
    item_totals: dict[int, Decimal],
    selectors: dict[int, list[int]],
    fee_total: Decimal,
) -> dict[int, Share]:
    """item_totals: {item_id: line_total của TẤT CẢ món}; selectors: {item_id: [user_id,...]}.

    Chỉ trả về những người có chọn ít nhất 1 món. Món chưa ai chọn không được tính cho ai.
    Mỗi phần đã làm tròn xuống tới đồng (chưa dồn phần lẻ — xem `assign_remainder`).
    """
    base = sum(item_totals.values(), ZERO)
    exact: dict[int, Fraction] = {}
    for item_id, line_total in item_totals.items():
        users = sorted(set(selectors.get(item_id, ())))
        if not users:
            continue
        part = Fraction(line_total) / len(users)
        for uid in users:
            exact[uid] = exact.get(uid, Fraction(0)) + part

    shares: dict[int, Share] = {}
    for uid, amount in exact.items():
        fee = Fraction(fee_total) * amount / Fraction(base) if base > 0 else Fraction(0)
        shares[uid] = Share(Decimal(math.floor(amount)), Decimal(math.floor(fee)))
    return shares


def assign_remainder(shares: dict[int, Share], payer_id: int, total_amount: Decimal) -> dict[int, Share]:
    """Dồn phần lẻ (total_amount − Σ đã làm tròn) cho người trả tiền. Trả về dict mới."""
    result = {uid: Share(s.item_amount, s.fee_amount) for uid, s in shares.items()}
    remainder = total_amount - sum((s.final_amount for s in result.values()), ZERO)
    if remainder < 0:  # không thể xảy ra với làm tròn xuống; chặn để không ghi số âm vào DB
        raise ValueError("Tổng phần chia vượt quá tổng hóa đơn")
    if remainder > 0:
        result.setdefault(payer_id, Share()).fee_amount += remainder
    return result
