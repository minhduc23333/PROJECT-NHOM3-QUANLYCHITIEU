"""Số liệu Dashboard (T05E17D). Chi tiêu nhóm tính hóa đơn SETTLED, hóa đơn cá nhân tính VERIFIED trở lên.

Phạm vi quyền:
  - hóa đơn nhóm: chỉ các nhóm mà người dùng là thành viên ACTIVE (bị REMOVED thì không thấy nữa);
  - hóa đơn cá nhân (group_id NULL): chỉ chủ sở hữu (uploaded_by).

Cách tính (SRS FR-12):
  - chi tiêu cá nhân = Σ split_details.final_amount của tôi trên hóa đơn nhóm SETTLED
                       + Σ total_amount hóa đơn cá nhân VERIFIED/SETTLED (không chia với ai);
  - chi tiêu nhóm    = Σ total_amount các hóa đơn SETTLED thuộc nhóm của tôi
                       (không cộng vào chi tiêu cá nhân).
Gom theo tháng/danh mục bằng Python để chạy được cả MySQL lẫn SQLite (test).
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import Debt, Group, GroupMember, Receipt, SplitDetail, User
from app.modules.dashboard.schemas import (
    CategoryTotal,
    DashboardSummary,
    MonthTotal,
    RecentReceipt,
)

ZERO = Decimal(0)
SETTLED = "SETTLED"
MONTHS = 6
RECENT_LIMIT = 5
DEFAULT_CATEGORY = "Khác"


def _last_months(n: int, today: date | None = None) -> list[str]:
    today = today or date.today()
    year, month = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(out))


def summary(db: Session, user: User) -> DashboardSummary:
    active_groups = select(GroupMember.group_id).where(
        GroupMember.user_id == user.id, GroupMember.status == "ACTIVE"
    )
    my_group_receipts = Receipt.group_id.in_(active_groups)
    my_personal_receipts = and_(Receipt.group_id.is_(None), Receipt.uploaded_by == user.id)
    in_my_groups = and_(Receipt.status == SETTLED, Receipt.group_id.in_(active_groups))
    my_personal_settled = and_(
        Receipt.status == SETTLED, Receipt.group_id.is_(None), Receipt.uploaded_by == user.id
    )
    my_personal_spent = and_(
        Receipt.status.in_(("VERIFIED", SETTLED)), Receipt.group_id.is_(None), Receipt.uploaded_by == user.id
    )

    group_count = db.scalar(select(func.count()).select_from(active_groups.subquery())) or 0
    receipt_count = db.scalar(select(func.count(Receipt.id)).where(or_(in_my_groups, my_personal_settled))) or 0
    total_receipt_count = db.scalar(
        select(func.count(Receipt.id)).where(or_(my_group_receipts, my_personal_receipts))
    ) or 0
    group_spent = db.scalar(select(func.sum(Receipt.total_amount)).where(in_my_groups)) or ZERO
    i_owe = db.scalar(select(func.sum(Debt.amount)).where(Debt.debtor_id == user.id, Debt.status == "OPEN")) or ZERO
    owed_to_me = db.scalar(select(func.sum(Debt.amount)).where(Debt.creditor_id == user.id, Debt.status == "OPEN")) or ZERO

    # Phần chi tiêu của tôi trên từng hóa đơn: (receipt_id, ngày, danh mục, số tiền)
    mine: list[tuple[int, date | None, str | None, Decimal]] = []
    shared = db.execute(
        select(Receipt.id, Receipt.receipt_date, Receipt.created_at, Receipt.category, SplitDetail.final_amount)
        .select_from(Receipt)
        .join(SplitDetail, and_(SplitDetail.receipt_id == Receipt.id, SplitDetail.user_id == user.id))
        .where(in_my_groups)
    ).all()
    personal = db.execute(
        select(Receipt.id, Receipt.receipt_date, Receipt.created_at, Receipt.category, Receipt.total_amount).where(
            my_personal_spent
        )
    ).all()
    for rid, r_date, created, category, amount in [*shared, *personal]:
        when = r_date or (created.date() if created else None)
        mine.append((rid, when, category, amount if amount is not None else ZERO))

    personal_spent = sum((row[3] for row in mine), ZERO)

    by_month: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_cat: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for _, when, category, amount in mine:
        if when is not None:
            by_month[f"{when.year:04d}-{when.month:02d}"] += amount
        by_cat[(category or "").strip() or DEFAULT_CATEGORY] += amount
    months = _last_months(MONTHS)
    my_amount = {row[0]: row[3] for row in mine}

    recent_rows = db.execute(
        select(Receipt, Group.name)
        .select_from(Receipt)
        .outerjoin(Group, Group.id == Receipt.group_id)
        .where(or_(my_group_receipts, my_personal_receipts))
        .order_by(Receipt.created_at.desc(), Receipt.id.desc())
        .limit(RECENT_LIMIT)
    ).all()
    recent = [
        RecentReceipt(
            id=r.id,
            group_id=r.group_id,
            group_name=group_name,
            merchant_name=r.merchant_name,
            receipt_date=r.receipt_date,
            created_at=r.created_at,
            category=r.category,
            status=r.status,
            total_amount=r.total_amount,
            my_amount=my_amount.get(r.id, ZERO),
        )
        for r, group_name in recent_rows
    ]

    return DashboardSummary(
        group_count=group_count,
        receipt_count=receipt_count,
        total_receipt_count=total_receipt_count,
        personal_spent=personal_spent,
        group_spent=group_spent,
        i_owe=i_owe,
        owed_to_me=owed_to_me,
        monthly=[MonthTotal(month=m, total=by_month[m]) for m in months],
        by_category=[
            CategoryTotal(category=c, total=t)
            for c, t in sorted(by_cat.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        recent_receipts=recent,
    )
