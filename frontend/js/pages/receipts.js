// T05E174 - UI-03: Danh sách hóa đơn
// - Chọn nhóm, danh sách hóa đơn của nhóm, badge trạng thái DRAFT / VERIFIED / SETTLED
// - Nút "+ Thêm hóa đơn": tải ảnh JPG/PNG (≤ 5 MB) -> tạo hóa đơn nháp (DRAFT)
// - Lọc cơ bản: theo trạng thái, tìm theo tên cửa hàng, sắp xếp
import { get, upload } from "../api.js";
import { formatDate, formatVND } from "../format.js";
import {
  clearFieldErrors,
  dataTable,
  emptyHTML,
  esc,
  renderState,
  selectField,
  showFieldErrors,
  toast,
  withBusy,
} from "../ui.js";

const MAX_MB = 5;
const IMAGE_TYPES = ["image/jpeg", "image/png"];

export const STATUS = {
  DRAFT: { label: "Nháp", cls: "rc-badge-draft", hint: "Chưa xác nhận, còn sửa được" },
  VERIFIED: { label: "Đã xác nhận", cls: "rc-badge-verified", hint: "Đã kiểm tra, chờ chốt" },
  SETTLED: { label: "Đã chốt", cls: "rc-badge-settled", hint: "Đã chốt, không sửa được nữa" },
};

// Kiểu dáng riêng của trang, cùng bảng màu Pink & Lavender với trang Nhóm (UI-05).
// Chèn một lần vào <head>, chỉ áp dụng trong .page-receipts nên không ảnh hưởng trang khác.
const CSS = `
.page-receipts {
  --plum: #464052; --brand-dark: #7a62a3; --line: #e9ddf7; --mist: #f3edfb;
  --grad: linear-gradient(100deg, #f0b0c3 0%, #d9b5d9 50%, #b6a1d4 100%);
}
.page-receipts .page-title {
  font-size: clamp(1.8rem, 3vw, 2.3rem); font-weight: 800 !important; letter-spacing: -0.03em; line-height: 1.15;
  background: linear-gradient(95deg, #464052 0%, #7a62a3 60%, #c27a9b 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent !important;
}
.page-receipts .page-title-ico {
  width: 46px; height: 46px; border-radius: 14px; display: grid; place-items: center; flex: none;
  background: var(--grad); color: var(--plum); box-shadow: 0 8px 18px -12px rgba(182, 161, 212, 0.9);
}
.page-receipts .page-title-ico svg { width: 24px; height: 24px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.page-receipts .btn-primary { background: var(--grad); border: 0; color: var(--plum); font-weight: 600; box-shadow: 0 8px 18px -12px rgba(182, 161, 212, 0.9); }
.page-receipts .btn-primary:hover, .page-receipts .btn-primary:focus-visible { background: linear-gradient(100deg, #eba1b7 0%, #d1a8d2 50%, #a993cb 100%); color: var(--plum); }
.page-receipts .card { border: 1px solid var(--line); border-radius: 14px; }
.page-receipts .form-control:focus, .page-receipts .form-select:focus { border-color: #b6a1d4; box-shadow: 0 0 0 .2rem rgba(182, 161, 212, .35); }
.rc-chip { border: 1px solid var(--line); background: #fff; color: var(--plum); border-radius: 999px; padding: 4px 12px; font-size: .875rem; }
.rc-chip:hover { background: var(--mist); }
.rc-chip[aria-pressed="true"] { background: var(--grad); border-color: transparent; font-weight: 600; }
.rc-chip .rc-count { display: inline-block; min-width: 20px; margin-left: 4px; padding: 0 6px; border-radius: 999px; background: var(--mist); font-size: .75rem; font-weight: 600; }
.rc-chip[aria-pressed="true"] .rc-count { background: rgba(255, 255, 255, .7); }
.rc-badge-draft { background: #ece8f1; color: #5b5568; }
.rc-badge-verified { background: #e9ddf7; color: #5a4790; }
.rc-badge-settled { background: #fce4ec; color: #a0516e; }
.rc-table { background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 4px 12px; }
.rc-table .table { margin-bottom: 0; }
.rc-table thead th { background: transparent; color: #6f687c; font-weight: 600; border-bottom-color: var(--line); }
.rc-table tbody td { border-color: #f1ecf8; }
.rc-table .table-warning > td, .receipt-card.rc-new { background: #fdf3d8 !important; }
.rc-summary { color: #6f687c; font-size: .875rem; }
.rc-empty { background: #fff; border: 1px dashed #dcd3ea; border-radius: 14px; }
`;
function ensureStyles() {
  if (document.getElementById("receipts-css")) return;
  const st = document.createElement("style");
  st.id = "receipts-css";
  st.textContent = CSS;
  document.head.appendChild(st);
}

const ICON =
  '<svg viewBox="0 0 24 24"><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9.5 8h5M9.5 12h5M9.5 16h3"/></svg>';
const OCR = {
  PENDING: '<span class="text-muted small d-block">Chờ đọc ảnh</span>',
  FAILED: '<span class="text-danger small d-block">Đọc ảnh lỗi</span>',
};

export const statusBadge = (s) => {
  const m = STATUS[s];
  return m
    ? `<span class="badge rounded-pill ${m.cls}" title="${esc(s)}: ${esc(m.hint)}">${esc(m.label)}</span>`
    : `<span class="badge rounded-pill text-bg-light">${esc(s)}</span>`;
};

const SORTS = {
  newest: { text: "Mới nhất", fn: (a, b) => dateOf(b) - dateOf(a) || b.id - a.id },
  oldest: { text: "Cũ nhất", fn: (a, b) => dateOf(a) - dateOf(b) || a.id - b.id },
  amount: { text: "Tiền nhiều nhất", fn: (a, b) => Number(b.total_amount ?? 0) - Number(a.total_amount ?? 0) },
};
const dateOf = (r) => new Date(r.receipt_date ?? r.created_at ?? 0).getTime() || 0;

// Bỏ dấu để tìm "pho hoa" vẫn ra "Phở Hòa"
const fold = (s) =>
  String(s ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase()
    .trim();

/** Lọc + sắp xếp, tách riêng để dễ test */
export function applyFilters(rows, { status = "ALL", q = "", sort = "newest" } = {}) {
  const key = fold(q);
  return rows
    .filter((r) => status === "ALL" || r.status === status)
    .filter((r) => !key || fold(r.merchant_name).includes(key))
    .sort((SORTS[sort] ?? SORTS.newest).fn);
}

export function render(el, params) {
  const state = {
    groupId: params.group ?? null,
    status: STATUS[params.status] ? params.status : "ALL",
    q: "",
    sort: "newest",
    rows: [],
    members: new Map(),
    highlight: null,
  };

  ensureStyles();
  el.innerHTML = `<div class="page-receipts">
    <div class="page-head d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
      <div class="d-flex align-items-center gap-3">
        <span class="page-title-ico" aria-hidden="true">${ICON}</span>
        <div>
          <h2 class="page-title mb-0">Hóa đơn</h2>
          <div class="text-muted">Hóa đơn của từng nhóm và trạng thái chia tiền</div>
        </div>
      </div>
      <button class="btn btn-primary d-none" id="btn-add" aria-expanded="false" aria-controls="upload-panel">+ Thêm hóa đơn</button>
    </div>
    <div id="picker"></div>
    <div id="upload-panel" class="card mb-3 d-none"></div>
    <div id="filters" class="d-none"></div>
    <div id="list"></div>
  </div>`;

  const list = el.querySelector("#list");
  const filters = el.querySelector("#filters");
  const addBtn = el.querySelector("#btn-add");
  const panel = el.querySelector("#upload-panel");

  const syncUrl = () => {
    const qs = new URLSearchParams({ group: state.groupId });
    if (state.status !== "ALL") qs.set("status", state.status);
    // Đổi địa chỉ mà không vẽ lại trang (để giữ bộ lọc khi tải lại / gửi link)
    history.replaceState(null, "", `#/receipts?${qs}`);
  };

  /* ---------- Danh sách + bộ lọc ---------- */
  const cols = [
    { key: "receipt_date", title: "Ngày", render: (v, r) => formatDate(v ?? r.created_at) },
    {
      key: "merchant_name",
      title: "Cửa hàng",
      render: (v, r) =>
        (v ? `<span class="fw-semibold">${esc(v)}</span>` : '<span class="text-muted fst-italic">Chưa có tên</span>') +
        (r.status === "DRAFT" ? OCR[r.ocr_status] ?? "" : ""),
    },
    {
      key: "payer_id",
      title: "Người trả",
      render: (v) => (v ? esc(state.members.get(v) ?? `#${v}`) : '<span class="text-muted">Chưa chọn</span>'),
    },
    { key: "total_amount", title: "Tổng tiền", align: "end", render: (v) => formatVND(v) },
    { key: "status", title: "Trạng thái", render: (v) => statusBadge(v) },
  ];

  // Điện thoại: mỗi hóa đơn một thẻ, dễ đọc hơn bảng nhiều cột
  const cardList = (rows) =>
    `<ul class="list-unstyled d-grid gap-2 mb-0">${rows
      .map(
        (r) => `<li class="receipt-card card"><div class="card-body py-2 px-3">
          <div class="d-flex justify-content-between align-items-start gap-2">
            <div style="min-width:0">
              ${r.merchant_name ? `<div class="fw-semibold text-truncate">${esc(r.merchant_name)}</div>` : '<div class="text-muted fst-italic">Chưa có tên</div>'}
              <div class="text-muted small">${formatDate(r.receipt_date ?? r.created_at)} · ${r.payer_id ? esc(state.members.get(r.payer_id) ?? "") : "Chưa chọn người trả"}</div>
              ${r.status === "DRAFT" ? OCR[r.ocr_status] ?? "" : ""}
            </div>
            <div class="text-end flex-shrink-0">
              <div class="fw-semibold">${formatVND(r.total_amount)}</div>
              ${statusBadge(r.status)}
            </div>
          </div>
        </div></li>`,
      )
      .join("")}</ul>`;

  function paintFilters() {
    const count = (s) => (s === "ALL" ? state.rows.length : state.rows.filter((r) => r.status === s).length);
    const chip = (s, text) =>
      `<button type="button" class="rc-chip" data-status="${s}" aria-pressed="${state.status === s}">
         ${esc(text)}<span class="rc-count">${count(s)}</span>
       </button>`;
    filters.innerHTML = `
      <div class="d-flex flex-wrap gap-2 align-items-center mb-2" role="group" aria-label="Lọc theo trạng thái">
        ${chip("ALL", "Tất cả")}${chip("DRAFT", "Nháp")}${chip("VERIFIED", "Đã xác nhận")}${chip("SETTLED", "Đã chốt")}
      </div>
      <div class="row g-2 mb-3">
        <div class="col-sm-7 col-lg-5">
          <input type="search" class="form-control" id="f-q" placeholder="Tìm theo tên cửa hàng..." value="${esc(state.q)}" aria-label="Tìm theo tên cửa hàng">
        </div>
        <div class="col-sm-5 col-lg-3">
          <select class="form-select" id="f-sort" aria-label="Sắp xếp">
            ${Object.entries(SORTS).map(([k, s]) => `<option value="${k}" ${state.sort === k ? "selected" : ""}>${s.text}</option>`).join("")}
          </select>
        </div>
      </div>`;
    filters.querySelectorAll("[data-status]").forEach((b) => {
      b.onclick = () => {
        state.status = b.dataset.status;
        syncUrl();
        paintFilters();
        paintTable();
      };
    });
    const q = filters.querySelector("#f-q");
    q.oninput = () => {
      state.q = q.value;
      paintTable();
    };
    filters.querySelector("#f-sort").onchange = (e) => {
      state.sort = e.target.value;
      paintTable();
    };
  }

  function paintTable() {
    if (!state.rows.length) {
      list.innerHTML = emptyHTML("Nhóm này chưa có hóa đơn. Bấm “+ Thêm hóa đơn” để tải ảnh hóa đơn đầu tiên.");
      return;
    }
    const shown = applyFilters(state.rows, state);
    const total = shown.reduce((s, r) => s + Number(r.total_amount ?? 0), 0);
    list.innerHTML = shown.length
      ? `<div class="rc-summary mb-2">Hiển thị ${shown.length}/${state.rows.length} hóa đơn · Tổng <b>${formatVND(total)}</b></div>
         <div class="d-none d-md-block rc-table">${dataTable(cols, shown)}</div>
         <div class="d-md-none">${cardList(shown)}</div>`
      : `<div class="rc-empty text-center text-muted p-4">Không có hóa đơn khớp bộ lọc.
           <button type="button" class="btn btn-link p-0 align-baseline" id="btn-clear">Xóa bộ lọc</button></div>`;
    list.querySelector("#btn-clear")?.addEventListener("click", () => {
      Object.assign(state, { status: "ALL", q: "", sort: "newest" });
      syncUrl();
      paintFilters();
      paintTable();
    });
    if (state.highlight) {
      // Đánh dấu hóa đơn vừa thêm (cả bảng trên máy tính và thẻ trên điện thoại)
      const idx = shown.findIndex((r) => r.id === state.highlight);
      list.querySelectorAll("tbody tr")[idx]?.classList.add("table-warning");
      list.querySelectorAll(".receipt-card")[idx]?.classList.add("rc-new");
      state.highlight = null;
    }
  }

  const loadReceipts = () =>
    renderState(
      list,
      async () => {
        const [g, rows] = await Promise.all([get(`/groups/${state.groupId}`), get(`/groups/${state.groupId}/receipts`)]);
        state.members = new Map((g.members ?? []).map((m) => [m.user_id, m.full_name]));
        return rows;
      },
      (_, rows) => {
        state.rows = rows;
        filters.classList.remove("d-none");
        addBtn.classList.remove("d-none");
        paintFilters();
        paintTable();
      },
    );

  /* ---------- Thêm hóa đơn (tải ảnh) ---------- */
  panel.innerHTML = `
    <div class="card-body">
      <h5 class="card-title mb-1">Thêm hóa đơn</h5>
      <p class="text-muted small mb-3">Chụp hoặc chọn ảnh hóa đơn (JPG, PNG, tối đa ${MAX_MB} MB). Hóa đơn được tạo ở trạng thái <b>Nháp</b>, sau đó có thể đọc ảnh và sửa trước khi xác nhận.</p>
      <form id="upload-form" novalidate>
        <div class="mb-3">
          <label class="form-label" for="f-file">Ảnh hóa đơn <span class="text-danger">*</span></label>
          <input class="form-control" type="file" id="f-file" name="file" accept="image/jpeg,image/png">
          <div class="invalid-feedback"></div>
        </div>
        <img id="preview" class="d-none rounded border mb-3" alt="Ảnh hóa đơn đã chọn" style="max-height:180px;max-width:100%">
        <div class="d-flex gap-2">
          <button class="btn btn-primary" type="submit">Tải lên</button>
          <button class="btn btn-outline-secondary" type="button" id="btn-cancel">Hủy</button>
        </div>
      </form>
    </div>`;
  const form = panel.querySelector("#upload-form");
  const fileInput = form.elements.file;
  const preview = panel.querySelector("#preview");

  const togglePanel = (open) => {
    panel.classList.toggle("d-none", !open);
    addBtn.setAttribute("aria-expanded", String(open));
    if (!open) {
      form.reset();
      clearFieldErrors(form);
      preview.classList.add("d-none");
      if (preview.src) URL.revokeObjectURL(preview.src);
      preview.removeAttribute("src");
    } else fileInput.focus();
  };
  addBtn.onclick = () => togglePanel(panel.classList.contains("d-none"));
  panel.querySelector("#btn-cancel").onclick = () => togglePanel(false);

  const checkFile = (f) => {
    if (!f) return "Chọn ảnh hóa đơn";
    if (!IMAGE_TYPES.includes(f.type)) return "Chỉ nhận ảnh JPG hoặc PNG";
    if (f.size > MAX_MB * 1024 * 1024) return `Ảnh quá lớn (tối đa ${MAX_MB} MB)`;
    return null;
  };

  fileInput.onchange = () => {
    clearFieldErrors(form);
    const f = fileInput.files[0];
    const err = checkFile(f);
    if (preview.src) URL.revokeObjectURL(preview.src);
    if (err) {
      preview.classList.add("d-none");
      if (f) showFieldErrors(form, [{ field: "file", message: err }]);
      return;
    }
    preview.src = URL.createObjectURL(f);
    preview.classList.remove("d-none");
  };

  form.onsubmit = async (ev) => {
    ev.preventDefault();
    clearFieldErrors(form);
    const f = fileInput.files[0];
    const err = checkFile(f);
    if (err) return showFieldErrors(form, [{ field: "file", message: err }]);
    const fd = new FormData();
    fd.append("file", f);
    try {
      const r = await withBusy(form.querySelector("[type=submit]"), () => upload(`/groups/${state.groupId}/receipts`, fd));
      toast.success("Đã thêm hóa đơn nháp");
      togglePanel(false);
      state.rows = [r, ...state.rows.filter((x) => x.id !== r.id)];
      Object.assign(state, { status: "ALL", q: "", sort: "newest", highlight: r.id });
      syncUrl();
      paintFilters();
      paintTable();
    } catch (e) {
      // 400 sai loại ảnh, 413 quá lớn -> báo dưới ô chọn ảnh; còn lại -> toast
      if ([400, 413, 422].includes(e.status)) showFieldErrors(form, [{ field: "file", message: e.message }]);
      else toast.error(e);
    }
  };

  /* ---------- Chọn nhóm ---------- */
  renderState(
    el.querySelector("#picker"),
    () => get("/groups"),
    (box, groups) => {
      if (!groups.length) {
        box.innerHTML = emptyHTML("Bạn cần tham gia hoặc tạo một nhóm trước khi thêm hóa đơn");
        list.innerHTML = "";
        return;
      }
      if (!groups.some((g) => String(g.id) === String(state.groupId))) state.groupId = groups[0].id;
      box.innerHTML = `<div style="max-width:360px">${selectField({
        label: "Nhóm",
        name: "group",
        value: state.groupId,
        options: groups.map((g) => ({ value: g.id, text: g.name })),
      })}</div>`;
      box.querySelector("select").onchange = (e) => {
        Object.assign(state, { groupId: e.target.value, status: "ALL", q: "" });
        togglePanel(false);
        syncUrl();
        loadReceipts();
      };
      syncUrl();
      loadReceipts();
    },
  );
}
