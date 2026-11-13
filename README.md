# SmartSplit AI

Ứng dụng chia hóa đơn nhóm: tạo nhóm → upload hóa đơn → mỗi người chọn món → tự tính tiền và công nợ.

## Chạy dự án

```bash
# 1. Database (MySQL 8)
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt   # OCR cần Tesseract + gói 'vie' (Linux: apt install tesseract-ocr tesseract-ocr-vie)
cp .env.example .env        # rồi ĐỔI JWT_SECRET (>= 32 ký tự):
                            # python -c "import secrets; print(secrets.token_urlsafe(48))"
alembic upgrade head        # tạo bảng
python -m scripts.seed      # (tùy chọn) 3 user demo + 1 nhóm, mật khẩu 123456
uvicorn app.main:app --reload --port 8000
```

Mở http://localhost:8000 (frontend được backend phục vụ luôn; các trang như `/login` và `/groups` cũng mở trực tiếp được), tài liệu API tại http://localhost:8000/docs.
Frontend không cần cài gì thêm: Bootstrap/Chart.js nằm sẵn trong `frontend/vendor/`.

## Test

```bash
cd backend && pytest
```

## API hiện có

| Method | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/api/health` | Kiểm tra server và DB (`/health` cũng được hỗ trợ) |
| POST | `/api/auth/register` | Đăng ký (`full_name`, `email`, `password` ≥ 8 ký tự). Trả 201 + token. Email trùng → 409 |
| POST | `/api/auth/login` | Đăng nhập (`email`, `password`). Trả token |
| GET | `/api/auth/me` | Thông tin người dùng hiện tại (header `Authorization: Bearer <token>`) |

| GET | `/api/groups/{id}/receipts` | Danh sách hóa đơn của nhóm |
| POST | `/api/groups/{id}/receipts` | Tải ảnh JPG/PNG (≤ 5 MB, kiểm tra magic bytes, không tin MIME client; người tải phải là thành viên ACTIVE) → bản nháp `DRAFT`, `ocr_status=PENDING`. Sai định dạng → 400, quá cỡ → 413 |
| POST | `/api/receipts/personal` | Như trên nhưng hóa đơn cá nhân (không cần nhóm) |
| POST | `/api/ocr/receipts/{id}` | Chạy OCR + parser, điền merchant/ngày/tiền + dòng món. OCR lỗi vẫn trả 200 với `ocr_status=FAILED` để nhập tay. Chỉ người tải lên |
| GET | `/api/receipts/{id}` | Xem bản nháp + dòng món + `items_total` + cờ `can_edit_*` |
| PATCH | `/api/receipts/{id}` | Sửa đầu hóa đơn (chỉ người tải lên). Đổi tiền khi `VERIFIED` → tự về `DRAFT`; `SETTLED` → 409 |
| POST / PATCH / DELETE | `/api/receipts/{id}/items[/{item_id}]` | CRUD dòng món (người tải lên hoặc Leader). Khi `VERIFIED` → tự về `DRAFT`; `SETTLED` → 409; `line_total` tự tính = SL × đơn giá |
| POST | `/api/receipts/{id}/verify` | Body `{payer_id}`. Tổng tiền khớp → `VERIFIED`; sai → 422 kèm danh sách lỗi |
| POST | `/api/receipts/{id}/settle` | `VERIFIED` → `SETTLED` (người tải lên hoặc Leader) |

Luồng: `DRAFT` → verify → `VERIFIED` → settle → `SETTLED` (logic ở `backend/app/modules/receipts/state.py`).

- Sửa dữ liệu ảnh hưởng chia tiền (dòng món, `subtotal`, `tax_amount`, `service_fee`, `total_amount`) khi `VERIFIED` → quay về `DRAFT` và xóa kết quả chia cũ (`split_details`, nợ `OPEN`). Đã có nợ `PAID` thì chặn sửa (409 `RECEIPT_HAS_PAID_DEBT`). Sửa tên quán/ngày/danh mục thì giữ nguyên `VERIFIED`.
- `SETTLED` khóa mọi thao tác sửa (409, `code = RECEIPT_SETTLED`). Nhảy cóc / xác nhận lại sai trạng thái → 409 `INVALID_STATUS_TRANSITION`.
- `GET /api/receipts/{id}` trả thêm `is_locked`, `can_verify`, `can_settle` cho UI.

Lỗi luôn có dạng `{"error": {"code", "message", "details"}}`.

## Quy ước Git
- **Nhánh chính:** `main` (chỉ merge khi code đã chạy ổn).
- **Tạo nhánh mới:** `feature/<tên-chức-năng>` (VD: `feature/api-login`).

## Quy ước Commit
- `Sprint: [Mô tả]` - Thêm chức năng mới.
- `fix: [Mô tả]` - Sửa lỗi bug.
- `docs: [Mô tả]` - Viết hoặc sửa tài liệu.
