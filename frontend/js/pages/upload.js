// T05E175 - UI Tải ảnh & theo dõi trạng thái OCR (#/receipts/new)
// Bước 1: chọn nhóm + chọn ảnh (xem trước, kiểm tra định dạng/kích thước ngay trên trình duyệt)
// Bước 2: tải lên (có % tiến độ) -> chạy OCR (hiện đang xử lý, đếm giây)
// Bước 3: OCR xong -> kiểm tra & sửa;  OCR thất bại -> chuyển sang nhập tay
// Mở lại hóa đơn nháp dang dở: #/receipts/new?receipt=<id>
import { API_BASE, ApiError, del, get, patch, post } from "../api.js";
import { getToken, logout } from "../auth.js";
import { formatNumber, formatVND, parseVND } from "../format.js";

import { clearFieldErrors, emptyHTML, esc, showFieldErrors, toast, withBusy } from "../ui.js";

export const MAX_MB = 5;
const CATEGORIES = ["Ăn uống", "Đi lại", "Mua sắm", "Nhà ở", "Giải trí", "Sức khỏe", "Khác"];
const FIELD_LABEL = {
  merchant_name: "Tên cửa hàng",
  receipt_date: "Ngày",
  items: "Danh sách món",
  subtotal: "Tạm tính",
  total_amount: "Tổng tiền",
};

/* ---------------- Kiểm tra ảnh phía trình duyệt ---------------- */
// Đọc vài byte đầu để biết đúng là JPG/PNG (không tin đuôi file)
export function sniffType(bytes) {
  const b = new Uint8Array(bytes);
  if (b[0] === 0xff && b[1] === 0xd8 && b[2] === 0xff) return "jpeg";
  const png = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (png.every((v, i) => b[i] === v)) return "png";
  return null;
}

export async function checkImage(file) {
  if (!file) return { error: "Chọn ảnh hóa đơn" };
  if (file.size === 0) return { error: "File rỗng" };
  if (file.size > MAX_MB * 1024 * 1024)
    return { error: `Ảnh ${(file.size / 1024 / 1024).toFixed(1)} MB, vượt quá giới hạn ${MAX_MB} MB` };
  const kind = sniffType(await file.slice(0, 8).arrayBuffer());
  if (!kind) return { error: "Chỉ nhận ảnh JPG hoặc PNG" };
  const dims = await new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => resolve({ w: img.naturalWidth, h: img.naturalHeight, url });
    img.onerror = () => resolve(null);
    img.src = url;
  });
  if (!dims) return { error: "Ảnh bị hỏng, không mở được" };
  const warn = Math.min(dims.w, dims.h) < 400 ? "Ảnh hơi nhỏ, chữ có thể khó đọc. Nên chụp gần và rõ hơn." : "";
  return { kind, ...dims, warn };
}

const fmtSize = (n) => (n < 1024 * 1024 ? `${Math.round(n / 1024)} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`);

/* ---------------- Tải lên có % tiến độ (fetch không báo tiến độ nên dùng XHR) ---------------- */
function uploadWithProgress(path, file, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", API_BASE + path);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
    xhr.onerror = () => reject(new ApiError(0, "Không kết nối được máy chủ"));
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* không phải JSON */
      }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data);
      if (xhr.status === 401) logout();
      const err = data?.error;
      reject(new ApiError(xhr.status, err?.message ?? `Tải ảnh thất bại (${xhr.status})`, err?.details ?? null, err?.code ?? null));
    };
    const fd = new FormData();
    fd.append("file", file);
    xhr.send(fd);
  });
}

/* ---------------- Kiểu dáng (Pink & Lavender, chỉ trong .page-upload) ---------------- */
const CSS = `
.page-upload { --ink:#464052; --muted:#6f687c; --line:#e9ddf7; --mist:#f3edfb; --brand-dark:#7a62a3;
  --grad: linear-gradient(100deg,#f0b0c3 0%,#d9b5d9 50%,#b6a1d4 100%); color: var(--ink); }
.page-upload .page-title { font-size: clamp(1.8rem,3vw,2.3rem); font-weight: 800 !important; letter-spacing: -.03em; line-height: 1.15;
  background: linear-gradient(95deg,#464052 0%,#7a62a3 60%,#c27a9b 100%); -webkit-background-clip: text; background-clip: text; color: transparent !important; }
.page-upload .page-title-ico { width:46px; height:46px; border-radius:14px; display:grid; place-items:center; flex:none; background:var(--grad); color:var(--ink); box-shadow:0 8px 18px -12px rgba(182,161,212,.9); }
.page-upload .page-title-ico svg { width:24px; height:24px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
.page-upload .card { border:1px solid var(--line); border-radius:16px; }
.page-upload .btn-primary { background:var(--grad); border:0; color:var(--ink); font-weight:600; box-shadow:0 8px 18px -12px rgba(182,161,212,.9); }
.page-upload .btn-primary:hover, .page-upload .btn-primary:focus-visible { background:linear-gradient(100deg,#eba1b7 0%,#d1a8d2 50%,#a993cb 100%); color:var(--ink); }
.page-upload .btn-primary:disabled { background:var(--grad); color:var(--ink); opacity:.6; }
.page-upload .form-control:focus, .page-upload .form-select:focus { border-color:#b6a1d4; box-shadow:0 0 0 .2rem rgba(182,161,212,.35); }
.up-steps { display:flex; gap:8px; list-style:none; padding:0; margin:0 0 20px; counter-reset: s; flex-wrap: wrap; }
.up-steps li { display:flex; align-items:center; gap:8px; padding:6px 12px 6px 6px; border-radius:999px; background:#fff; border:1px solid var(--line); color:var(--muted); font-size:.875rem; }
.up-steps li::before { counter-increment:s; content:counter(s); width:24px; height:24px; border-radius:50%; display:grid; place-items:center; background:var(--mist); font-weight:700; font-size:.8rem; }
.up-steps li.active { color:var(--ink); font-weight:600; border-color:#d9c9ef; }
.up-steps li.active::before { background:var(--grad); }
.up-steps li.done::before { content:"✓"; background:#dff3ea; color:#2f7a5a; }
.drop { position:relative; display:grid; place-items:center; text-align:center; gap:6px; min-height:220px; padding:24px; border:2px dashed #d9c9ef;
  border-radius:16px; background:#faf8fd; cursor:pointer; transition:background .15s, border-color .15s; }
.drop:hover, .drop.drag { background:var(--mist); border-color:#b6a1d4; }
.drop.has-error { border-color:#e5a3b6; background:#fff6f8; }
.drop svg { width:44px; height:44px; fill:none; stroke:#b6a1d4; stroke-width:1.6; stroke-linecap:round; stroke-linejoin:round; }
.drop input { position:absolute; inset:0; opacity:0; cursor:pointer; }
.drop-err { color:#b0405f; font-weight:600; }
.preview { display:flex; gap:16px; align-items:flex-start; flex-wrap:wrap; }
.preview-img { position:relative; width:180px; max-width:100%; border-radius:12px; overflow:hidden; border:1px solid var(--line); background:#fff; flex:none; }
.preview-img img { display:block; width:100%; max-height:260px; object-fit:contain; }
.scan::after { content:""; position:absolute; left:0; right:0; height:36px; top:-36px;
  background:linear-gradient(180deg, rgba(182,161,212,0), rgba(182,161,212,.55), rgba(182,161,212,0)); animation: scan 1.6s ease-in-out infinite; }
@keyframes scan { to { top:100%; } }
.meta dt { font-weight:500; color:var(--muted); font-size:.8rem; } .meta dd { margin:0 0 8px; }
.proc { display:flex; gap:20px; align-items:center; flex-wrap:wrap; }
.proc-list { list-style:none; padding:0; margin:0; display:grid; gap:10px; }
.proc-list li { display:flex; align-items:center; gap:10px; color:var(--muted); }
.proc-list li.active { color:var(--ink); font-weight:600; }
.proc-list li.done { color:#2f7a5a; }
.proc-dot { width:22px; height:22px; border-radius:50%; display:grid; place-items:center; background:var(--mist); font-size:.75rem; flex:none; }
.proc-list li.done .proc-dot { background:#dff3ea; }
.progress { height:8px; border-radius:999px; background:var(--mist); }
.progress-bar { background:var(--grad); }
.notice { border-radius:14px; padding:14px 16px; display:flex; gap:12px; align-items:flex-start; }
.notice-ok { background:#effaf4; border:1px solid #c6e9d6; color:#24543d; }
.notice-fail { background:#fff4f6; border:1px solid #f3c6d2; color:#7d2f48; }
.notice-ico { font-size:1.25rem; line-height:1; }
.need { display:inline-block; margin-left:6px; padding:1px 8px; border-radius:999px; background:#fff1d6; color:#8a5a00; font-size:.72rem; font-weight:600; }
.items-table input { min-width:0; }
.items-table td { vertical-align: middle; }
.sum-box { background:#faf8fd; border:1px solid var(--line); border-radius:14px; padding:12px 16px; }
.sum-box .row-total { font-size:1.15rem; font-weight:800; }
@media (prefers-reduced-motion: reduce) { .scan::after { animation:none; } }
`;
function ensureStyles() {
  if (document.getElementById("upload-css")) return;
  const st = document.createElement("style");
  st.id = "upload-css";
  st.textContent = CSS;
  document.head.appendChild(st);
}

const ICON_RECEIPT = '<svg viewBox="0 0 24 24"><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9.5 8h5M9.5 12h5M9.5 16h3"/></svg>';
const ICON_UPLOAD = '<svg viewBox="0 0 24 24"><path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/></svg>';

/* ======================================================================= */

export function render(el, params) {
  ensureStyles();
  const state = { groupId: params.group ?? "", file: null, info: null, receipt: null, ocr: null, timer: null };

  el.innerHTML = `<div class="page-upload">
    <a href="#/receipts" class="d-inline-block mb-2" style="color:#7a62a3;text-decoration:none">‹ Danh sách hóa đơn</a>
    <div class="d-flex align-items-center gap-3 mb-3">
      <span class="page-title-ico" aria-hidden="true">${ICON_RECEIPT}</span>
      <div>
        <h2 class="page-title mb-0">Thêm hóa đơn</h2>
        <div class="text-muted">Chụp ảnh hóa đơn, hệ thống sẽ tự đọc các món và số tiền</div>
      </div>
    </div>
    <ol class="up-steps" aria-label="Các bước">
      <li data-step="1">Chọn ảnh</li><li data-step="2">Đọc hóa đơn</li><li data-step="3">Kiểm tra &amp; lưu</li>
    </ol>
    <div id="stage"></div>
  </div>`;
  const stage = el.querySelector("#stage");

  const setStep = (n) =>
    el.querySelectorAll(".up-steps li").forEach((li) => {
      const s = Number(li.dataset.step);
      li.classList.toggle("active", s === n);
      li.classList.toggle("done", s < n);
      if (s === n) li.setAttribute("aria-current", "step");
      else li.removeAttribute("aria-current");
    });

  // Rời trang khi đang đếm giây thì dừng bộ đếm
  const stopTimer = () => state.timer && clearInterval(state.timer);
  window.addEventListener("hashchange", stopTimer, { once: true });

  /* ---------- Bước 1: chọn nhóm + ảnh ---------- */
  async function stepPick() {
    setStep(1);
    let groups = [];
    try {
      groups = await get("/groups");
    } catch (e) {
      toast.error(e);
    }
    if (!groups.some((g) => String(g.id) === String(state.groupId))) state.groupId = groups[0]?.id ?? "personal";

    stage.innerHTML = `<div class="card"><div class="card-body">
      <form id="pick-form" novalidate>
        <div class="mb-3" style="max-width:380px">
          <label class="form-label" for="f-group">Hóa đơn của</label>
          <select class="form-select" id="f-group" name="group">
            ${groups.map((g) => `<option value="${g.id}" ${String(g.id) === String(state.groupId) ? "selected" : ""}>Nhóm: ${esc(g.name)}</option>`).join("")}
            <option value="personal" ${state.groupId === "personal" ? "selected" : ""}>Cá nhân (chỉ mình tôi xem)</option>
          </select>
        </div>
        <label class="form-label">Ảnh hóa đơn <span class="text-danger">*</span></label>
        <div class="drop" id="drop">
          <input type="file" id="f-file" accept="image/jpeg,image/png" aria-label="Chọn ảnh hóa đơn">
          <div>${ICON_UPLOAD}</div>
          <div class="fw-semibold">Kéo thả ảnh vào đây, hoặc bấm để chọn ảnh</div>
          <div class="text-muted small">JPG hoặc PNG, tối đa ${MAX_MB} MB. Trên điện thoại có thể chụp trực tiếp.</div>
          <div class="drop-err" id="drop-err" role="alert"></div>
        </div>
        <div id="preview" class="mt-3"></div>
        <div class="d-flex gap-2 mt-3">
          <button class="btn btn-primary" type="submit" id="btn-go" disabled>Tải lên &amp; đọc hóa đơn</button>
          <a class="btn btn-outline-secondary" href="#/receipts">Hủy</a>
        </div>
      </form>
    </div></div>`;

    const form = stage.querySelector("#pick-form");
    const drop = stage.querySelector("#drop");
    const input = stage.querySelector("#f-file");
    const errBox = stage.querySelector("#drop-err");
    const preview = stage.querySelector("#preview");
    const goBtn = stage.querySelector("#btn-go");

    form.elements.group.onchange = (e) => (state.groupId = e.target.value);

    const accept = async (file) => {
      errBox.textContent = "";
      drop.classList.remove("has-error");
      if (state.info?.url) URL.revokeObjectURL(state.info.url);
      state.file = null;
      state.info = null;
      goBtn.disabled = true;
      preview.innerHTML = "";
      const info = await checkImage(file);
      if (info.error) {
        errBox.textContent = info.error;
        drop.classList.add("has-error");
        return;
      }
      state.file = file;
      state.info = info;
      goBtn.disabled = false;
      preview.innerHTML = `<div class="preview">
        <div class="preview-img"><img src="${info.url}" alt="Ảnh hóa đơn đã chọn"></div>
        <dl class="meta mb-0">
          <dt>Tên file</dt><dd class="text-break">${esc(file.name)}</dd>
          <dt>Dung lượng</dt><dd>${fmtSize(file.size)} <span class="text-success">✓</span></dd>
          <dt>Định dạng · Kích thước</dt><dd>${info.kind.toUpperCase()} · ${info.w} × ${info.h} px <span class="text-success">✓</span></dd>
          ${info.warn ? `<dd class="text-warning-emphasis small">⚠ ${esc(info.warn)}</dd>` : ""}
          <dd><button type="button" class="btn btn-sm btn-outline-secondary" id="btn-change">Chọn ảnh khác</button></dd>
        </dl>
      </div>`;
      preview.querySelector("#btn-change").onclick = () => input.click();
    };

    input.onchange = () => input.files[0] && accept(input.files[0]);
    ["dragenter", "dragover"].forEach((t) =>
      drop.addEventListener(t, (e) => {
        e.preventDefault();
        drop.classList.add("drag");
      }),
    );
    ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("drag")));
    drop.addEventListener("drop", (e) => {
      e.preventDefault();
      const f = e.dataTransfer.files[0];
      if (f) accept(f);
    });

    form.onsubmit = (ev) => {
      ev.preventDefault();
      if (!state.file) {
        errBox.textContent = "Chọn ảnh hóa đơn";
        drop.classList.add("has-error");
        return;
      }
      stepProcess();
    };
  }

  /* ---------- Bước 2: tải lên + OCR ---------- */
  function processUI(withImage) {
    stage.innerHTML = `<div class="card"><div class="card-body">
      <div class="proc">
        ${withImage && state.info ? `<div class="preview-img scan" id="scan"><img src="${state.info.url}" alt="Ảnh hóa đơn đang xử lý"></div>` : ""}
        <div class="flex-grow-1" style="min-width:240px">
          <h5 class="mb-3" aria-live="polite" id="proc-title">Đang tải ảnh lên...</h5>
          <ul class="proc-list">
            <li id="p-up" class="active"><span class="proc-dot">1</span><span>Tải ảnh lên <span id="up-pct"></span></span></li>
            <li id="p-ocr"><span class="proc-dot">2</span><span>Đọc chữ trên hóa đơn (OCR) <span id="ocr-sec" class="text-muted"></span></span></li>
            <li id="p-parse"><span class="proc-dot">3</span><span>Nhận diện món, ngày, số tiền</span></li>
          </ul>
          <div class="progress mt-3" role="progressbar" aria-label="Tiến độ" aria-valuemin="0" aria-valuemax="100">
            <div class="progress-bar" id="bar" style="width:0%"></div>
          </div>
          <p class="text-muted small mt-2 mb-0">Có thể mất tới 30 giây. Vui lòng không đóng trang.</p>
        </div>
      </div>
    </div></div>`;
  }
  const mark = (id, cls) => {
    const li = stage.querySelector(`#${id}`);
    if (!li) return;
    li.className = cls;
    if (cls === "done") li.querySelector(".proc-dot").textContent = "✓";
  };

  async function stepProcess() {
    setStep(2);
    processUI(true);
    const bar = stage.querySelector("#bar");
    try {
      const path = state.groupId === "personal" ? "/receipts/personal" : `/groups/${state.groupId}/receipts`;
      state.receipt = await uploadWithProgress(path, state.file, (pct) => {
        stage.querySelector("#up-pct").textContent = `${pct}%`;
        bar.style.width = `${Math.round(pct * 0.3)}%`;
      });
    } catch (e) {
      // Lỗi khi tải: quay về bước 1, báo lỗi ngay dưới ô ảnh
      await stepPick();
      const errBox = stage.querySelector("#drop-err");
      errBox.textContent = e.message;
      stage.querySelector("#drop").classList.add("has-error");
      return;
    }
    mark("p-up", "done");
    await runOcr();
  }

  async function runOcr() {
    const title = stage.querySelector("#proc-title");
    const bar = stage.querySelector("#bar");
    const sec = stage.querySelector("#ocr-sec");
    title.textContent = "Đang đọc hóa đơn...";
    mark("p-ocr", "active");
    const started = Date.now();
    stopTimer();
    state.timer = setInterval(() => {
      const s = Math.floor((Date.now() - started) / 1000);
      sec.textContent = `· ${s} giây`;
      bar.style.width = `${Math.min(30 + s * 2.2, 92)}%`; // ước lượng, tối đa 92% cho tới khi xong
      if (s >= 4) mark("p-parse", "active");
    }, 500);
    try {
      state.ocr = await post(`/ocr/receipts/${state.receipt.id}`);
      state.receipt = state.ocr.receipt;
    } catch (e) {
      // Không chạy được OCR (lỗi server, mạng...) -> vẫn cho nhập tay
      state.ocr = { receipt: state.receipt, items: [], missing: Object.keys(FIELD_LABEL), warnings: [e.message], error: true };
    } finally {
      stopTimer();
    }
    bar.style.width = "100%";
    mark("p-ocr", "done");
    mark("p-parse", "done");
    await stepReview();
  }

  /* ---------- Bước 3: kiểm tra & lưu / nhập tay ---------- */
  async function stepReview() {
    setStep(3);
    stage.innerHTML = '<div class="card"><div class="card-body"><div class="text-muted">Đang tải hóa đơn...</div></div></div>';
    let detail;
    try {
      detail = await get(`/receipts/${state.receipt.id}`);
    } catch (e) {
      stage.innerHTML = `<div class="card"><div class="card-body">${emptyHTML(e.message)}</div></div>`;
      return;
    }
    if (detail.status !== "DRAFT" || !detail.can_edit_receipt) {
      stage.innerHTML = `<div class="card"><div class="card-body">
        <div class="notice notice-ok"><span class="notice-ico">ℹ</span><div>Hóa đơn này đã ${detail.status === "DRAFT" ? "không thể sửa bởi bạn" : "được xác nhận"}.</div></div>
        <a class="btn btn-primary mt-3" href="#/receipts${detail.group_id ? `?group=${detail.group_id}` : ""}">Về danh sách hóa đơn</a>
      </div></div>`;
      return;
    }
    const failed = detail.ocr_status !== "DONE";
    const missing = new Set(state.ocr?.missing ?? (failed ? Object.keys(FIELD_LABEL) : []));
    const warnings = state.ocr?.warnings ?? [];
    renderEditor(detail, { failed, missing, warnings });
  }

  function renderEditor(d, { failed, missing, warnings }) {
    const need = (k) => (missing.has(k) && !failed ? '<span class="need">Cần kiểm tra</span>' : "");
    const catOptions = [...new Set([...(d.category ? [d.category] : []), ...CATEGORIES])];
    const notice = failed
      ? `<div class="notice notice-fail mb-3" role="alert"><span class="notice-ico">✍</span><div>
           <div class="fw-semibold">Không đọc được hóa đơn từ ảnh, vui lòng nhập tay</div>
           <div class="small">Ảnh có thể bị mờ, nghiêng, thiếu sáng, hoặc máy chủ chưa cài công cụ đọc ảnh (OCR). Hóa đơn nháp vẫn được lưu, bạn chỉ cần điền các ô bên dưới.</div>
         </div></div>`
      : `<div class="notice notice-ok mb-3"><span class="notice-ico">✓</span><div>
           <div class="fw-semibold">Đã đọc xong hóa đơn</div>
           <div class="small">Kiểm tra lại các ô bên dưới, nhất là những ô có nhãn <span class="need">Cần kiểm tra</span>, rồi bấm Lưu.</div>
           ${warnings.length ? `<ul class="small mb-0 mt-1">${warnings.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}
         </div></div>`;

    stage.innerHTML = `<div class="card"><div class="card-body">
      ${notice}
      <form id="edit-form" novalidate>
        <div class="row g-3">
          <div class="col-md-6">
            <label class="form-label" for="f-merchant_name">Tên cửa hàng ${need("merchant_name")}</label>
            <input class="form-control" id="f-merchant_name" name="merchant_name" maxlength="255" placeholder="VD: Quán Phở Hòa" value="${esc(d.merchant_name ?? "")}">
            <div class="invalid-feedback"></div>
          </div>
          <div class="col-6 col-md-3">
            <label class="form-label" for="f-receipt_date">Ngày ${need("receipt_date")}</label>
            <input class="form-control" type="date" id="f-receipt_date" name="receipt_date" value="${esc(d.receipt_date ?? new Date().toISOString().slice(0, 10))}">
            <div class="invalid-feedback"></div>
          </div>
          <div class="col-6 col-md-3">
            <label class="form-label" for="f-category">Danh mục</label>
            <select class="form-select" id="f-category" name="category">
              ${catOptions.map((c) => `<option ${c === (d.category ?? "Ăn uống") ? "selected" : ""}>${esc(c)}</option>`).join("")}
            </select>
          </div>
        </div>

        <div class="d-flex justify-content-between align-items-end mt-4 mb-2">
          <label class="form-label mb-0">Danh sách món ${need("items")}</label>
          <button type="button" class="btn btn-sm btn-outline-secondary" id="btn-add-item">+ Thêm món</button>
        </div>
        <div class="table-responsive">
          <table class="table align-middle items-table mb-1">
            <thead class="table-light"><tr><th>Tên món</th><th style="width:90px">SL</th><th style="width:150px">Đơn giá</th><th class="text-end" style="width:130px">Thành tiền</th><th style="width:44px"></th></tr></thead>
            <tbody id="items"></tbody>
          </table>
        </div>
        <div class="invalid-feedback d-block mb-2" id="items-err"></div>

        <div class="row g-3 justify-content-end">
          <div class="col-6 col-md-3">
            <label class="form-label" for="f-tax_amount">Thuế</label>
            <input class="form-control text-end" id="f-tax_amount" name="tax_amount" inputmode="numeric" data-money value="${d.tax_amount ? formatNumber(d.tax_amount) : ""}" placeholder="0">
          </div>
          <div class="col-6 col-md-3">
            <label class="form-label" for="f-service_fee">Phí dịch vụ</label>
            <input class="form-control text-end" id="f-service_fee" name="service_fee" inputmode="numeric" data-money value="${d.service_fee ? formatNumber(d.service_fee) : ""}" placeholder="0">
          </div>
          <div class="col-md-5">
            <div class="sum-box">
              <div class="d-flex justify-content-between"><span>Tạm tính ${need("subtotal")}</span><span id="sum-sub">0 ₫</span></div>
              <div class="d-flex justify-content-between row-total mt-1"><span>Tổng cộng ${need("total_amount")}</span><span id="sum-total">0 ₫</span></div>
              ${!failed && d.total_amount != null ? `<div class="small text-muted mt-1">Tổng trên hóa đơn (OCR): ${formatVND(d.total_amount)}</div>` : ""}
            </div>
          </div>
        </div>

        <div class="d-flex flex-wrap gap-2 mt-4">
          <button class="btn btn-primary" type="submit">Lưu hóa đơn nháp</button>
          <a class="btn btn-outline-secondary" href="#/receipts${d.group_id ? `?group=${d.group_id}` : ""}">Để sau</a>
        </div>
      </form>
    </div></div>`;

    const form = stage.querySelector("#edit-form");
    const tbody = stage.querySelector("#items");
    const removed = new Set();

    const rowHTML = (it = {}) => `<tr data-id="${it.id ?? ""}">
      <td><input class="form-control form-control-sm" name="item_name" maxlength="255" placeholder="Tên món" value="${esc(it.item_name ?? "")}"></td>
      <td><input class="form-control form-control-sm text-end" name="quantity" type="number" min="0.01" step="0.01" value="${it.quantity != null ? Number(it.quantity) : 1}"></td>
      <td><input class="form-control form-control-sm text-end" name="unit_price" inputmode="numeric" data-money placeholder="0" value="${it.unit_price != null ? formatNumber(it.unit_price) : ""}"></td>
      <td class="text-end text-nowrap" data-line>0 ₫</td>
      <td><button type="button" class="btn btn-sm btn-link text-danger p-0" data-del aria-label="Xóa món">✕</button></td>
    </tr>`;

    const lineOf = (tr) => {
      const q = Number(tr.querySelector("[name=quantity]").value) || 0;
      return Math.round(q * parseVND(tr.querySelector("[name=unit_price]").value));
    };
    const recalc = () => {
      let sub = 0;
      tbody.querySelectorAll("tr").forEach((tr) => {
        const line = lineOf(tr);
        sub += line;
        tr.querySelector("[data-line]").textContent = formatVND(line);
      });
      const total = sub + parseVND(form.elements.tax_amount.value) + parseVND(form.elements.service_fee.value);
      stage.querySelector("#sum-sub").textContent = formatVND(sub);
      stage.querySelector("#sum-total").textContent = formatVND(total);
      return { sub, total };
    };
    const bindMoney = (root) =>
      root.querySelectorAll("input[data-money]").forEach((inp) => {
        inp.addEventListener("input", () => {
          const digits = inp.value.replace(/\D/g, "");
          inp.value = digits ? formatNumber(Number(digits)) : "";
        });
      });
    const addRow = (it) => {
      tbody.insertAdjacentHTML("beforeend", rowHTML(it));
      const tr = tbody.lastElementChild;
      bindMoney(tr);
      tr.querySelector("[data-del]").onclick = () => {
        if (tr.dataset.id) removed.add(Number(tr.dataset.id));
        tr.remove();
        recalc();
      };
      return tr;
    };

    (d.items?.length ? d.items : [{}]).forEach((it) => addRow(it));
    bindMoney(form);
    form.addEventListener("input", recalc);
    recalc();
    stage.querySelector("#btn-add-item").onclick = () => addRow().querySelector("[name=item_name]").focus();
    if (failed) form.elements.merchant_name.focus();

    form.onsubmit = async (ev) => {
      ev.preventDefault();
      clearFieldErrors(form);
      const itemsErr = stage.querySelector("#items-err");
      itemsErr.textContent = "";
      tbody.querySelectorAll(".is-invalid").forEach((i) => i.classList.remove("is-invalid"));

      // Kiểm tra các dòng món
      const rows = [...tbody.querySelectorAll("tr")].filter(
        (tr) => tr.querySelector("[name=item_name]").value.trim() || parseVND(tr.querySelector("[name=unit_price]").value),
      );
      let bad = false;
      rows.forEach((tr) => {
        const name = tr.querySelector("[name=item_name]");
        const qty = tr.querySelector("[name=quantity]");
        if (!name.value.trim()) (name.classList.add("is-invalid"), (bad = true));
        if (!(Number(qty.value) > 0)) (qty.classList.add("is-invalid"), (bad = true));
      });
      if (!rows.length) {
        itemsErr.textContent = "Nhập ít nhất một món (tên và đơn giá)";
        return;
      }
      if (bad) {
        itemsErr.textContent = "Kiểm tra lại các ô được đánh dấu đỏ trong danh sách món";
        return;
      }

      const { sub } = recalc();
      const tax = parseVND(form.elements.tax_amount.value);
      const fee = parseVND(form.elements.service_fee.value);
      const header = {
        merchant_name: form.elements.merchant_name.value.trim() || null,
        receipt_date: form.elements.receipt_date.value || null,
        category: form.elements.category.value,
        subtotal: sub,
        tax_amount: tax,
        service_fee: fee,
        total_amount: sub + tax + fee,
      };

      const btn = form.querySelector("[type=submit]");
      try {
        await withBusy(btn, async () => {
          for (const id of removed) await del(`/receipts/${d.id}/items/${id}`);
          removed.clear();
          for (const tr of rows) {
            const body = {
              item_name: tr.querySelector("[name=item_name]").value.trim(),
              quantity: Number(tr.querySelector("[name=quantity]").value),
              unit_price: parseVND(tr.querySelector("[name=unit_price]").value),
            };
            if (tr.dataset.id) await patch(`/receipts/${d.id}/items/${tr.dataset.id}`, body);
            else tr.dataset.id = (await post(`/receipts/${d.id}/items`, body)).id;
          }
          // Dòng trống (không tên, không giá) thì bỏ khỏi bảng
          [...tbody.querySelectorAll("tr")].filter((tr) => !rows.includes(tr)).forEach((tr) => tr.remove());
          await patch(`/receipts/${d.id}`, header);
        });
        stepDone(d);
      } catch (e) {
        if (e.details?.length) showFieldErrors(form, e.details);
        toast.error(e);
      }
    };
  }

  function stepDone(d) {
    setStep(4);
    const back = `#/receipts${d.group_id ? `?group=${d.group_id}` : ""}`;
    stage.innerHTML = `<div class="card"><div class="card-body text-center py-5">
      <div style="font-size:2.5rem">✅</div>
      <h4 class="mt-2">Đã lưu hóa đơn nháp</h4>
      <p class="text-muted">Hóa đơn đang ở trạng thái <b>Nháp</b>. Bước tiếp theo là chọn người trả và xác nhận hóa đơn.</p>
      <div class="d-flex flex-wrap gap-2 justify-content-center">
        <a class="btn btn-primary" href="${back}">Về danh sách hóa đơn</a>
        <button type="button" class="btn btn-outline-secondary" id="btn-again">Thêm hóa đơn khác</button>
      </div>
    </div></div>`;
    toast.success("Đã lưu hóa đơn nháp");
    stage.querySelector("#btn-again").onclick = () => {
      Object.assign(state, { file: null, info: null, receipt: null, ocr: null });
      stepPick();
    };
  }

  /* ---------- Bắt đầu: hóa đơn mới, hoặc mở lại hóa đơn nháp dang dở ---------- */
  if (params.receipt) {
    (async () => {
      try {
        state.receipt = await get(`/receipts/${encodeURIComponent(params.receipt)}`);
      } catch (e) {
        stage.innerHTML = `<div class="card"><div class="card-body">${emptyHTML(e.message, { actionText: "Về danh sách hóa đơn", actionHref: "#/receipts" })}</div></div>`;
        return;
      }
      if (state.receipt.status === "DRAFT" && state.receipt.ocr_status === "PENDING" && state.receipt.can_edit_receipt) {
        setStep(2);
        processUI(false);
        mark("p-up", "done");
        await runOcr();
      } else {
        await stepReview();
      }
    })();
  } else {
    stepPick();
  }
}
