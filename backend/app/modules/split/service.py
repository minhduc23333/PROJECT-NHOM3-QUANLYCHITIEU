"""Module chia tiền: từ ItemSelection -> SplitDetail -> Debt.

TODO:
- calculate(receipt_id): item_amount theo món đã chọn, fee_amount chia thuế/phí theo tỉ lệ,
  làm tròn VND (đơn vị đồng), phần lẻ dồn cho người trả.
- tạo Debt (debtor -> creditor = payer) với status OPEN.
"""