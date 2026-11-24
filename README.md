# SmartSplit AI

Ứng dụng quản lý chi tiêu và **chia hóa đơn nhóm**: tạo nhóm → tải ảnh hóa đơn → OCR tự đọc món và số tiền → mỗi người chọn món của mình → hệ thống tự tính tiền và công nợ.

> Đồ án nhóm 3 – Quản lý chi tiêu.

## Mục lục

- [Tính năng](#tính-năng)
- [Công nghệ](#công-nghệ)
- [Cấu trúc thư mục](#cấu-trúc-thư-mục)
- [Cài đặt và chạy](#cài-đặt-và-chạy)
- [Biến môi trường](#biến-môi-trường)
- [Luồng nghiệp vụ](#luồng-nghiệp-vụ)
- [Quy tắc chia tiền](#quy-tắc-chia-tiền)
- [API](#api)
- [Test](#test)
- [Quy ước làm việc](#quy-ước-làm-việc)

## Tính năng

- **Tài khoản:** đăng ký, đăng nhập (JWT), quên / đặt lại mật khẩu qua email.
- **Nhóm:** tạo nhóm (người tạo là `LEADER`), thêm thành viên bằng email.
- **Hóa đơn:** tải ảnh JPG/PNG cho nhóm hoặc hóa đơn cá nhân, xem lại ảnh gốc để đối chiếu, sửa đầu hóa đơn và từng dòng món.
- **OCR:** đọc hóa đơn bằng Tesseract (mặc định), EasyOCR hoặc Gemini Vision. OCR lỗi vẫn cho nhập tay.
- **Phân loại:** danh mục cố định (Ăn uống, Di chuyển, Mua sắm, Khác), gợi ý theo tên cửa hàng.
- **Chia tiền:** mỗi người chọn món, thuế/phí chia theo tỉ lệ, Leader chốt và hệ thống ghi công nợ.
- **Công nợ:** xem theo hóa đơn hoặc theo nhóm, xác nhận đã thanh toán.
- **Dashboard:** tổng chi tiêu, số tiền nợ / được nợ, biểu đồ theo tháng và theo danh mục.

## Công nghệ

| Thành phần | Công nghệ |
|---|---|
| Backend | Python 3.11, FastAPI, SQLAlchemy 2, Alembic |
| Cơ sở dữ liệu | MySQL 8 (Docker) |
| Xác thực | JWT (PyJWT), mật khẩu băm bằng bcrypt |
| OCR | OpenCV + Tesseract (`vie+eng`), tùy chọn EasyOCR / Gemini |
| Frontend | HTML, JavaScript thuần (ES modules), Bootstrap, Chart.js – không cần build |
| Test | pytest (backend), `node --test` (component frontend) |

## Cấu trúc thư mục

```text
.
├── docker-compose.yml          # MySQL 8
├── backend/
│   ├── app/
│   │   ├── main.py             # Khởi tạo FastAPI, phục vụ luôn frontend
│   │   ├── core/               # config, db, bảo mật, lỗi, gửi mail
│   │   ├── models/             # User, Group, Receipt, Split...
│   │   └── modules/            # auth, groups, receipts, ocr, split, dashboard
│   ├── alembic/                # Migration
│   ├── scripts/seed.py         # Dữ liệu demo
│   ├── tests/
│   ├── Dockerfile
│   └── .env.example
└── frontend/
    ├── index.html
    ├── css/
    ├── js/                     # pages/, components/, router, api...
    ├── vendor/                 # Bootstrap, Chart.js (có sẵn, không cần cài)
    └── COMPONENTS.md           # Tài liệu component dùng chung
```

## Cài đặt và chạy

**Yêu cầu:** Python 3.11+, Docker, Tesseract OCR (nếu dùng OCR cục bộ).

```bash
# 1. Cơ sở dữ liệu (MySQL 8)
docker compose up -d

# 2. Backend
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Cấu hình
cp .env.example .env
# Mở .env và ĐỔI JWT_SECRET (>= 32 ký tự). Sinh nhanh bằng:
python -c "import secrets; print(secrets.token_urlsafe(48))"

# 4. Tạo bảng
alembic upgrade head

# 5. (Tùy chọn) Dữ liệu demo: 3 người dùng + 1 nhóm
python -m scripts.seed

# 6. Chạy server
uvicorn app.main:app --reload --port 8000
```

Sau đó mở:

- Ứng dụng: http://localhost:8000 (backend phục vụ luôn frontend; `/login`, `/groups`... mở trực tiếp được)
- Tài liệu API (Swagger): http://localhost:8000/docs

**Tài khoản demo** (sau khi chạy seed, mật khẩu `123456`): `an@demo.vn` (Leader), `binh@demo.vn`, `chi@demo.vn`.

**Ghi chú:**

- Nếu bỏ qua bước `alembic upgrade head`, ở môi trường dev backend sẽ tự migrate khi khởi động với DB còn trống (`AUTO_MIGRATE=true`).
- **Cài Tesseract:** Linux `sudo apt install tesseract-ocr tesseract-ocr-vie`; Windows tải bản cài đặt rồi đặt `TESSERACT_CMD` trong `.env` nếu không nằm trong `PATH`.
- Có thể chạy backend bằng Docker bằng `backend/Dockerfile` (đã cài sẵn Tesseract và gói tiếng Việt).

## Biến môi trường

Cấu hình trong `backend/.env` (mẫu ở `backend/.env.example`).

| Biến | Mặc định | Mô tả |
|---|---|---|
| `DATABASE_URL` | MySQL local | Chuỗi kết nối DB |
| `JWT_SECRET` | – | **Bắt buộc đổi**. `APP_ENV=prod` sẽ báo lỗi nếu < 32 ký tự |
| `APP_ENV` | `dev` | `dev` hoặc `prod` |
| `CORS_ORIGINS` | `http://localhost:8000` | Danh sách origin, cách nhau bằng dấu phẩy |
| `AUTO_MIGRATE` | `true` | Tự chạy migration khi DB còn trống |
| `MAX_UPLOAD_MB` | `5` | Dung lượng ảnh tối đa |
| `OCR_ENGINE` | `auto` | `auto` / `tesseract` / `easyocr` / `gemini` |
| `OCR_LANG` | `vie+eng` | Ngôn ngữ Tesseract |
| `OCR_TIMEOUT_SEC` | `60` | Thời gian tối đa cho một lần OCR |
| `TESSERACT_CMD` | trống | Đường dẫn `tesseract` nếu không nằm trong `PATH` |
| `GEMINI_API_KEY` | trống | Có khóa thì `OCR_ENGINE=auto` sẽ ưu tiên Gemini |
| `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS` | xem `config.py` | Model chính và danh sách dự phòng |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Địa chỉ web để tạo liên kết trong email |
| `PASSWORD_RESET_EXPIRE_MINUTES` | `30` | Hạn của liên kết đặt lại mật khẩu |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | trống | Gửi email thật. Để trống `SMTP_HOST` thì liên kết đặt lại chỉ hiện ở terminal backend / giao diện (chế độ dev) |

> Dùng Gmail: bật xác minh 2 bước rồi tạo **Mật khẩu ứng dụng** (App password) làm `SMTP_PASSWORD`.
>
> Muốn dùng EasyOCR: bỏ comment `easyocr` trong `requirements.txt` (nặng, kéo theo torch) và đặt `OCR_ENGINE=easyocr`.

## Luồng nghiệp vụ

```text
DRAFT ──verify──▶ VERIFIED ──split / settle──▶ SETTLED
```

1. Thành viên tải ảnh → hóa đơn `DRAFT`, `ocr_status=PENDING`.
2. Chạy OCR, kiểm tra và sửa kết quả, chọn người trả tiền, **verify** (tổng tiền phải khớp).
3. Các thành viên chọn món của mình (Leader có thể chọn thay).
4. **Leader chốt** bằng `/split`: ghi chi tiết chia tiền, tạo công nợ và chuyển `SETTLED` trong một transaction.
5. Chủ nợ hoặc Leader xác nhận từng khoản nợ đã trả.

Quy tắc trạng thái (logic ở `backend/app/modules/receipts/state.py`):

- Sửa dữ liệu ảnh hưởng chia tiền (dòng món, `subtotal`, `tax_amount`, `service_fee`, `total_amount`) khi `VERIFIED` → quay về `DRAFT` và xóa kết quả chia cũ (`split_details`, nợ `OPEN`). Đã có nợ `PAID` thì chặn sửa (409 `RECEIPT_HAS_PAID_DEBT`).
- Sửa tên quán, ngày, danh mục thì giữ nguyên `VERIFIED`.
- `SETTLED` khóa mọi thao tác sửa (409 `RECEIPT_SETTLED`).
- Nhảy cóc hoặc xác nhận sai trạng thái → 409 `INVALID_STATUS_TRANSITION`.
- `POST /api/receipts/{id}/settle` chỉ đổi trạng thái, **không** chia tiền. Muốn có công nợ hãy dùng `/split`.

## Quy tắc chia tiền

Code ở `backend/app/modules/split/calc.py`.

- Món có *k* người chọn thì chia đều cho *k* người.
- Thuế và phí dịch vụ chia theo tỉ lệ phần món của mỗi người.
- Mỗi người làm tròn **xuống** tới đồng; phần lẻ dồn cho **người trả tiền** (cộng vào `fee_amount`), nên `Σ final_amount = total_amount`.
- Công nợ: `debtor` (người phải trả) → `creditor` (người trả hóa đơn). Chỉ tạo nợ cho người khác người trả và có số tiền > 0.
- Lựa chọn của thành viên đã bị gỡ khỏi nhóm sẽ bị bỏ qua.

## API

Tiền tố `/api`. Xem đầy đủ và thử trực tiếp tại `/docs`. Các endpoint (trừ `health`, `register`, `login`, `forgot-password`, `reset-password`) cần header `Authorization: Bearer <token>`.

Lỗi luôn có dạng: `{"error": {"code", "message", "details"}}`.

### Hệ thống và xác thực

| Method | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/api/health` | Kiểm tra server và DB (`/health` cũng được) |
| POST | `/api/auth/register` | Đăng ký (`full_name`, `email`, `password` 6–72 ký tự). 201 + token; email trùng → 409 |
| POST | `/api/auth/login` | Đăng nhập, nhận token |
| GET | `/api/auth/me` | Thông tin người dùng hiện tại |
| POST | `/api/auth/forgot-password` | Gửi liên kết đặt lại mật khẩu. Luôn trả cùng một thông báo; tối đa 5 yêu cầu / email / 15 phút (429) |
| POST | `/api/auth/reset-password` | Đặt mật khẩu mới bằng token. Token sai / hết hạn / đã dùng → 400 `RESET_TOKEN_INVALID` |

### Nhóm

| Method | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/api/groups` | Danh sách nhóm của tôi |
| POST | `/api/groups` | Tạo nhóm (người tạo là LEADER) |
| GET | `/api/groups/{id}` | Chi tiết nhóm + thành viên |
| GET | `/api/groups/{id}/members` | Danh sách thành viên |
| POST | `/api/groups/{id}/members` | Thêm thành viên bằng email (chỉ LEADER) |

### Hóa đơn và OCR

| Method | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/api/groups/{id}/receipts` | Hóa đơn của nhóm |
| POST | `/api/groups/{id}/receipts` | Tải ảnh JPG/PNG (≤ 5 MB, kiểm tra magic bytes, không tin MIME từ client; người tải phải là thành viên ACTIVE) → `DRAFT`. Sai định dạng → 400, quá cỡ → 413 |
| POST | `/api/receipts/personal` | Như trên nhưng là hóa đơn cá nhân (không cần nhóm, chỉ chủ tài khoản xem được) |
| GET | `/api/receipts/category-suggestion` | Gợi ý danh mục theo `merchant_name` (không khớp → "Khác") |
| POST | `/api/ocr/receipts/{id}` | Chạy OCR, điền cửa hàng / ngày / tiền + dòng món. OCR lỗi vẫn trả 200 với `ocr_status=FAILED` để nhập tay. Chỉ người tải lên |
| GET | `/api/receipts/{id}` | Xem hóa đơn + dòng món + `items_total` + các cờ `can_edit_*`, `is_locked`, `can_verify`, `can_settle` |
| GET | `/api/receipts/{id}/image` | Ảnh gốc để đối chiếu kết quả OCR |
| PATCH | `/api/receipts/{id}` | Sửa đầu hóa đơn (chỉ người tải lên) |
| DELETE | `/api/receipts/{id}` | Xóa hóa đơn và dữ liệu chia tiền liên quan |
| POST | `/api/receipts/{id}/items` | Thêm dòng món (người tải lên hoặc Leader) |
| PATCH / DELETE | `/api/receipts/{id}/items/{item_id}` | Sửa / xóa dòng món. `line_total` tự tính = SL × đơn giá |
| POST | `/api/receipts/{id}/verify` | Body `{payer_id}`. Tổng tiền khớp → `VERIFIED`; sai → 422 kèm danh sách lỗi |
| POST | `/api/receipts/{id}/settle` | `VERIFIED` → `SETTLED` (người tải lên hoặc Leader), không tạo công nợ |

### Chọn món, chia tiền, công nợ

| Method | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/api/receipts/{id}/selections` | Ai chọn món nào: tạm tính từng người (món + thuế/phí theo tỉ lệ) và các món chưa ai chọn |
| PUT | `/api/receipts/{id}/items/{item_id}/selection` | Chọn món cho chính mình. Leader có thể truyền `?user_id=` để chọn thay thành viên ACTIVE. Idempotent; dùng khi `DRAFT` / `VERIFIED`, `SETTLED` → 409 |
| DELETE | `/api/receipts/{id}/items/{item_id}/selection` | Bỏ chọn (tương tự trên) |
| POST | `/api/receipts/{id}/split` | **Chỉ Leader** chốt: cần `VERIFIED`, không còn món chưa ai chọn, tổng tiền khớp (không thì 422 kèm `details`) |
| GET | `/api/receipts/{id}/debts` | Công nợ của một hóa đơn (`?status=OPEN\|PAID`, `?mine=true`) |
| GET | `/api/groups/{id}/debts` | Công nợ của cả nhóm, cùng bộ lọc. Chỉ thành viên ACTIVE (người ngoài → 403) |
| PATCH | `/api/debts/{id}/pay` | Xác nhận khoản nợ đã trả. Chỉ chủ nợ hoặc Leader; đã `PAID` → 409 `DEBT_ALREADY_PAID` |

### Dashboard

| Method | Đường dẫn | Mô tả |
|---|---|---|
| GET | `/api/dashboard/summary` | Số liệu tổng quan (chỉ tính hóa đơn `SETTLED`): số nhóm, số hóa đơn, chi tiêu cá nhân / nhóm, đang nợ / được nợ, chi tiêu 6 tháng gần nhất, theo danh mục, 5 hóa đơn gần nhất |

## Test

```bash
# Backend
cd backend && pytest

# Frontend (component dùng chung)
cd frontend && npm test
```

Lint backend bằng `ruff` (đã có trong `requirements.txt`): `cd backend && ruff check .`

## Quy ước làm việc

**Git**

- Nhánh chính: `main` (chỉ merge khi code đã chạy ổn).
- Nhánh mới: `feature/<tên-chức-năng>` (ví dụ `feature/api-login`).

**Commit**

- `Sprint: [Mô tả]` – thêm chức năng mới.
- `fix: [Mô tả]` – sửa lỗi.
- `docs: [Mô tả]` – viết hoặc sửa tài liệu.
