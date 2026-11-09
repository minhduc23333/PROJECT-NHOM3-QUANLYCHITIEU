from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Debt, GroupMember, Receipt, User
from app.modules.dashboard.schemas import DashboardSummary, MonthTotal

ZERO = Decimal("0")


def _last_months(n: int) -> list[str]:
    today = date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def summary(db: Session, user: User) -> DashboardSummary:
    group_ids = select(GroupMember.group_id).where(GroupMember.user_id == user.id, GroupMember.status == "ACTIVE")

    group_count = db.scalar(select(func.count()).select_from(group_ids.subquery())) or 0
    receipt_count = db.scalar(select(func.count(Receipt.id)).where(Receipt.group_id.in_(group_ids))) or 0
    total_spent = db.scalar(select(func.sum(Receipt.total_amount)).where(Receipt.payer_id == user.id)) or ZERO
    i_owe = db.scalar(select(func.sum(Debt.amount)).where(Debt.debtor_id == user.id, Debt.status == "OPEN")) or ZERO
    owed = db.scalar(select(func.sum(Debt.amount)).where(Debt.creditor_id == user.id, Debt.status == "OPEN")) or ZERO

    # Gom theo tháng bằng Python cho chạy được cả MySQL lẫn SQLite (test)
    months = _last_months(6)
    buckets: dict[str, Decimal] = defaultdict(lambda: ZERO)
    rows = db.execute(
        select(Receipt.receipt_date, Receipt.created_at, Receipt.total_amount).where(Receipt.payer_id == user.id)
    ).all()
    for r_date, created, amount in rows:
        d = r_date or (created.date() if created else None)
        if d and amount is not None:
            buckets[f"{d.year:04d}-{d.month:02d}"] += amount

    return DashboardSummary(
        group_count=group_count,
        receipt_count=receipt_count,
        total_spent=total_spent,
        i_owe=i_owe,
        owed_to_me=owed,
        monthly=[MonthTotal(month=m, total=buckets[m]) for m in months],
    )