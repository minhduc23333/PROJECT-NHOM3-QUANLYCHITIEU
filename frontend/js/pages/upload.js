// T05E175 - UI Tải ảnh & theo dõi trạng thái OCR (#/receipts/new)
// Bước 1: chọn nhóm + chọn ảnh (xem trước, kiểm tra định dạng/kích thước ngay trên trình duyệt)
// Bước 2: tải lên (có % tiến độ) -> chạy OCR (hiện đang xử lý, đếm giây)
// Bước 3: chuyển sang trang Kiểm tra & xác nhận #/receipts/:id (OCR thất bại -> nhập tay ở trang đó)
// Mở lại hóa đơn nháp dang dở: #/receipts/new?receipt=<id>
import { API_BASE, ApiError, get, post } from "../api.js";
import { getToken, logout } from "../auth.js";

import { navigate } from "../router.js";
import { emptyHTML, esc, toast } from "../ui.js";

export const MAX_MB = 5;
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
      <li data-step="1">Chọn ảnh</li><li data-step="2">Đọc hóa đơn</li><li data-step="3">Kiểm tra &amp; xác nhận</li>
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

  /* ---------- Bước 3: sang trang Kiểm tra & xác nhận (T05E176) ---------- */
  // OCR đọc được -> kiểm tra, sửa; OCR thất bại -> trang đó mở sẵn chế độ nhập tay
  const stepReview = () => navigate(`/receipts/${state.receipt.id}`);

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
