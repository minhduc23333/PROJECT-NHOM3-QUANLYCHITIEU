"""Module chia tiền: chọn món → chốt (tính chia + tạo công nợ) → xem công nợ.

Phạm vi quyền:
  * Thành viên ACTIVE tự chọn món; LEADER có thể chọn/bỏ chọn thay thành viên ACTIVE. Hóa đơn SETTLED bị khóa (409).
  * Chốt: chỉ LEADER, hóa đơn phải VERIFIED. Toàn bộ ghi split_details + debts + đổi SETTLED nằm trong 1 transaction.
  * Xem công nợ: thành viên ACTIVE của nhóm thấy công nợ của nhóm đó; hóa đơn cá nhân chỉ chủ sở hữu.
Selection của người đã bị gỡ khỏi nhóm (không còn ACTIVE) bị bỏ qua: món đó coi như chưa ai chọn.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, aliased

from app.core.deps import get_group_membership, require_leader
from app.core.errors import BadRequest, Conflict, Forbidden, NotFound, Unprocessable
from app.models import (
    Debt,
    GroupMember,
    ItemSelection,
    Receipt,
    ReceiptItem,
    SplitDetail,
    User,
)
from app.modules.receipts import state
from app.modules.split import calc
from app.modules.split.schemas import (
    DebtList,
    DebtOut,
    MemberShare,
    SelectionSummary,
    SplitLine,
    SplitResult,
    UnselectedItem,
)

ZERO = Decimal(0)
ERR_PERSONAL = "PERSONAL_RECEIPT"


# ---------- Helper ----------
def _load(db: Session, user: User, receipt_id: int, *, lock: bool = False) -> tuple[Receipt, GroupMember | None]:
    """404 nếu không có hóa đơn; hóa đơn cá nhân chỉ chủ sở hữu; hóa đơn nhóm cần là thành viên ACTIVE."""
    stmt = select(Receipt).where(Receipt.id == receipt_id)
    if lock:
        stmt = stmt.with_for_update()  # MySQL: khóa dòng để chọn món / chốt không đè nhau
    receipt = db.scalar(stmt)
    if receipt is None:
        raise NotFound("Không tìm thấy hóa đơn")
    if receipt.group_id is None:
        if receipt.uploaded_by != user.id:
            raise Forbidden("Bạn không có quyền truy cập hóa đơn cá nhân này")
        return receipt, None
    _, member = get_group_membership(db, receipt.group_id, user.id)
    return receipt, member


def _load_group_receipt(db: Session, user: User, receipt_id: int, *, lock: bool = False) -> tuple[Receipt, GroupMember]:
    receipt, member = _load(db, user, receipt_id, lock=lock)
    if member is None:
        raise BadRequest("Hóa đơn cá nhân không có chia tiền theo nhóm", code=ERR_PERSONAL)
    return receipt, member


def _items(db: Session, receipt_id: int) -> list[ReceiptItem]:
    return list(db.scalars(select(ReceiptItem).where(ReceiptItem.receipt_id == receipt_id).order_by(ReceiptItem.id)))


def _active_members(db: Session, group_id: int) -> list[tuple[int, str]]:
    rows = db.execute(
        select(User.id, User.full_name)
        .join(GroupMember, GroupMember.user_id == User.id)
        .where(GroupMember.group_id == group_id, GroupMember.status == "ACTIVE")
        .order_by(User.full_name, User.id)
    ).all()
    return [(uid, name) for uid, name in rows]


def _selectors(db: Session, receipt_id: int, active_ids: set[int]) -> dict[int, list[int]]:
    """{item_id: [user_id,...]} chỉ tính người còn ACTIVE; JOIN receipt_items nên bỏ qua selection mồ côi."""
    rows = db.execute(
        select(ItemSelection.item_id, ItemSelection.user_id)
        .join(ReceiptItem, ReceiptItem.id == ItemSelection.item_id)
        .where(ReceiptItem.receipt_id == receipt_id, ItemSelection.user_id.in_(active_ids or {-1}))
        .order_by(ItemSelection.item_id, ItemSelection.user_id)
    ).all()
    out: dict[int, list[int]] = {}
    for item_id, uid in rows:
        out.setdefault(item_id, []).append(uid)
    return out


def _fee_total(receipt: Receipt) -> Decimal:
    return (receipt.tax_amount or ZERO) + (receipt.service_fee or ZERO)


def _discount_amount(receipt: Receipt) -> Decimal:
    return receipt.discount_amount or ZERO


# ---------- 1. Chọn / bỏ chọn món + tổng tạm tính ----------
def selection_summary(db: Session, user: User, receipt_id: int) -> SelectionSummary:
    receipt, _ = _load_group_receipt(db, user, receipt_id)
    return _summary(db, receipt, user)


def _summary(db: Session, receipt: Receipt, user: User) -> SelectionSummary:
    items = _items(db, receipt.id)
    members = _active_members(db, receipt.group_id)
    selectors = _selectors(db, receipt.id, {uid for uid, _ in members})
    shares = calc.compute_shares({i.id: i.line_total for i in items}, selectors, _fee_total(receipt), _discount_amount(receipt))

    chosen_by: dict[int, list[int]] = {}
    for item_id, users in selectors.items():
        for uid in users:
            chosen_by.setdefault(uid, []).append(item_id)

    member_rows = []
    for uid, name in members:
        share = shares.get(uid, calc.Share())
        member_rows.append(
            MemberShare(
                user_id=uid,
                full_name=name,
                selected_item_ids=sorted(chosen_by.get(uid, [])),
                item_amount=share.item_amount,
                fee_amount=share.fee_amount,
                total=share.final_amount,
            )
        )
    return SelectionSummary(
        receipt_id=receipt.id,
        receipt_status=receipt.status,
        can_select=not state.is_settled(receipt),
        items_total=sum((i.line_total for i in items), ZERO),
        fee_total=_fee_total(receipt),
        discount_amount=_discount_amount(receipt),
        my_selected_item_ids=sorted(chosen_by.get(user.id, [])),
        members=member_rows,
        unselected_items=[
            UnselectedItem(id=i.id, item_name=i.item_name, quantity=i.quantity, line_total=i.line_total)
            for i in items
            if i.id not in selectors
        ],
    )


def _load_for_selection(
    db: Session, user: User, receipt_id: int, item_id: int, target_user_id: int | None
) -> tuple[Receipt, int]:
    receipt, member = _load_group_receipt(db, user, receipt_id, lock=True)
    state.require_not_settled(receipt)  # 409 RECEIPT_SETTLED
    item = db.scalar(select(ReceiptItem).where(ReceiptItem.id == item_id, ReceiptItem.receipt_id == receipt.id))
    if item is None:
        raise NotFound("Không tìm thấy dòng món")
    if target_user_id is None or target_user_id == user.id:
        return receipt, user.id

    require_leader(member)
    target_is_active = db.scalar(
        select(GroupMember.user_id).where(
            GroupMember.group_id == receipt.group_id,
            GroupMember.user_id == target_user_id,
            GroupMember.status == "ACTIVE",
        )
    )
    if target_is_active is None:
        raise Forbidden("Chỉ có thể chia món cho thành viên đang hoạt động trong nhóm")
    return receipt, target_user_id


def select_item(
    db: Session, user: User, receipt_id: int, item_id: int, target_user_id: int | None = None
) -> SelectionSummary:
    """Chọn món cho mình; LEADER có thể chọn thay thành viên ACTIVE. Idempotent."""
    receipt, selected_user_id = _load_for_selection(db, user, receipt_id, item_id, target_user_id)
    if db.get(ItemSelection, (item_id, selected_user_id)) is None:
        db.add(ItemSelection(item_id=item_id, user_id=selected_user_id))
    db.commit()
    return _summary(db, receipt, user)


def deselect_item(
    db: Session, user: User, receipt_id: int, item_id: int, target_user_id: int | None = None
) -> SelectionSummary:
    """Bỏ chọn món của mình; LEADER có thể bỏ chọn thay thành viên ACTIVE. Idempotent."""
    receipt, selected_user_id = _load_for_selection(db, user, receipt_id, item_id, target_user_id)
    db.execute(delete(ItemSelection).where(ItemSelection.item_id == item_id, ItemSelection.user_id == selected_user_id))
    db.commit()
    return _summary(db, receipt, user)


# ---------- 2. Chốt hóa đơn: tính chia + ghi split_details + debts (1 transaction) ----------
def finalize_receipt(db: Session, user: User, receipt_id: int) -> SplitResult:
    receipt, member = _load_group_receipt(db, user, receipt_id, lock=True)
    require_leader(member)  # 403

    if receipt.status != state.VERIFIED:
        db.rollback()
        if state.is_settled(receipt):
            raise Conflict("Hóa đơn đã được chốt", code=state.ERR_SETTLED)
        raise Conflict("Hóa đơn phải được xác nhận (VERIFIED) trước khi chốt", code=state.ERR_BAD_TRANSITION)

    items = _items(db, receipt.id)
    members = _active_members(db, receipt.group_id)
    active_ids = {uid for uid, _ in members}
    selectors = _selectors(db, receipt.id, active_ids)

    errors: list[dict] = []
    if receipt.payer_id is None or receipt.payer_id not in active_ids:
        errors.append({"field": "payer_id", "message": "Người trả tiền chưa có hoặc không còn là thành viên đang hoạt động"})
    if not items:
        errors.append({"field": "items", "message": "Hóa đơn chưa có dòng món nào"})
    for i in items:
        if i.id not in selectors:
            errors.append({"field": "items", "message": f"Món '{i.item_name}' (id {i.id}) chưa có ai chọn"})

    items_sum = sum((i.line_total for i in items), ZERO)
    discount = _discount_amount(receipt)
    expected_total = items_sum + _fee_total(receipt) - discount
    if receipt.subtotal != items_sum:
        errors.append({"field": "subtotal", "message": f"subtotal ({receipt.subtotal}) ≠ tổng các dòng món ({items_sum})"})
    if receipt.total_amount is None or receipt.total_amount != expected_total:
        errors.append(
            {
                "field": "total_amount",
                "message": f"total_amount ({receipt.total_amount}) ≠ tổng món + thuế + phí - giảm giá ({expected_total})",
            }
        )
    elif receipt.total_amount <= 0:
        errors.append({"field": "total_amount", "message": "Hóa đơn có tổng tiền 0, không có gì để chia"})

    paid = db.scalar(select(Debt.id).where(Debt.receipt_id == receipt.id, Debt.status == "PAID").limit(1))
    if paid is not None:
        raise Conflict("Hóa đơn đã có khoản nợ được thanh toán", code=state.ERR_HAS_PAID_DEBT)
    if errors:
        db.rollback()  # nhả khóa dòng; chưa ghi gì nên hóa đơn vẫn VERIFIED
        raise Unprocessable("Chưa thể chốt hóa đơn", details=errors)

    payer_id = receipt.payer_id
    shares = calc.assign_remainder(
        calc.compute_shares({i.id: i.line_total for i in items}, selectors, _fee_total(receipt), discount),
        payer_id,
        receipt.total_amount,
    )

    # Mọi thứ dưới đây trong CÙNG 1 transaction (1 commit); lỗi bất kỳ → rollback, vẫn VERIFIED, không có nợ nửa vời
    try:
        db.execute(delete(Debt).where(Debt.receipt_id == receipt.id))
        db.execute(delete(SplitDetail).where(SplitDetail.receipt_id == receipt.id))
        for uid, share in sorted(shares.items()):
            db.add(
                SplitDetail(
                    receipt_id=receipt.id,
                    user_id=uid,
                    item_amount=share.item_amount,
                    fee_amount=share.fee_amount,
                    final_amount=share.final_amount,
                )
            )
            if uid != payer_id and share.final_amount > 0:  # chỉ debtor ≠ payer và amount > 0
                db.add(
                    Debt(
                        receipt_id=receipt.id,
                        debtor_id=uid,
                        creditor_id=payer_id,
                        amount=share.final_amount,
                        status="OPEN",
                    )
                )
        state.transition(receipt, state.SETTLED)
        db.commit()
    except Exception:
        db.rollback()
        raise

    names = dict(members)
    debts = _query_debts(db, Debt.receipt_id == receipt.id)
    return SplitResult(
        receipt_id=receipt.id,
        status=receipt.status,
        payer_id=payer_id,
        total_amount=receipt.total_amount,
        splits=[
            SplitLine(
                user_id=uid,
                full_name=names.get(uid, ""),
                item_amount=s.item_amount,
                fee_amount=s.fee_amount,
                final_amount=s.final_amount,
            )
            for uid, s in sorted(shares.items())
        ],
        debts=debts,
    )


# ---------- 3. Xem công nợ theo hóa đơn / theo nhóm ----------
def _query_debts(db: Session, *where, user_id: int | None = None, status: str | None = None) -> list[DebtOut]:
    debtor, creditor = aliased(User), aliased(User)
    stmt = (
        select(Debt, Receipt.group_id, Receipt.merchant_name, debtor.full_name, creditor.full_name)
        .join(Receipt, Receipt.id == Debt.receipt_id)
        .join(debtor, debtor.id == Debt.debtor_id)
        .join(creditor, creditor.id == Debt.creditor_id)
        .where(*where)
        .order_by(Debt.receipt_id.desc(), Debt.id)
    )
    if status is not None:
        stmt = stmt.where(Debt.status == status)
    if user_id is not None:  # chỉ khoản liên quan tới user (đang nợ hoặc đang được nhận)
        stmt = stmt.where((Debt.debtor_id == user_id) | (Debt.creditor_id == user_id))
    return [
        DebtOut(
            id=d.id,
            receipt_id=d.receipt_id,
            group_id=group_id,
            merchant_name=merchant,
            debtor_id=d.debtor_id,
            debtor_name=debtor_name,
            creditor_id=d.creditor_id,
            creditor_name=creditor_name,
            amount=d.amount,
            status=d.status,
        )
        for d, group_id, merchant, debtor_name, creditor_name in db.execute(stmt).all()
    ]


def _debt_list(items: list[DebtOut]) -> DebtList:
    return DebtList(
        items=items,
        total_open=sum((d.amount for d in items if d.status == "OPEN"), ZERO),
        total_paid=sum((d.amount for d in items if d.status == "PAID"), ZERO),
    )


def receipt_debts(
    db: Session, user: User, receipt_id: int, *, status: Literal["OPEN", "PAID"] | None = None, mine: bool = False
) -> DebtList:
    """Công nợ của 1 hóa đơn. Hóa đơn nhóm: thành viên ACTIVE; hóa đơn cá nhân: chủ sở hữu (luôn rỗng)."""
    receipt, _ = _load(db, user, receipt_id)  # 404 / 403
    items = _query_debts(
        db, Debt.receipt_id == receipt.id, user_id=user.id if mine else None, status=status
    )
    return _debt_list(items)


def group_debts(
    db: Session, user: User, group_id: int, *, status: Literal["OPEN", "PAID"] | None = None, mine: bool = False
) -> DebtList:
    """Công nợ của mọi hóa đơn trong nhóm. Chỉ thành viên ACTIVE của nhóm đó xem được (404 / 403)."""
    get_group_membership(db, group_id, user.id)
    items = _query_debts(db, Receipt.group_id == group_id, user_id=user.id if mine else None, status=status)
    return _debt_list(items)


def pay_debt(db: Session, user: User, debt_id: int) -> DebtOut:
    """Xác nhận khoản nợ đã được trả; chỉ chủ nợ hoặc LEADER ACTIVE của nhóm được phép."""
    debt = db.scalar(select(Debt).where(Debt.id == debt_id).with_for_update())
    if debt is None:
        raise NotFound("Không tìm thấy khoản nợ")

    receipt = db.get(Receipt, debt.receipt_id)
    if user.id != debt.creditor_id:
        member = (
            db.scalar(
                select(GroupMember).where(
                    GroupMember.group_id == receipt.group_id,
                    GroupMember.user_id == user.id,
                    GroupMember.role == "LEADER",
                    GroupMember.status == "ACTIVE",
                )
            )
            if receipt.group_id is not None
            else None
        )
        if member is None:
            db.rollback()
            raise Forbidden("Chỉ chủ nợ hoặc trưởng nhóm đang hoạt động mới được xác nhận đã nhận tiền")

    if debt.status == "PAID":
        db.rollback()
        raise Conflict("Khoản nợ đã được thanh toán", code="DEBT_ALREADY_PAID")

    debt.status = "PAID"
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return _query_debts(db, Debt.id == debt_id)[0]
