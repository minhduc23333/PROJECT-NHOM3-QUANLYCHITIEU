"""Báo cáo chi tiêu theo thời gian / danh mục (T05E180). Chỉ tính hóa đơn SETTLED.

Phạm vi (giống Dashboard T05E17D):
  - scope="me":    phần của tôi = Σ split_details.final_amount trên hóa đơn nhóm
                   + Σ total_amount hóa đơn cá nhân của tôi (chỉ khi không lọc theo nhóm);
  - scope="group": tổng tiền hóa đơn (total_amount) của các nhóm tôi đang là thành viên ACTIVE.
  - group_id: chỉ một nhóm (phải là thành viên ACTIVE: 404 / 403).
Ngày của hóa đơn = receipt_date, không có thì lấy ngày tạo.
"""
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.deps import get_group_membership
from app.core.errors import Unprocessable
from app.models import GroupMember, Receipt, SplitDetail, User
from app.modules.dashboard.schemas import ReportCategory, ReportMerchant, ReportPeriod, SpendingReport

ZERO = Decimal(0)
SETTLED = "SETTLED"
DEFAULT_CATEGORY = "Khác"
MAX_DAYS = 731  # tối đa ~2 năm cho một báo cáo
TOP_MERCHANTS = 5

Granularity = Literal["auto", "day", "week", "month"]


def default_range(today: date | None = None) -> tuple[date, date]:
    """Mặc định: 6 tháng gần nhất (từ ngày 1 của tháng cách đây 5 tháng tới hôm nay)."""
    today = today or date.today()
    y, m = today.year, today.month - 5
    while m <= 0:
        y, m = y - 1, m + 12
    return date(y, m, 1), today


def pick_granularity(date_from: date, date_to: date, wanted: str) -> str:
    if wanted != "auto":
        return wanted
    days = (date_to - date_from).days + 1
    return "day" if days <= 31 else "week" if days <= 120 else "month"


def _period_start(d: date, g: str) -> date:
    if g == "day":
        return d
    if g == "week":
        return d - timedelta(days=d.weekday())  # thứ Hai
    return d.replace(day=1)


def _next_start(start: date, g: str) -> date:
    if g == "day":
        return start + timedelta(days=1)
    if g == "week":
        return start + timedelta(days=7)
    return date(start.year + (start.month == 12), start.month % 12 + 1, 1)


def _key_label(start: date, g: str) -> tuple[str, str]:
    if g == "day":
        return start.isoformat(), start.strftime("%d/%m")
    if g == "week":
        iso = start.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}", start.strftime("%d/%m")
    return f"{start.year:04d}-{start.month:02d}", f"{start.month:02d}/{start.year}"


def _rows(db: Session, user: User, scope: str, group_id: int | None):
    """(receipt_id, ngày, danh mục, tên cửa hàng, số tiền) theo phạm vi quyền."""
    if group_id is not None:
        get_group_membership(db, group_id, user.id)  # 404 / 403
        groups_cond = Receipt.group_id == group_id
    else:
        active = select(GroupMember.group_id).where(GroupMember.user_id == user.id, GroupMember.status == "ACTIVE")
        groups_cond = Receipt.group_id.in_(active)
    in_groups = and_(Receipt.status == SETTLED, groups_cond)
    cols = (Receipt.id, Receipt.receipt_date, Receipt.created_at, Receipt.category, Receipt.merchant_name)

    if scope == "group":
        rows = db.execute(select(*cols, Receipt.total_amount).where(in_groups)).all()
    else:
        rows = db.execute(
            select(*cols, SplitDetail.final_amount)
            .select_from(Receipt)
            .join(SplitDetail, and_(SplitDetail.receipt_id == Receipt.id, SplitDetail.user_id == user.id))
            .where(in_groups)
        ).all()
        if group_id is None:  # hóa đơn cá nhân chỉ thuộc phạm vi "của tôi" khi không lọc nhóm
            rows += db.execute(
                select(*cols, Receipt.total_amount).where(
                    Receipt.status == SETTLED, Receipt.group_id.is_(None), Receipt.uploaded_by == user.id
                )
            ).all()
    out = []
    for rid, r_date, created, category, merchant, amount in rows:
        when = r_date or (created.date() if created else None)
        if when is None:
            continue
        out.append((rid, when, (category or "").strip() or DEFAULT_CATEGORY, (merchant or "").strip(), amount or ZERO))
    return out


def spending_report(
    db: Session,
    user: User,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    granularity: Granularity = "auto",
    scope: Literal["me", "group"] = "me",
    group_id: int | None = None,
) -> SpendingReport:
    d_from, d_to = default_range()
    date_from = date_from or d_from
    date_to = date_to or d_to
    errors = []
    if date_from > date_to:
        errors.append({"field": "date_from", "message": "Ngày bắt đầu phải trước hoặc bằng ngày kết thúc"})
    elif (date_to - date_from).days + 1 > MAX_DAYS:
        errors.append({"field": "date_to", "message": "Khoảng thời gian tối đa là 2 năm"})
    if errors:
        raise Unprocessable("Khoảng thời gian không hợp lệ", details=errors)

    g = pick_granularity(date_from, date_to, granularity)
    rows = [r for r in _rows(db, user, scope, group_id) if date_from <= r[1] <= date_to]

    # Đủ mọi kỳ trong khoảng (kỳ trống = 0) để biểu đồ liền mạch
    periods: dict[date, dict] = {}
    start = _period_start(date_from, g)
    while start <= date_to:
        nxt = _next_start(start, g)
        periods[start] = {"start": max(start, date_from), "end": min(nxt - timedelta(days=1), date_to),
                          "total": ZERO, "cats": defaultdict(lambda: ZERO)}
        start = nxt

    by_cat: dict[str, Decimal] = defaultdict(lambda: ZERO)
    cat_receipts: dict[str, set[int]] = defaultdict(set)
    by_merchant: dict[str, Decimal] = defaultdict(lambda: ZERO)
    merchant_receipts: dict[str, set[int]] = defaultdict(set)
    receipts: set[int] = set()
    total = ZERO
    for rid, when, cat, merchant, amount in rows:
        p = periods[_period_start(when, g)]
        p["total"] += amount
        p["cats"][cat] += amount
        by_cat[cat] += amount
        cat_receipts[cat].add(rid)
        if merchant:
            by_merchant[merchant] += amount
            merchant_receipts[merchant].add(rid)
        receipts.add(rid)
        total += amount

    def pct(v: Decimal) -> float:
        return float((v * 100 / total).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)) if total else 0.0

    period_list = []
    for s, p in periods.items():
        key, label = _key_label(s, g)
        period_list.append(ReportPeriod(key=key, label=label, start=p["start"], end=p["end"],
                                        total=p["total"], by_category=dict(p["cats"])))
    avg = (total / len(period_list)).quantize(Decimal("1"), rounding=ROUND_HALF_UP) if period_list else ZERO

    return SpendingReport(
        date_from=date_from,
        date_to=date_to,
        granularity=g,
        scope=scope,
        group_id=group_id,
        total=total,
        receipt_count=len(receipts),
        average_per_period=avg,
        periods=period_list,
        by_category=[
            ReportCategory(category=c, total=t, receipt_count=len(cat_receipts[c]), percent=pct(t))
            for c, t in sorted(by_cat.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        top_merchants=[
            ReportMerchant(merchant=m, total=t, receipt_count=len(merchant_receipts[m]))
            for m, t in sorted(by_merchant.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_MERCHANTS]
        ],
    )
