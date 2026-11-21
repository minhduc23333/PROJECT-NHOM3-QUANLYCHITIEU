# Component dùng chung & trạng thái UI (T05E166)

Mọi trang import từ `js/ui.js`. Code nằm trong `js/components/`, kiểu dáng trong `css/components.css`.
Xem và bấm thử tất cả tại **http://localhost:8000/#/dev/ui** (cần đăng nhập).

```js
import { renderState, toast, field, moneyField, bindMoneyInputs, dataTable, confirmDialog } from "../ui.js";
import { formatVND } from "../format.js";
```

## 1. Trạng thái UI

| Trạng thái | Hàm | Ghi chú |
|---|---|---|
| Đang tải | `loadingHTML(text?)`, `skeletonHTML(rows?)` | Spinner hoặc khung xương |
| Dữ liệu trống | `emptyHTML(text, { actionText, actionHref }?)` | Có thể kèm nút, ví dụ "Tạo nhóm" |
| Lỗi | `errorHTML(message, retry = true)` | Nút "Thử lại" gắn bằng `data-retry` |
| Thành công | `successHTML(message)`, `toast.success(message)` | Trong trang hoặc thông báo nổi |

Cách dùng thường gặp, gộp cả 4 trạng thái:

```js
renderState(box, () => get(`/groups/${id}/receipts`), (el, rows) => {
  el.innerHTML = dataTable(columns, rows);
}, {
  isEmpty: (rows) => rows.length === 0,
  emptyText: "Nhóm chưa có hóa đơn",
  emptyAction: { actionText: "Tải hóa đơn", actionHref: "#/receipts" },
  loading: "skeleton",
});
```

Lỗi 403 / 404 / 422 không hiện nút "Thử lại" (thử lại cũng ra kết quả như cũ). Lỗi mạng, 500 thì có.

## 2. Thông báo nổi (toast)

```js
toast.success("Đã lưu hóa đơn");
toast.info("Đang xử lý ảnh...");
toast.error(e);            // nhận chuỗi hoặc lỗi từ api.js (lấy e.message)
```

## 3. Form field

```js
form.innerHTML = `
  ${field({ label: "Tên cửa hàng", name: "merchant", required: true })}
  ${moneyField({ label: "Tổng tiền", name: "total", required: true })}
  ${selectField({ label: "Nhóm", name: "group_id", options: groups.map(g => ({ value: g.id, text: g.name })) })}
  ${textareaField({ label: "Ghi chú", name: "note" })}
  <button class="btn btn-primary">Lưu</button>`;
bindMoneyInputs(form);                         // ô tiền tự thêm dấu chấm: 90000 -> 90.000

form.onsubmit = async (ev) => {
  ev.preventDefault();
  if (!validateRequired(form)) return;          // báo "Không được để trống" dưới ô
  const data = { ...formValues(form), total: moneyValue(form.elements.total) };
  try {
    await withBusy(form.querySelector("button"), () => post("/receipts", data));
    toast.success("Đã lưu");
  } catch (e) {
    handleFormError(form, e);                   // 422/409 có details -> đỏ đúng ô; còn lại -> toast
  }
};
```

## 4. Bảng

```js
dataTable(
  [
    { key: "name", title: "Món" },
    { key: "amount", title: "Thành tiền", align: "end", render: (v) => formatVND(v) },
  ],
  rows,
  { emptyText: "Chưa có món", footer: { name: "Tổng cộng", amount: formatVND(total) } },
);
```

Cột không có `render` được tự `esc()`. Nếu dùng `render`, tự `esc()` phần dữ liệu người dùng.

## 5. Hộp xác nhận

```js
if (await confirmDialog({ title: "Xóa hóa đơn?", message: "Không hoàn tác được.", okText: "Xóa", danger: true })) {
  await del(`/receipts/${id}`);
}
```

## 6. Định dạng tiền VND, ngày (`js/format.js`)

| Hàm | Ví dụ |
|---|---|
| `formatVND(90000)` | `90.000 ₫` |
| `formatVND(null)` | `—` |
| `formatVNDShort(1500000)` | `1,5 tr` (trục biểu đồ) |
| `formatNumber(90000)` | `90.000` (ô nhập) |
| `parseVND("90.000 ₫")` | `90000` |
| `formatDate("2026-11-13")` | `13/11/2026` |

## Test

```bash
cd frontend
node --test tests/components.test.mjs
```
