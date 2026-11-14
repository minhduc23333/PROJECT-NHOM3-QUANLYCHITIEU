// Trang thử toàn bộ component dùng chung & trạng thái UI (T05E166): mở #/dev/ui
import { formatDate, formatVND, formatVNDShort } from "../format.js";
import {
  bindMoneyInputs,
  clearFieldErrors,
  confirmDialog,
  dataTable,
  emptyHTML,
  errorHTML,
  field,
  formValues,
  loadingHTML,
  moneyField,
  moneyValue,
  renderState,
  selectField,
  showFieldErrors,
  skeletonHTML,
  successHTML,
  textareaField,
  toast,
  validateRequired,
  withBusy,
} from "../ui.js";

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const ITEMS = [
  { name: "Phở bò tái", qty: 1, amount: 65000 },
  { name: "Bún chả", qty: 1, amount: 55000 },
  { name: "Gỏi cuốn (3 cuốn)", qty: 1, amount: 45000 },
  { name: "Trà đá", qty: 3, amount: 15000 },
];
const COLS = [
  { key: "name", title: "Món" },
  { key: "qty", title: "SL", align: "center" },
  { key: "amount", title: "Thành tiền", align: "end", render: (v) => formatVND(v) },
];

export function render(el) {
  el.innerHTML = `<div class="ui-demo">
    <h2 class="mb-1">Component dùng chung &amp; trạng thái UI</h2>
    <p class="text-muted">Trang dành cho nhóm phát triển: xem và thử mọi component trước khi dùng trong các trang.</p>

    <section>
      <h5>1. Trạng thái tải dữ liệu</h5>
      <div class="d-flex gap-2 flex-wrap mb-3">
        <button class="btn btn-outline-secondary btn-sm" data-state="ok">Có dữ liệu</button>
        <button class="btn btn-outline-secondary btn-sm" data-state="empty">Trống</button>
        <button class="btn btn-outline-secondary btn-sm" data-state="error">Lỗi mạng (có Thử lại)</button>
        <button class="btn btn-outline-secondary btn-sm" data-state="403">Lỗi 403 (không Thử lại)</button>
        <button class="btn btn-outline-secondary btn-sm" data-state="skeleton">Tải kiểu khung xương</button>
      </div>
      <div class="card"><div class="card-body" id="state-box"></div></div>
    </section>

    <section>
      <h5>2. Các khối trạng thái riêng lẻ</h5>
      <div class="row g-3">
        <div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-body">${loadingHTML()}</div></div></div>
        <div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-body">${emptyHTML("Chưa có hóa đơn", { actionText: "Tải hóa đơn", actionHref: "#/receipts" })}</div></div></div>
        <div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-body">${errorHTML("Không kết nối được máy chủ", false)}</div></div></div>
        <div class="col-md-6 col-xl-3"><div class="card h-100"><div class="card-body">${successHTML("Đã lưu hóa đơn")}</div></div></div>
      </div>
      <div class="card mt-3"><div class="card-body">${skeletonHTML(3)}</div></div>
    </section>

    <section>
      <h5>3. Thông báo nổi (toast) và hộp xác nhận</h5>
      <div class="d-flex gap-2 flex-wrap">
        <button class="btn btn-success" id="t-ok">Thông báo thành công</button>
        <button class="btn btn-primary" id="t-info">Thông báo thông tin</button>
        <button class="btn btn-danger" id="t-err">Thông báo lỗi</button>
        <button class="btn btn-outline-danger" id="m-del">Hộp xác nhận xóa</button>
        <button class="btn btn-outline-primary" id="m-ok">Hộp xác nhận thường</button>
      </div>
      <div class="small text-muted mt-2" id="m-result"></div>
    </section>

    <section>
      <h5>4. Form field + hiển thị lỗi</h5>
      <div class="card"><div class="card-body">
        <form id="demo-form" novalidate style="max-width:520px">
          ${field({ label: "Tên cửa hàng", name: "merchant", required: true, placeholder: "VD: Quán Phở Hòa" })}
          ${moneyField({ label: "Tổng tiền", name: "total", required: true, hint: "Gõ số, dấu chấm tự thêm" })}
          ${selectField({ label: "Danh mục", name: "category", required: true, placeholder: "Chọn danh mục", options: [{ value: "an-uong", text: "Ăn uống" }, { value: "di-lai", text: "Đi lại" }] })}
          ${textareaField({ label: "Ghi chú", name: "note", placeholder: "Không bắt buộc" })}
          <div class="d-flex gap-2">
            <button class="btn btn-primary" type="submit">Lưu (giả lập)</button>
            <button class="btn btn-outline-secondary" type="button" id="server-err">Giả lập lỗi 422 từ server</button>
          </div>
        </form>
      </div></div>
    </section>

    <section>
      <h5>5. Bảng dữ liệu + định dạng tiền VND</h5>
      <div class="card"><div class="card-body" id="table-box"></div></div>
      <div class="card mt-3"><div class="card-body">${dataTable(COLS, [], { emptyText: "Hóa đơn chưa có món nào" })}</div></div>
    </section>

    <section>
      <h5>6. Định dạng tiền, ngày</h5>
      <div class="card"><div class="card-body" id="fmt-box"></div></div>
    </section>
  </div>`;

  // 1. Trạng thái tải
  const stateBox = el.querySelector("#state-box");
  const load = (mode) =>
    renderState(
      stateBox,
      async () => {
        await wait(700);
        if (mode === "error") throw Object.assign(new Error("Không kết nối được máy chủ"), { status: 0 });
        if (mode === "403") throw Object.assign(new Error("Bạn không phải thành viên của nhóm này"), { status: 403 });
        return mode === "empty" ? [] : ITEMS;
      },
      (c, rows) => {
        c.innerHTML = dataTable(COLS, rows);
      },
      {
        isEmpty: (d) => d.length === 0,
        emptyText: "Nhóm chưa có hóa đơn nào",
        emptyAction: { actionText: "Tải hóa đơn đầu tiên", actionHref: "#/receipts" },
        loading: mode === "skeleton" ? "skeleton" : "Đang tải hóa đơn...",
      },
    );
  el.querySelectorAll("[data-state]").forEach((b) => (b.onclick = () => load(b.dataset.state)));
  load("ok");

  // 3. Toast + hộp xác nhận
  const result = el.querySelector("#m-result");
  el.querySelector("#t-ok").onclick = () => toast.success("Đã lưu hóa đơn");
  el.querySelector("#t-info").onclick = () => toast.info("Đang xử lý ảnh hóa đơn...");
  el.querySelector("#t-err").onclick = () => toast.error("Không tải được ảnh, thử lại sau");
  el.querySelector("#m-del").onclick = async () => {
    const ok = await confirmDialog({ title: "Xóa hóa đơn?", message: "Hóa đơn và phần chia tiền sẽ bị xóa, không hoàn tác được.", okText: "Xóa", danger: true });
    result.textContent = ok ? "Kết quả: đã bấm Xóa" : "Kết quả: đã hủy";
    if (ok) toast.success("Đã xóa hóa đơn");
  };
  el.querySelector("#m-ok").onclick = async () => {
    const ok = await confirmDialog({ title: "Chốt hóa đơn?", message: "Sau khi chốt, các thành viên sẽ thấy số tiền phải trả.", okText: "Chốt" });
    result.textContent = ok ? "Kết quả: đã bấm Chốt" : "Kết quả: đã hủy";
  };

  // 4. Form
  const form = el.querySelector("#demo-form");
  bindMoneyInputs(form);
  form.onsubmit = async (ev) => {
    ev.preventDefault();
    if (!validateRequired(form)) return;
    const total = moneyValue(form.elements.total);
    if (total <= 0) return showFieldErrors(form, [{ field: "total", message: "Tổng tiền phải lớn hơn 0" }]);
    await withBusy(form.querySelector("[type=submit]"), () => wait(800));
    const v = formValues(form);
    toast.success(`Đã lưu "${v.merchant}" - ${formatVND(total)}`);
    form.reset();
    clearFieldErrors(form);
  };
  el.querySelector("#server-err").onclick = () => {
    clearFieldErrors(form);
    // Dạng lỗi backend trả về: {"error": {"code": "VALIDATION_ERROR", "details": [{field, message}]}}
    showFieldErrors(form, [
      { field: "merchant", message: "Tên cửa hàng tối đa 200 ký tự" },
      { field: "total", message: "Tổng tiền không khớp với tổng các món" },
    ]);
  };

  // 5. Bảng có dòng tổng
  const total = ITEMS.reduce((s, r) => s + r.amount, 0);
  el.querySelector("#table-box").innerHTML = dataTable(COLS, ITEMS, {
    caption: "Hóa đơn Quán Phở Hòa",
    footer: { name: "Tổng cộng", amount: formatVND(total) },
  });

  // 6. Định dạng
  const ex = [
    ["formatVND(90000)", formatVND(90000)],
    ['formatVND("1250000.00")', formatVND("1250000.00")],
    ["formatVND(null)", formatVND(null)],
    ["formatVNDShort(1500000)", formatVNDShort(1500000)],
    ['formatDate("2026-11-13")', formatDate("2026-11-13")],
  ];
  el.querySelector("#fmt-box").innerHTML = dataTable(
    [{ key: 0, title: "Gọi hàm" }, { key: 1, title: "Kết quả", align: "end" }],
    ex.map(([a, b]) => ({ 0: a, 1: b })),
  );
}
