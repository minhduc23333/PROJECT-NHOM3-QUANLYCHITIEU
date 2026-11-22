import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]


def apply_change(rel_path: str, old: str, new: str):
    p = PROJECT_ROOT / rel_path
    text = p.read_text(encoding='utf-8')
    if new in text:
        print(f'[SKIP] {rel_path}: already updated')
        return
    if old in text:
        p.write_text(text.replace(old, new, 1), encoding='utf-8', newline='')
        print(f'[OK] Updated {rel_path}')
        return
    norm = text.replace('\r\n', '\n')
    if old in norm:
        updated = norm.replace(old, new, 1)
        if '\r\n' in text:
            updated = updated.replace('\n', '\r\n')
        p.write_text(updated, encoding='utf-8', newline='')
        print(f'[OK] Updated {rel_path} (CRLF)')
        return
    raise RuntimeError(f'[ERR] Matching block not found in {rel_path}')

apply_change('backend/app/modules/ocr/gemini_ocr.py', '8. total_amount: Tổng tiền THỰC TRẢ cuối cùng (sau thuế, phí và đã trừ giảm giá/làm tròn) bằng VND.\n   - Nếu hóa đơn có SubTotal/Total trước thuế (VD: 834,000), VAT 8% (66,720) và Payment Amount (900,720): thì subtotal=834000, tax_amount=66720, discount_amount=null, total_amount=900720.\n   - Nếu hóa đơn có cả dòng "Tổng tiền hàng: 242,641" và "Thanh toán (Đã làm tròn): 242,000": lấy total_amount=242000 (số thực trả), subtotal=242641 và discount_amount=641.', '8. total_amount: Tổng tiền THỰC TRẢ cuối cùng (sau thuế, phí và đã trừ giảm giá/làm tròn) bằng VND.\n   - Nếu hóa đơn có SubTotal/Total trước thuế (VD: 834,000), VAT 8% (66,720) và Payment Amount (900,720): thì subtotal=834000, tax_amount=66720, discount_amount=null, total_amount=900720.\n   - Nếu hóa đơn có cả dòng "Tổng tiền hàng: 242,641" và "Thanh toán (Đã làm tròn): 242,000": lấy total_amount=242000 (số thực trả), subtotal=242641 và discount_amount=641.\n   - Nếu hóa đơn có tạm tính trước thuế (VD: 160,909) + thuế VAT (VD: 13,091) nhưng tổng thanh toán cuối cùng (VD: 174,000) bằng đúng tổng các món (VD: 159,000 + 15,000 = 174,000) vì giá món đã bao gồm thuế: đặt subtotal = tổng các món (174000), tax_amount = 0, và total_amount = tổng thực trả cuối cùng (174000).')
apply_change('backend/app/modules/ocr/gemini_ocr.py', '    if fee is not None and 0 < fee < Decimal(100):\n        base = subtotal if subtotal is not None else items_sum\n        if total is None or abs((base + (tax or 0) + fee) - total) >= abs((base + (tax or 0)) - total):\n            fee = None\n\n    parsed = ParsedReceipt(', '    if fee is not None and 0 < fee < Decimal(100):\n        base = subtotal if subtotal is not None else items_sum\n        if total is None or abs((base + (tax or 0) + fee) - total) >= abs((base + (tax or 0)) - total):\n            fee = None\n\n    # Hóa đơn đã gộp VAT vào giá món (VD: tổng món 174.000 = tổng trả 174.000, nhưng bill có in tạm tính trước thuế + VAT)\n    if items and total is not None and subtotal is not None and (tax or 0) > 0:\n        fees_with_tax = (tax or Decimal(0)) + (fee or Decimal(0))\n        disc = discount or Decimal(0)\n        if (\n            abs(items_sum - total) <= ROUNDING_TOLERANCE\n            and abs(subtotal + fees_with_tax - disc - total) <= ROUNDING_TOLERANCE\n            and items_sum > subtotal\n        ):\n            subtotal = items_sum\n            tax = Decimal(0)\n\n    # Nếu không có subtotal nhưng có items + total + fees/discount khớp trong ngưỡng làm tròn, điền subtotal = items_sum\n    if items and total is not None and subtotal is None:\n        fees = (tax or Decimal(0)) + (fee or Decimal(0))\n        disc = discount or Decimal(0)\n        if abs(items_sum + fees - disc - total) <= ROUNDING_TOLERANCE:\n            subtotal = items_sum\n\n    parsed = ParsedReceipt(')
apply_change('backend/app/modules/ocr/service.py', '    if parsed.items and parsed.total_amount is not None:\n        items_sum = sum((i.line_total for i in parsed.items), Decimal(0))\n        fees = (parsed.tax_amount or Decimal(0)) + (parsed.service_fee or Decimal(0))\n        implied_discount = items_sum + fees - parsed.total_amount', '    if parsed.items and parsed.total_amount is not None:\n        items_sum = sum((i.line_total for i in parsed.items), Decimal(0))\n        fees = (parsed.tax_amount or Decimal(0)) + (parsed.service_fee or Decimal(0))\n        if parsed.subtotal is not None and (parsed.tax_amount or 0) > 0:\n            disc = parsed.discount_amount or Decimal(0)\n            if (\n                abs(items_sum - parsed.total_amount) <= Decimal(1000)\n                and abs(parsed.subtotal + fees - disc - parsed.total_amount) <= Decimal(1000)\n                and items_sum > parsed.subtotal\n            ):\n                parsed.subtotal = items_sum\n                parsed.tax_amount = Decimal(0)\n                fees = parsed.service_fee or Decimal(0)\n                parsed.warnings = [\n                    w for w in parsed.warnings if "khác tạm tính" not in w and "khác tổng thanh toán" not in w\n                ]\n        implied_discount = items_sum + fees - parsed.total_amount')
print('\nOCR monetary fix completed!')
