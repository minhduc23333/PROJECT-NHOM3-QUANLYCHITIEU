# SmartSplit AI

Ứng dụng chia hóa đơn nhóm: tạo nhóm → upload hóa đơn → mỗi người chọn món → tự tính tiền và công nợ.

## Chạy dự án

```bash
# 1. Database (MySQL 8)
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # rồi ĐỔI JWT_SECRET (>= 32 ký tự):
                            # python -c "import secrets; print(secrets.token_urlsafe(48))"
alembic upgrade head        # tạo bảng
python -m scripts.seed      # (tùy chọn) 3 user demo + 1 nhóm, mật khẩu 123456
uvicorn app.main:app --reload --port 8000
```

Mở http://localhost:8000 (frontend được backend phục vụ luôn), tài liệu API tại http://localhost:8000/docs.
Frontend không cần cài gì thêm: Bootstrap/Chart.js nằm sẵn trong `frontend/vendor/`.

## Test

```bash
cd backend && pytest
```

## API hiện có

| Method | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/health` | Kiểm tra server và DB |
| POST | `/auth/register` | Đăng ký (`full_name`, `email`, `password` ≥ 8 ký tự). Trả 201 + token. Email trùng → 409 |
| POST | `/auth/login` | Đăng nhập (`email`, `password`). Trả token |
| GET | `/auth/me` | Thông tin người dùng hiện tại (header `Authorization: Bearer <token>`) |

Lỗi luôn có dạng `{"error": {"code", "message", "details"}}`.

## Quy ước Git
- **Nhánh chính:** `main` (chỉ merge khi code đã chạy ổn).
- **Tạo nhánh mới:** `feature/<tên-chức-năng>` (VD: `feature/api-login`).

## Quy ước Commit
- `Sprint: [Mô tả]` - Thêm chức năng mới.
- `fix: [Mô tả]` - Sửa lỗi bug.
- `docs: [Mô tả]` - Viết hoặc sửa tài liệu.
