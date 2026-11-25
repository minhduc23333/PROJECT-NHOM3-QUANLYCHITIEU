// T05E176 - UI-04: Kiểm tra & xác nhận kết quả OCR (#/receipts/:id)
// Ảnh gốc cạnh biểu mẫu; sửa/thêm/xóa dòng món; sửa tạm tính / VAT / phí / tổng; đánh dấu trường thiếu;
// chọn người ứng tiền; cảnh báo lệch tổng; nút Xác nhận (DRAFT -> VERIFIED).
import { API_BASE, del, get, patch, post } from "../api.js";
import { getToken, getUser } from "../auth.js";
import { formatDateTime, formatNumber, formatVND, parseVND } from "../format.js";
import { navigate } from "../router.js";
import { confirmDialog, emptyHTML, esc, toast, withBusy } from "../ui.js";

// Phải khớp backend (app/modules/receipts/categories.py). Mặc định "Khác".
const CATEGORIES = ["Ăn uống", "Di chuyển", "Mua sắm", "Khác"];
const DEFAULT_CATEGORY = "Khác";
const STATUS = {
  DRAFT: { text: "Nháp", cls: "rv-st-draft" },
  VERIFIED: { text: "Đã xác nhận", cls: "rv-st-verified" },
  SETTLED: { text: "Đã chốt", cls: "rv-st-settled" },
};

/** Kiểm tra số liệu, tách riêng để dễ test. Trả về danh sách cảnh báo (rỗng = khớp hết). */
export function checkTotals({ itemsSum, subtotal, tax, fee, discount = 0, total, itemCount }) {
  const out = [];
  if (!itemCount) out.push({ field: "items", text: "Hóa đơn chưa có dòng món nào." });
  if (subtotal == null) out.push({ field: "subtotal", text: "Chưa có tạm tính." });
  else if (itemCount && itemsSum !== subtotal)
    out.push({
      field: "subtotal",
      text: `Tổng các món ${formatVND(itemsSum)} khác tạm tính ${formatVND(subtotal)} (lệch ${formatVND(Math.abs(itemsSum - subtotal))}).`,
      fix: "sub",
    });
  if (total == null) out.push({ field: "total_amount", text: "Chưa có tổng tiền." });
  else if (subtotal != null) {
    const expected = subtotal + tax + fee - discount;
    if (expected < 0)
      out.push({
        field: "discount_amount",
        text: `Giảm giá / làm tròn (${formatVND(discount)}) lớn hơn tạm tính + VAT + phí (${formatVND(subtotal + tax + fee)}).`,
      });
    else if (expected !== total)
      out.push({
        field: "total_amount",
        text: `Tạm tính + VAT + phí${discount ? " − giảm giá" : ""} = ${formatVND(expected)} khác tổng tiền ${formatVND(total)} (lệch ${formatVND(Math.abs(expected - total))}).`,
        fix: "total",
      });
  }
  return out;
}

const CSS = `
.page-review { --ink:#464052; --muted:#6f687c; --line:#e9ddf7; --mist:#f3edfb; --brand-dark:#7a62a3;
  --grad: linear-gradient(100deg,#f0b0c3 0%,#d9b5d9 50%,#b6a1d4 100%); color: var(--ink); }
.page-review .page-title { font-size: clamp(1.6rem,3vw,2.1rem); font-weight:800 !important; letter-spacing:-.03em; line-height:1.15;
  background: linear-gradient(95deg,#464052 0%,#7a62a3 60%,#c27a9b 100%); -webkit-background-clip:text; background-clip:text; color:transparent !important; }
.page-review .card { border:1px solid var(--line); border-radius:16px; }
.page-review .btn-primary { background:var(--grad); border:0; color:var(--ink); font-weight:600; box-shadow:0 8px 18px -12px rgba(182,161,212,.9); }
.page-review .btn-primary:hover, .page-review .btn-primary:focus-visible { background:linear-gradient(100deg,#eba1b7 0%,#d1a8d2 50%,#a993cb 100%); color:var(--ink); }
.page-review .btn-primary:disabled { background:var(--grad); color:var(--ink); opacity:.55; }
.page-review .form-control:focus, .page-review .form-select:focus { border-color:#b6a1d4; box-shadow:0 0 0 .2rem rgba(182,161,212,.35); }
.page-review .section-title { font-size:1rem; font-weight:700; margin:0 0 10px; }
.page-review .rv-close {
  width:38px; height:38px; flex:none; display:grid; place-items:center; border:1px solid var(--line); border-radius:12px;
  background:#fff; color:var(--muted); text-decoration:none; transition:background .18s ease, color .18s ease, transform .18s ease, box-shadow .18s ease;
}
.page-review .rv-close svg { width:19px; height:19px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; }
.page-review .rv-close:hover, .page-review .rv-close:focus-visible {
  background:var(--mist); color:var(--ink); transform:rotate(90deg); box-shadow:0 3px 10px rgba(70,64,82,.12);
}
.page-review .rv-close:focus-visible { outline:2px solid #8a70b5; outline-offset:2px; }
.rv-badge { display:inline-block; padding:3px 10px; border-radius:999px; font-size:.78rem; font-weight:600; }
.rv-st-draft { background:#ece8f1; color:#5b5568; } .rv-st-verified { background:#e9ddf7; color:#5a4790; } .rv-st-settled { background:#fce4ec; color:#a0516e; }
.img-panel { position:sticky; top:76px; }
.img-box { position:relative; height:min(70vh,640px); overflow:auto; background:#efeaf6; border:1px solid var(--line); border-radius:14px; display:flex; align-items:flex-start; justify-content:center; }
.img-box img { display:block; width:100%; height:auto; transform-origin: top center; }
.img-empty { color:#6f687c; margin:auto; text-align:center; padding:20px; }
.img-tools { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
.img-tools .btn { border-radius:10px; }
.miss-tag { display:inline-block; margin-left:6px; padding:1px 8px; border-radius:999px; background:#fff1d6; color:#8a5a00; font-size:.72rem; font-weight:600; vertical-align:middle; }
.is-missing { border-color:#f0c36d !important; background:#fffbf1 !important; }
.notice { border-radius:14px; padding:12px 14px; display:flex; gap:10px; align-items:flex-start; }
.notice-ok { background:#effaf4; border:1px solid #c6e9d6; color:#24543d; }
.notice-warn { background:#fff8ec; border:1px solid #f5dcae; color:#7a4e00; }
.notice-fail { background:#fff4f6; border:1px solid #f3c6d2; color:#7d2f48; }
.notice-info { background:var(--mist); border:1px solid var(--line); color:var(--ink); }
.items-table td { vertical-align:middle; } .items-table input { min-width:0; }
.money-grid .form-label { font-size:.85rem; color:var(--muted); margin-bottom:4px; }
.money-grid .input-group-text { background:#faf8fd; }
.money-grid > [class*="col"] { min-width:0; }
@media (min-width: 768px) {
  .money-grid > [class*="col"] { flex:0 0 20%; max-width:20%; }
  .money-grid .rv-money-fix { width:100%; padding-inline:6px; text-align:center; overflow:hidden; }
  .money-grid .rv-money-fix span { min-width:0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
}
.money-grid .rv-money-fix {
  display:flex; align-items:center; justify-content:center; gap:6px; width:max-content; max-width:100%;
  margin:7px auto 0; padding:5px 12px; border:1px solid #d9c9ed; border-radius:999px;
  background:#f7f2fc; color:#5f4788; font-size:.8rem; font-weight:600; text-decoration:none;
  transition:background .18s ease, border-color .18s ease, box-shadow .18s ease, transform .18s ease;
}
.money-grid .rv-money-fix svg { width:15px; height:15px; flex:none; fill:none; stroke:currentColor; stroke-width:1.8; stroke-linecap:round; stroke-linejoin:round; }
.money-grid .rv-money-fix:hover, .money-grid .rv-money-fix:focus-visible {
  background:#eee5f8; border-color:#bca5dc; color:#49366c; box-shadow:0 3px 10px rgba(95,71,136,.15); transform:translateY(-1px);
}
.money-grid .rv-money-fix:focus-visible { outline:2px solid #8a70b5; outline-offset:2px; }
.check-list { list-style:none; padding:0; margin:0; display:grid; gap:6px; }
.check-list li { display:flex; gap:8px; align-items:flex-start; }
.sticky-actions { position:sticky; bottom:0; z-index:5; background:rgba(249,247,252,.95); backdrop-filter:blur(6px);
  border-top:1px solid var(--line); margin:16px -16px -16px; padding:12px 16px; border-radius:0 0 16px 16px; }
@media (max-width: 991.98px) { .img-panel { position:static; } .img-box { height:46vh; } }
/* Điện thoại: mỗi dòng món thành một khối (tên món một hàng riêng, bên dưới là SL / đơn giá / thành tiền) */
@media (max-width: 575.98px) {
  .items-table, .items-table tbody, .items-table tfoot { display:block; width:100%; }
  .items-table thead { display:none; }
  .items-table tfoot tr { display:flex; justify-content:space-between; padding-top:10px; }
  .items-table tfoot td:empty { display:none; }
  .items-table tbody tr { display:grid; grid-template-columns: 64px minmax(0,1fr) auto 24px; gap:6px 8px; align-items:center;
    padding:10px 0; border-bottom:1px solid var(--line); }
  .items-table tbody td { border:0; padding:0; }
  .items-table tbody td:first-child { grid-column: 1 / -1; }
  .items-table tfoot td { border:0; }
}
`;
function ensureStyles() {
  if (document.getElementById("review-css")) return;
  const st = document.createElement("style");
  st.id = "review-css";
  st.textContent = CSS;
  document.head.appendChild(st);
}

const num = (v) => (v == null || v === "" ? null : Math.round(Number(v)));
const moneyVal = (input) => (input.value.trim() === "" ? null : parseVND(input.value));
const bindMoney = (root) =>
  root.querySelectorAll("input[data-money]").forEach((inp) => {
    inp.addEventListener("input", () => {
      const digits = inp.value.replace(/\D/g, "");
      inp.value = digits ? formatNumber(Number(digits)) : "";
    });
  });

async function loadImage(id) {
  const r = await fetch(`${API_BASE}/receipts/${id}/image`, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!r.ok) return null;
  return URL.createObjectURL(await r.blob());
}

export function render(el, params) {
  ensureStyles();
  const id = params.id;
  el.innerHTML = `<div class="page-review"><div id="rv">${'<div class="text-muted p-3">Đang tải hóa đơn...</div>'}</div></div>`;
  const box = el.querySelector("#rv");
  let imgUrl = null;
  window.addEventListener("hashchange", () => imgUrl && URL.revokeObjectURL(imgUrl), { once: true });

  async function load() {
    let d, members;
    try {
      d = await get(`/receipts/${encodeURIComponent(id)}`);
      if (d.group_id) {
        const g = await get(`/groups/${d.group_id}`);
        members = (g.members ?? []).filter((m) => m.status === "ACTIVE");
        d.group_name = g.name;
      } else {
        const me = getUser();
        members = [{ user_id: me?.id ?? d.uploaded_by, full_name: me?.full_name ?? "Tôi" }];
      }
    } catch (e) {
      box.innerHTML = `<a href="#/receipts" class="d-inline-block mb-2" style="color:#7a62a3;text-decoration:none">‹ Danh sách hóa đơn</a>
        <div class="card"><div class="card-body">${emptyHTML(e.message, { actionText: "Về danh sách hóa đơn", actionHref: "#/receipts" })}</div></div>`;
      return;
    }
    if (!imgUrl) imgUrl = await loadImage(id).catch(() => null);
    paint(d, members);
  }

  function paint(d, members) {
    const editable = d.status !== "SETTLED" && (d.can_edit_receipt || d.can_edit_items);
    const headerOn = editable && d.can_edit_receipt;
    const itemsOn = editable && d.can_edit_items;
    const st = STATUS[d.status] ?? { text: d.status, cls: "" };
    const back = `#/receipts?group=${d.group_id ?? "personal"}`;
    const meId = getUser()?.id;
    const payerName = members.find((m) => m.user_id === d.payer_id)?.full_name;

    let notice = "";
    if (d.status === "SETTLED")
      notice = `<div class="notice notice-info mb-3"><span>🔒</span><div>Hóa đơn đã <b>chốt</b>, không sửa được nữa.</div></div>`;
    else if (d.status === "VERIFIED")
      notice = `<div class="notice notice-ok mb-3"><span>✓</span><div><b>Đã xác nhận</b>${payerName ? ` · Người ứng tiền: <b>${esc(payerName)}</b>` : ""}.
        Nếu sửa số tiền hoặc dòng món, hóa đơn sẽ quay về <b>Nháp</b> và cần xác nhận lại.</div></div>`;
    else if (d.ocr_status === "DONE")
      notice = `<div class="notice notice-ok mb-3"><span>✓</span><div><b>Đã đọc tự động từ ảnh.</b> Đối chiếu với ảnh hóa đơn, sửa chỗ sai, nhất là các ô có nhãn <span class="miss-tag">Thiếu</span> và các cảnh báo lệch tổng.</div></div>`;
    else if (d.ocr_status === "FAILED")
      notice = `<div class="notice notice-fail mb-3"><span>✍</span><div class="flex-grow-1"><b>Không đọc được ảnh tự động.</b> Đối chiếu với ảnh hóa đơn và nhập tay các ô bên dưới.
        ${d.can_edit_receipt && d.status === "DRAFT" ? '<div class="mt-2"><button type="button" class="btn btn-sm btn-outline-secondary" id="btn-ocr">Đọc lại ảnh</button></div>' : ""}</div></div>`;
    else
      notice = `<div class="notice notice-warn mb-3"><span>⏳</span><div class="flex-grow-1"><b>Ảnh chưa được đọc.</b> Bấm để hệ thống tự đọc, hoặc nhập tay luôn.
        ${d.can_edit_receipt ? '<div class="mt-2"><button type="button" class="btn btn-sm btn-primary" id="btn-ocr">Đọc ảnh tự động</button></div>' : ""}</div></div>`;

    const catOptions = [...new Set([...(d.category ? [d.category] : []), ...CATEGORIES])];
    const dis = (on) => (on ? "" : "disabled");

    box.innerHTML = `
      <a href="${back}" class="d-inline-block mb-2" style="color:#7a62a3;text-decoration:none">‹ Danh sách hóa đơn</a>
      <div class="d-flex justify-content-between align-items-start gap-2 mb-3">
        <div class="d-flex flex-wrap align-items-center gap-2">
          <h2 class="page-title mb-0">Kiểm tra hóa đơn</h2>
          <span class="rv-badge ${st.cls}" title="${esc(d.status)}">${st.text}</span>
          ${d.group_id && d.status !== "DRAFT" ? `<a class="btn btn-sm btn-primary" href="#/receipts/${d.id}/split">${d.status === "SETTLED" ? "Xem kết quả chia" : "Chia tiền →"}</a>` : ""}
          <span class="text-muted small ms-1">${esc(d.group_name ? `Nhóm: ${d.group_name}` : "Cá nhân")} · tải lên ${formatDateTime(d.created_at)}</span>
        </div>
        ${d.can_delete ? '<button type="button" class="btn btn-sm btn-outline-danger" id="btn-delete-receipt">Xóa hóa đơn</button>' : ""}
        <a class="rv-close" href="${back}" aria-label="Thoát kiểm tra hóa đơn" title="Thoát">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg>
        </a>
      </div>
      <div class="row g-4">
        <div class="col-lg-5">
          <div class="img-panel">
            <div class="img-box" id="img-box">
              ${imgUrl ? `<img id="rv-img" src="${imgUrl}" alt="Ảnh gốc hóa đơn">` : '<div class="img-empty">Không tải được ảnh gốc của hóa đơn.</div>'}
            </div>
            ${imgUrl ? `<div class="img-tools">
              <button type="button" class="btn btn-sm btn-outline-secondary" data-zoom="-">− Thu nhỏ</button>
              <button type="button" class="btn btn-sm btn-outline-secondary" data-zoom="0">Vừa khung</button>
              <button type="button" class="btn btn-sm btn-outline-secondary" data-zoom="+">+ Phóng to</button>
              <a class="btn btn-sm btn-outline-secondary" href="${imgUrl}" target="_blank" rel="noopener">Mở ảnh lớn ↗</a>
            </div>` : ""}
          </div>
        </div>

        <div class="col-lg-7">
          ${notice}
          <form id="rv-form" class="card" novalidate><div class="card-body">
            <h3 class="section-title">Thông tin chung</h3>
            <div class="row g-3 mb-3">
              <div class="col-md-6">
                <label class="form-label" for="f-merchant_name">Tên cửa hàng <span data-miss="merchant_name"></span></label>
                <input class="form-control" id="f-merchant_name" name="merchant_name" maxlength="255" placeholder="VD: Quán Phở Hòa" value="${esc(d.merchant_name ?? "")}" ${dis(headerOn)}>
                <div class="invalid-feedback"></div>
              </div>
              <div class="col-6 col-md-3">
                <label class="form-label" for="f-receipt_date">Ngày <span data-miss="receipt_date"></span></label>
                <input class="form-control" type="date" id="f-receipt_date" name="receipt_date" value="${esc(d.receipt_date ?? "")}" ${dis(headerOn)}>
                <div class="invalid-feedback"></div>
              </div>
              <div class="col-6 col-md-3">
                <label class="form-label" for="f-category">Danh mục</label>
                <select class="form-select" id="f-category" name="category" ${dis(headerOn)}>
                  ${catOptions.map((c) => `<option ${c === (d.category ?? DEFAULT_CATEGORY) ? "selected" : ""}>${esc(c)}</option>`).join("")}
                </select>
                <div class="form-text" id="cat-hint"></div>
              </div>
            </div>

            <div class="d-flex justify-content-between align-items-end mb-2">
              <h3 class="section-title mb-0">Dòng món <span data-miss="items"></span></h3>
              ${itemsOn ? '<button type="button" class="btn btn-sm btn-outline-secondary" id="btn-add-item">+ Thêm món</button>' : ""}
            </div>
            <div class="table-responsive">
              <table class="table align-middle items-table mb-1">
                <thead class="table-light"><tr><th>Tên món</th><th style="width:84px">SL</th><th style="width:140px">Đơn giá</th><th class="text-end" style="width:120px">Thành tiền</th>${itemsOn ? '<th style="width:40px"></th>' : ""}</tr></thead>
                <tbody id="items"></tbody>
                <tfoot><tr><td colspan="3" class="text-end text-muted">Tổng các món</td><td class="text-end fw-semibold" id="items-sum">0 ₫</td>${itemsOn ? "<td></td>" : ""}</tr></tfoot>
              </table>
            </div>
            <div class="invalid-feedback d-block mb-3" id="err-items"></div>

            <h3 class="section-title">Số tiền trên hóa đơn</h3>
            <div class="row g-3 money-grid mb-2">
              ${moneyInput("subtotal", "Tạm tính", d.subtotal, headerOn, "sub", "Lấy tổng các món")}
              ${moneyInput("tax_amount", "VAT", d.tax_amount, headerOn)}
              ${moneyInput("service_fee", "Phí dịch vụ", d.service_fee, headerOn)}
              ${moneyInput("discount_amount", "Giảm giá / làm tròn", d.discount_amount, headerOn)}
              ${moneyInput("total_amount", "Tổng tiền", d.total_amount, headerOn, "total", "Tổng chi phí")}
            </div>
            <div id="checks" class="mb-3" aria-live="polite"></div>

            <h3 class="section-title">Người ứng tiền <span data-miss="payer_id"></span></h3>
            <div class="mb-1" style="max-width:360px">
              <select class="form-select" id="f-payer_id" name="payer_id" ${dis(d.status === "DRAFT" && d.can_verify && d.group_id)}>
                ${d.group_id ? '<option value="">Chọn người đã trả tiền hóa đơn này</option>' : ""}
                ${members
                  .map((m) => {
                    const sel = (d.payer_id ?? (d.group_id ? meId : m.user_id)) === m.user_id;
                    return `<option value="${m.user_id}" ${sel ? "selected" : ""}>${esc(m.full_name)}${m.user_id === meId ? " (tôi)" : ""}</option>`;
                  })
                  .join("")}
              </select>
              <div class="invalid-feedback"></div>
            </div>
            <div class="form-text mb-2">${d.group_id ? "Người ứng tiền là người đã thanh toán; các thành viên khác sẽ nợ người này phần của mình." : "Hóa đơn cá nhân: người ứng tiền là bạn."}</div>

            ${editable || d.can_verify ? `<div class="sticky-actions d-flex flex-wrap gap-2 align-items-center">
              ${editable ? `<button type="button" class="btn btn-outline-secondary" id="btn-save">${d.status === "DRAFT" ? "Lưu nháp" : "Lưu thay đổi"}</button>` : ""}
              ${d.status === "DRAFT" && d.can_verify ? '<button type="submit" class="btn btn-primary" id="btn-verify">Xác nhận hóa đơn</button>' : ""}
              <span class="text-muted small ms-auto" id="save-state"></span>
            </div>` : ""}
          </div></form>
        </div>
      </div>`;

    function moneyInput(name, label, value, on, fix, fixText) {
      const zeroDefault = name === "tax_amount" || name === "service_fee" || name === "discount_amount";
      return `<div class="${name === "total_amount" ? "col-12 col-md-4" : "col-6 col-md-4"}">
        <label class="form-label" for="f-${name}">${label} <span data-miss="${name}"></span></label>
        <div class="input-group input-group-sm has-validation">
          <input class="form-control text-end" id="f-${name}" name="${name}" inputmode="numeric" data-money placeholder="${zeroDefault ? "0" : "—"}"
                 value="${value != null ? formatNumber(value) : ""}" ${on ? "" : "disabled"}>
          <span class="input-group-text">₫</span>
          <div class="invalid-feedback"></div>
        </div>
        ${fix && on ? `<button type="button" class="rv-money-fix" data-fix="${fix}">
          <svg viewBox="0 0 24 24" aria-hidden="true">${fix === "sub" ? '<path d="M4 5h16M4 10h10M4 15h8"/><path d="m15 17 2 2 4-5"/>' : '<rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 7h8M8 12h2m4 0h2m-8 4h2m4 0h2"/>'}</svg>
          <span>${fixText}</span>
        </button>` : "" }
      </div>`;
    }

    /* ----- Ảnh: phóng to / thu nhỏ ----- */
    const img = box.querySelector("#rv-img");
    let zoom = 1;
    box.querySelectorAll("[data-zoom]").forEach((b) => {
      b.onclick = () => {
        zoom = b.dataset.zoom === "0" ? 1 : Math.min(3, Math.max(1, zoom + (b.dataset.zoom === "+" ? 0.5 : -0.5)));
        img.style.width = `${zoom * 100}%`;
      };
    });

    /* ----- Dòng món ----- */
    const form = box.querySelector("#rv-form");
    const tbody = box.querySelector("#items");
    const removed = new Set();
    const original = new Map((d.items ?? []).map((it) => [it.id, it]));

    const rowHTML = (it = {}) => `<tr data-id="${it.id ?? ""}">
      <td><input class="form-control form-control-sm" name="item_name" maxlength="255" placeholder="Tên món" value="${esc(it.item_name ?? "")}" ${dis(itemsOn)}></td>
      <td><input class="form-control form-control-sm text-end" name="quantity" type="number" min="0.01" step="0.01" value="${it.quantity != null ? Number(it.quantity) : 1}" ${dis(itemsOn)}></td>
      <td><input class="form-control form-control-sm text-end" name="unit_price" inputmode="numeric" data-money placeholder="0" value="${it.unit_price != null ? formatNumber(it.unit_price) : ""}" ${dis(itemsOn)}></td>
      <td class="text-end text-nowrap" data-line>0 ₫</td>
      ${itemsOn ? '<td><button type="button" class="btn btn-sm btn-link text-danger p-0" data-del aria-label="Xóa dòng món">✕</button></td>' : ""}
    </tr>`;
    const addRow = (it) => {
      tbody.insertAdjacentHTML("beforeend", rowHTML(it));
      const tr = tbody.lastElementChild;
      bindMoney(tr);
      const delBtn = tr.querySelector("[data-del]");
      if (delBtn)
        delBtn.onclick = () => {
          if (tr.dataset.id) removed.add(Number(tr.dataset.id));
          tr.remove();
          refresh();
        };
      return tr;
    };
    (d.items?.length ? d.items : itemsOn ? [{}] : []).forEach((it) => addRow(it));
    box.querySelector("#btn-add-item")?.addEventListener("click", () => addRow().querySelector("[name=item_name]").focus());
    bindMoney(form);

    const filledRows = () =>
      [...tbody.querySelectorAll("tr")].filter(
        (tr) => tr.querySelector("[name=item_name]").value.trim() || parseVND(tr.querySelector("[name=unit_price]").value),
      );
    const lineOf = (tr) => Math.round((Number(tr.querySelector("[name=quantity]").value) || 0) * parseVND(tr.querySelector("[name=unit_price]").value));

    /* ----- Đánh dấu thiếu + cảnh báo lệch tổng, cập nhật khi gõ ----- */
    function refresh() {
      let itemsSum = 0;
      tbody.querySelectorAll("tr").forEach((tr) => {
        const l = lineOf(tr);
        itemsSum += l;
        tr.querySelector("[data-line]").textContent = formatVND(l);
      });
      box.querySelector("#items-sum").textContent = formatVND(itemsSum);
      const v = {
        itemsSum,
        itemCount: filledRows().length,
        subtotal: moneyVal(form.elements.subtotal),
        tax: moneyVal(form.elements.tax_amount) ?? 0,
        fee: moneyVal(form.elements.service_fee) ?? 0,
        discount: moneyVal(form.elements.discount_amount) ?? 0,
        total: moneyVal(form.elements.total_amount),
      };
      const missing = {
        merchant_name: !form.elements.merchant_name.value.trim(),
        receipt_date: !form.elements.receipt_date.value,
        items: v.itemCount === 0,
        subtotal: v.subtotal == null,
        total_amount: v.total == null,
        payer_id: !form.elements.payer_id.value,
      };
      Object.entries(missing).forEach(([k, m]) => {
        const tag = box.querySelector(`[data-miss="${k}"]`);
        if (tag) tag.innerHTML = m ? '<span class="miss-tag">Thiếu</span>' : "";
        form.elements[k]?.classList?.toggle("is-missing", m && !form.elements[k].disabled);
      });
      const warns = checkTotals(v);
      const checks = box.querySelector("#checks");
      checks.innerHTML = warns.length
        ? `<div class="notice notice-warn"><span>⚠</span><div class="flex-grow-1"><b>Số liệu chưa khớp</b>
            <ul class="check-list mt-1">${warns
              .map((w) => `<li>• <span>${w.text}${w.fix && headerOn ? ` <button type="button" class="btn btn-link btn-sm p-0 align-baseline" data-fix="${w.fix}">Sửa nhanh</button>` : ""}</span></li>`)
              .join("")}</ul></div></div>`
        : `<div class="notice notice-ok"><span>✓</span><div>Tổng các món, tạm tính, VAT, phí và tổng tiền đã khớp.</div></div>`;
      checks.querySelectorAll("[data-fix]").forEach((b) => (b.onclick = () => quickFix(b.dataset.fix)));
      return { v, warns, missing };
    }
    function quickFix(kind) {
      const { v } = refresh();
      if (kind === "sub") form.elements.subtotal.value = formatNumber(v.itemsSum);
      if (kind === "total") {
        const sub = moneyVal(form.elements.subtotal) ?? 0;
        form.elements.total_amount.value = formatNumber(Math.max(0, sub + v.tax + v.fee - v.discount));
      }
      refresh();
      box.querySelector("#save-state") && (box.querySelector("#save-state").textContent = "Có thay đổi chưa lưu");
    }
    box.querySelectorAll(".money-grid [data-fix]").forEach((b) => (b.onclick = () => quickFix(b.dataset.fix)));
    form.addEventListener("input", () => {
      refresh();
      const s = box.querySelector("#save-state");
      if (s) s.textContent = "Có thay đổi chưa lưu";
    });
    form.addEventListener("change", refresh);
    refresh();

    /* ----- Gợi ý danh mục theo tên cửa hàng (T05E17F) ----- */
    // Chỉ gợi ý khi người dùng chưa tự chọn và hóa đơn chưa có danh mục riêng; chọn tay luôn thắng.
    const catSelect = form.elements.category;
    const catHint = box.querySelector("#cat-hint");
    let catTouched = false;
    catSelect.addEventListener("change", () => {
      catTouched = true;
      if (catHint) catHint.textContent = "";
    });
    form.elements.merchant_name.addEventListener("change", async () => {
      const name = form.elements.merchant_name.value.trim();
      if (!headerOn || catTouched || !name || (d.category && d.category !== DEFAULT_CATEGORY)) return;
      try {
        const { category } = await get(`/receipts/category-suggestion?merchant_name=${encodeURIComponent(name)}`);
        if (!CATEGORIES.includes(category) || category === DEFAULT_CATEGORY || catSelect.value === category) return;
        catSelect.value = category;
        if (catHint) catHint.textContent = `Gợi ý theo tên cửa hàng: ${category}. Bạn có thể đổi.`;
        form.dispatchEvent(new Event("input")); // đánh dấu "Có thay đổi chưa lưu"
      } catch {
        /* gợi ý chỉ là tiện ích, lỗi thì bỏ qua */
      }
    });

    /* ----- Xóa hóa đơn ----- */
    box.querySelector("#btn-delete-receipt")?.addEventListener("click", async (e) => {
      const button = e.currentTarget;
      const ok = await confirmDialog({
        title: "Xóa hóa đơn?",
        message: `Hóa đơn “${d.merchant_name || "Chưa có tên"}” và dữ liệu chia tiền liên quan sẽ bị xóa. Không thể hoàn tác.`,
        okText: "Xóa",
        cancelText: "Hủy",
        danger: true,
      });
      if (!ok) return;
      try {
        await withBusy(button, () => del(`/receipts/${d.id}`));
        toast.success("Đã xóa hóa đơn");
        window.location.hash = back;
      } catch (err) {
        toast.error(err);
      }
    });

    /* ----- Đọc ảnh tự động (khi còn PENDING) ----- */
    box.querySelector("#btn-ocr")?.addEventListener("click", async (e) => {
      try {
        const res = await withBusy(e.currentTarget, () => post(`/ocr/receipts/${d.id}`, undefined, { timeoutMs: 300000 }));
        if (res?.receipt?.ocr_status === "FAILED")
          toast.error(new Error(res.warnings?.[0] ?? "Vẫn không đọc được ảnh, hãy nhập tay"));
        else toast.info(res?.warnings?.length ? `Đã đọc ảnh. Lưu ý: ${res.warnings[0]}` : "Đã đọc ảnh, kiểm tra lại kết quả");
      } catch (err) {
        toast.error(err);
      }
      load();
    });

    /* ----- Lưu ----- */
    const clearErrors = () => {
      form.querySelectorAll(".is-invalid").forEach((i) => i.classList.remove("is-invalid"));
      form.querySelectorAll(".invalid-feedback").forEach((f) => (f.textContent = ""));
      box.querySelector("#err-items").textContent = "";
    };
    const showErrors = (details = []) => {
      for (const e of details) {
        if (e.field === "items" || ["item_name", "quantity", "unit_price", "line_total"].includes(e.field)) {
          box.querySelector("#err-items").textContent = e.message;
          continue;
        }
        const input = form.elements[e.field];
        if (!input) continue;
        input.classList.add("is-invalid");
        const fb = input.closest(".input-group")?.querySelector(".invalid-feedback") ?? input.parentElement.querySelector(".invalid-feedback");
        if (fb) fb.textContent = e.message;
      }
    };

    async function save() {
      clearErrors();
      const rows = filledRows();
      let bad = false;
      rows.forEach((tr) => {
        const n = tr.querySelector("[name=item_name]");
        const q = tr.querySelector("[name=quantity]");
        if (!n.value.trim()) (n.classList.add("is-invalid"), (bad = true));
        if (!(Number(q.value) > 0)) (q.classList.add("is-invalid"), (bad = true));
      });
      if (bad) {
        box.querySelector("#err-items").textContent = "Dòng món cần có tên và số lượng lớn hơn 0";
        throw new Error("invalid");
      }
      if (itemsOn) {
        for (const itemId of removed) await del(`/receipts/${d.id}/items/${itemId}`);
        removed.clear();
        for (const tr of rows) {
          const body = {
            item_name: tr.querySelector("[name=item_name]").value.trim(),
            quantity: Number(tr.querySelector("[name=quantity]").value),
            unit_price: parseVND(tr.querySelector("[name=unit_price]").value),
          };
          const old = original.get(Number(tr.dataset.id));
          if (old) {
            // OCR có thể đọc thành tiền không khớp SL × đơn giá: gửi lại để server tính lại thành tiền
            const lineOk = num(old.line_total) === Math.round(body.quantity * body.unit_price);
            const same = lineOk && old.item_name === body.item_name && Number(old.quantity) === body.quantity && num(old.unit_price) === body.unit_price;
            if (!same) await patch(`/receipts/${d.id}/items/${old.id}`, body);
          } else {
            const created = await post(`/receipts/${d.id}/items`, body);
            tr.dataset.id = created.id;
            original.set(created.id, created);
          }
        }
        [...tbody.querySelectorAll("tr")].filter((tr) => !rows.includes(tr)).forEach((tr) => tr.remove());
      }
      if (headerOn) {
        const header = {
          merchant_name: form.elements.merchant_name.value.trim() || null,
          receipt_date: form.elements.receipt_date.value || null,
          category: form.elements.category.value,
          subtotal: moneyVal(form.elements.subtotal),
          tax_amount: moneyVal(form.elements.tax_amount) ?? 0,
          service_fee: moneyVal(form.elements.service_fee) ?? 0,
          discount_amount: moneyVal(form.elements.discount_amount) ?? 0,
          total_amount: moneyVal(form.elements.total_amount),
        };
        // Chỉ gửi trường đã đổi (tránh làm hóa đơn đã xác nhận bị mở lại không cần thiết)
        const changed = Object.fromEntries(
          Object.entries(header).filter(([k, val]) => {
            const zeroFields = ["tax_amount", "service_fee", "discount_amount"];
            const before = ["subtotal", "total_amount", ...zeroFields].includes(k) ? num(d[k]) ?? (zeroFields.includes(k) ? 0 : null) : (d[k] ?? null);
            return before !== val;
          }),
        );
        if (Object.keys(changed).length) await patch(`/receipts/${d.id}`, changed);
      }
    }

    box.querySelector("#btn-save")?.addEventListener("click", async (e) => {
      try {
        await withBusy(e.currentTarget, save);
        toast.success("Đã lưu nháp");
        load();
      } catch (err) {
        if (err.message !== "invalid") {
          showErrors(err.details);
          toast.error(err);
        }
      }
    });

    /* ----- Xác nhận ----- */
    form.onsubmit = async (ev) => {
      ev.preventDefault();
      const { warns, missing } = refresh();
      if (missing.payer_id) {
        showErrors([{ field: "payer_id", message: "Chọn người đã trả tiền" }]);
        form.elements.payer_id.focus();
        return;
      }
      if (warns.length) {
        const ok = await confirmDialog({
          title: "Số liệu chưa khớp",
          message: `${warns.map((w) => w.text.replace(/<[^>]+>/g, "")).join(" ")} Hệ thống sẽ không xác nhận được nếu số liệu lệch. Vẫn thử xác nhận?`,
          okText: "Vẫn xác nhận",
        });
        if (!ok) return;
      }
      const btn = box.querySelector("#btn-verify");
      try {
        await withBusy(btn, async () => {
          if (editable) await save();
          await post(`/receipts/${d.id}/verify`, { payer_id: Number(form.elements.payer_id.value) });
        });
        toast.success("Đã xác nhận hóa đơn");
        navigate(d.group_id ? `/receipts/${d.id}/split` : "/receipts?group=personal");
      } catch (err) {
        if (err.message === "invalid") return;
        clearErrors();
        showErrors(err.details);
        toast.error(err.details?.length ? "Hóa đơn chưa hợp lệ để xác nhận, xem các ô báo đỏ" : err);
      }
    };
  }

  load();
}
