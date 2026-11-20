// T05E17B - UI-06: Chia hóa đơn (#/receipts/:id/split)
// Bảng món × thành viên có checkbox, đơn giá, tổng tạm tính từng người, tô nổi món chưa ai chọn,
// nút Chốt chia (chỉ Trưởng nhóm), hiển thị lý do không chốt được.
import { del, get, post, put } from "../api.js";
import { getUser } from "../auth.js";
import { formatNumber, formatVND } from "../format.js";
import { confirmDialog, emptyHTML, esc, toast, withBusy } from "../ui.js";

const STATUS = {
  DRAFT: { text: "Nháp", cls: "sp-st-draft" },
  VERIFIED: { text: "Đã xác nhận", cls: "sp-st-verified" },
  SETTLED: { text: "Đã chốt", cls: "sp-st-settled" },
};
const num = (v) => Number(v ?? 0) || 0;
const initials = (name = "") => {
  const p = String(name).trim().split(/\s+/).filter(Boolean);
  return p.length ? (p[0][0] + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase() : "?";
};

/** Lý do chưa chốt được, tính trước ở giao diện (backend vẫn kiểm tra lại). Tách riêng để dễ test. */
export function blockers({ status, payerId, memberIds, items, selectorsByItem, subtotal, total, fee }) {
  const out = [];
  if (status === "DRAFT") out.push({ kind: "draft", text: "Hóa đơn chưa được xác nhận. Cần kiểm tra & xác nhận trước khi chốt chia." });
  if (status === "SETTLED") return [];
  if (payerId == null || !memberIds.includes(payerId)) out.push({ kind: "payer", text: "Chưa có người ứng tiền, hoặc người đó không còn trong nhóm." });
  if (!items.length) out.push({ kind: "items", text: "Hóa đơn chưa có dòng món nào." });
  const free = items.filter((i) => !(selectorsByItem.get(i.id)?.length));
  if (free.length) out.push({ kind: "unselected", text: `Còn ${free.length} món chưa ai chọn: ${free.map((i) => i.item_name).join(", ")}.` });
  const itemsSum = items.reduce((s, i) => s + num(i.line_total), 0);
  if (items.length && subtotal != null && Math.round(num(subtotal)) !== Math.round(itemsSum))
    out.push({ kind: "subtotal", text: `Tạm tính ${formatVND(subtotal)} khác tổng các món ${formatVND(itemsSum)}.` });
  if (total == null) out.push({ kind: "total", text: "Hóa đơn chưa có tổng tiền." });
  else if (Math.round(num(total)) !== Math.round(itemsSum + fee))
    out.push({ kind: "total", text: `Tổng tiền ${formatVND(total)} khác tổng món + thuế + phí ${formatVND(itemsSum + fee)}.` });
  return out;
}

const CSS = `
.page-split { --ink:#464052; --muted:#6f687c; --line:#e9ddf7; --mist:#f3edfb; --brand-dark:#7a62a3;
  --grad: linear-gradient(100deg,#f0b0c3 0%,#d9b5d9 50%,#b6a1d4 100%); color: var(--ink); }
.page-split .page-title { font-size: clamp(1.6rem,3vw,2.1rem); font-weight:800 !important; letter-spacing:-.03em; line-height:1.15;
  background: linear-gradient(95deg,#464052 0%,#7a62a3 60%,#c27a9b 100%); -webkit-background-clip:text; background-clip:text; color:transparent !important; }
.page-split .card { border:1px solid var(--line); border-radius:16px; }
.page-split .btn-primary { background:var(--grad); border:0; color:var(--ink); font-weight:600; box-shadow:0 8px 18px -12px rgba(182,161,212,.9); }
.page-split .btn-primary:hover, .page-split .btn-primary:focus-visible { background:linear-gradient(100deg,#eba1b7 0%,#d1a8d2 50%,#a993cb 100%); color:var(--ink); }
.page-split .btn-primary:disabled { background:var(--grad); color:var(--ink); opacity:.5; }
.sp-badge { display:inline-block; padding:3px 10px; border-radius:999px; font-size:.78rem; font-weight:600; }
.sp-st-draft { background:#ece8f1; color:#5b5568; } .sp-st-verified { background:#e9ddf7; color:#5a4790; } .sp-st-settled { background:#fce4ec; color:#a0516e; }
.sp-facts { display:flex; flex-wrap:wrap; gap:8px 20px; color:var(--muted); font-size:.9rem; }
.sp-facts b { color:var(--ink); }
.notice { border-radius:14px; padding:12px 14px; display:flex; gap:10px; align-items:flex-start; }
.notice-info { background:var(--mist); border:1px solid var(--line); }
.notice-warn { background:#fff8ec; border:1px solid #f5dcae; color:#7a4e00; }
.notice-fail { background:#fff4f6; border:1px solid #f3c6d2; color:#7d2f48; }
.notice-ok { background:#effaf4; border:1px solid #c6e9d6; color:#24543d; }
.mx-wrap { overflow-x:auto; border:1px solid var(--line); border-radius:14px; background:#fff; }
.mx { border-collapse:separate; border-spacing:0; width:100%; min-width:560px; font-size:.92rem; }
.mx th, .mx td { padding:10px 12px; border-bottom:1px solid #f1ecf8; white-space:nowrap; vertical-align:middle; }
.mx thead th { background:#faf8fd; font-weight:600; color:var(--muted); }
.mx .c-item { position:sticky; left:0; background:#fff; z-index:1; min-width:180px; white-space:normal; }
.mx thead .c-item { background:#faf8fd; }
.mx .c-mem { text-align:center; min-width:96px; }
.mx .c-mem.me { background:#f7f2fd; }
.mx thead .c-mem.me { background:#efe6fa; }
.mx .c-num { text-align:right; }
.mx tr.free td { background:#fff6e5; }
.mx tr.free .c-item { background:#fff6e5; box-shadow: inset 4px 0 0 #f0b04a; }
.free-tag { display:inline-block; margin-left:6px; padding:1px 8px; border-radius:999px; background:#ffe3ad; color:#7a4e00; font-size:.72rem; font-weight:700; }
.mx tfoot td { background:#faf8fd; font-weight:600; border-bottom:0; }
.mx tfoot tr.grand td { font-size:1rem; font-weight:800; border-top:2px solid var(--line); }
.mx tfoot .c-item { background:#faf8fd; }
.mem-head { display:flex; flex-direction:column; align-items:center; gap:4px; }
.mem-ava { width:30px; height:30px; border-radius:50%; display:grid; place-items:center; font-size:.72rem; font-weight:700; background:#e9ddf7; color:#6c56a0; }
.c-mem.me .mem-ava { background:var(--grad); color:var(--ink); }
.mem-tag { font-size:.68rem; font-weight:600; color:var(--brand-dark); }
.mx input[type=checkbox] { width:20px; height:20px; accent-color:#a993cb; cursor:pointer; }
.mx input[type=checkbox]:disabled { cursor:default; opacity:.85; }
.mx .busy { opacity:.4; }
.tick { display:inline-grid; place-items:center; width:22px; height:22px; border-radius:6px; color:#c9c2d4; font-weight:700; }
.tick.on { background:#b6a1d4; color:#fff; }
.cnt { display:inline-block; min-width:22px; padding:0 6px; border-radius:999px; background:var(--mist); font-size:.75rem; font-weight:700; text-align:center; }
.reasons { margin:6px 0 0; padding-left:18px; }
.reasons li { margin:2px 0; }
.result-list { list-style:none; margin:0; padding:0; display:grid; gap:8px; }
.result-list li { display:flex; justify-content:space-between; gap:12px; padding:10px 12px; border:1px solid var(--line); border-radius:12px; background:#fff; }
.mx-section-title { margin:0 0 8px; font-size:1rem; font-weight:700; color:var(--ink); }
/* Chọn món theo thành viên: mỗi món một dòng, mỗi thành viên một "viên" (pill) */
.pk-legend { display:flex; flex-wrap:wrap; gap:12px; font-size:.8rem; color:var(--muted); align-items:center; }
.pk-legend .pill.demo { padding:1px 8px; font-size:.72rem; cursor:default; }
.pick-list { display:grid; gap:10px; }
.pick-row { display:grid; grid-template-columns: minmax(160px, 1.1fr) minmax(0, 2fr) 120px; gap:12px 16px; align-items:center;
  padding:12px 16px; border:1px solid var(--line); border-radius:14px; background:#fff; transition: box-shadow .15s; }
.pick-row:hover { box-shadow:0 8px 20px -16px rgba(122,98,163,.6); }
.pick-row.free { background:#fffaf0; border-color:#f5dcae; box-shadow: inset 4px 0 0 #f0b04a; }
.pick-name { font-weight:700; }
.pick-sub { font-size:.82rem; color:var(--muted); margin-top:2px; }
.pick-sub b { color:var(--ink); font-weight:600; }
.pick-members { display:flex; flex-wrap:wrap; gap:8px; }
.pick-split { text-align:right; font-size:.82rem; color:var(--muted); line-height:1.3; }
.pick-split b { color:var(--ink); font-size:1rem; }
.pick-split span { display:block; }
.pill { position:relative; display:inline-flex; align-items:center; gap:6px; padding:4px 12px 4px 4px; border-radius:999px;
  border:1.5px dashed #ddd3ea; background:#fff; color:#8a8296; font-size:.85rem; user-select:none; }
.pill .p-ava { width:24px; height:24px; border-radius:50%; display:grid; place-items:center; font-size:.68rem; font-weight:700; background:#f3eff8; color:#a39bb0; }
.pill.on { border-style:solid; border-color:#cdbbe6; background:#f4eefc; color:var(--ink); font-weight:600; }
.pill.on .p-ava { background:#b6a1d4; color:#fff; font-size:.8rem; }
.pill.me { cursor:pointer; border-color:#e3b8cb; }
.pill.me:hover { background:#fdf4f8; }
.pill.me.on { background:var(--grad); border-color:transparent; color:var(--ink); box-shadow:0 6px 14px -10px rgba(182,161,212,.9); }
.pill.me.on .p-ava { background:#fff; color:#7a62a3; }
.pill-input { position:absolute; opacity:0; width:1px; height:1px; pointer-events:none; }
.pill.me:focus-within { outline:3px solid rgba(182,161,212,.45); outline-offset:2px; }
.pill.busy, .pill:has(.busy) { opacity:.5; }
.pk-toolbar { display:flex; flex-wrap:wrap; gap:8px 16px; align-items:center; justify-content:space-between; }
.pk-seg { display:inline-flex; flex-wrap:wrap; border:1px solid var(--line); border-radius:10px; overflow:hidden; background:#fff; }
.pk-seg button { border:0; background:transparent; padding:5px 12px; font-size:.84rem; color:var(--ink); }
.pk-seg button[aria-pressed="true"] { background:var(--grad); font-weight:600; }
.pk-switch { display:inline-flex; align-items:center; gap:6px; font-size:.85rem; color:var(--muted); cursor:pointer; }
.pk-switch input { width:18px; height:18px; accent-color:#a993cb; }
.pill.more { border-style:solid; border-color:var(--line); background:var(--mist); color:var(--brand-dark); font-weight:600; padding:4px 12px; cursor:pointer; }
.pill.more:hover { background:#e9ddf7; }
.share-list { display:grid; gap:8px; }
.sl-row { display:grid; grid-template-columns: 34px minmax(140px, 220px) 1fr auto; gap:12px; align-items:center;
  padding:10px 14px; border:1px solid var(--line); border-radius:12px; background:#fff; }
.sl-row.me { background:linear-gradient(100deg,#fbf6ff 0%,#fff 70%); border-color:#d9c9ef; }
.sl-name { min-width:0; }
.sl-detail { font-size:.75rem; color:var(--muted); margin-top:4px; }
.sl-total { font-weight:800; font-size:1.05rem; white-space:nowrap; }
.share-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap:12px; }
.share-card { border:1px solid var(--line); border-radius:16px; background:#fff; padding:14px 16px; }
.share-card.me { background:linear-gradient(160deg,#fbf6ff 0%,#fff 70%); border-color:#d9c9ef; }
.share-total { font-size:1.4rem; font-weight:800; letter-spacing:-.02em; }
.share-bar { height:6px; border-radius:999px; background:#efeaf6; overflow:hidden; margin:6px 0 10px; }
.share-bar i { display:block; height:100%; background:linear-gradient(90deg,#f0b0c3,#b6a1d4); }
.share-rows { display:flex; justify-content:space-between; font-size:.82rem; color:var(--muted); padding:2px 0; }
.share-rows span:last-child { color:var(--ink); }
.share-sum { text-align:right; font-size:.85rem; color:var(--muted); }
@media (max-width: 767.98px) {
  .pick-row { grid-template-columns: 1fr auto; }
  .pick-members { grid-column: 1 / -1; order:3; }
  .pick-split { grid-column:2; grid-row:1; }
}
@media (max-width: 575.98px) {
  .mx-items-wrap { display:none; }
  .pill { font-size:.82rem; }
  .share-grid { grid-template-columns: 1fr 1fr; }
  .sl-row { grid-template-columns: 34px 1fr auto; }
  .sl-bar { grid-column: 1 / -1; grid-row: 2; }
  .sl-total { grid-column: 3; grid-row: 1; }
  .share-total { font-size:1.15rem; }
}
`;
function ensureStyles() {
  if (document.getElementById("split-css")) return;
  const st = document.createElement("style");
  st.id = "split-css";
  st.textContent = CSS;
  document.head.appendChild(st);
}

export function render(el, params) {
  ensureStyles();
  const id = params.id;
  const meId = getUser()?.id;
  el.innerHTML = `<div class="page-split"><div id="sp"><div class="text-muted p-3">Đang tải...</div></div></div>`;
  const box = el.querySelector("#sp");
  const st = { receipt: null, summary: null, group: null, error: null, result: null, debts: null };
  // Trạng thái hiển thị (không gửi lên server): lọc món, mở rộng dòng, kiểu xem phần tiền
  const ui = { filter: "all", showAll: false, expanded: new Set(), shareView: null };
  const MANY = 6; // từ 7 thành viên trở lên: gọn lại, ẩn bớt người chưa chọn

  async function load() {
    try {
      st.receipt = await get(`/receipts/${encodeURIComponent(id)}`);
      if (!st.receipt.group_id) {
        box.innerHTML = backLink() + `<div class="card"><div class="card-body">${emptyHTML("Hóa đơn cá nhân không cần chia tiền theo nhóm.", { actionText: "Về hóa đơn", actionHref: `#/receipts/${id}` })}</div></div>`;
        return;
      }
      [st.summary, st.group] = await Promise.all([get(`/receipts/${id}/selections`), get(`/groups/${st.receipt.group_id}`)]);
      st.debts = st.receipt.status === "SETTLED" ? await get(`/receipts/${id}/debts`).catch(() => null) : null;
    } catch (e) {
      box.innerHTML = backLink() + `<div class="card"><div class="card-body">${emptyHTML(e.message, { actionText: "Về danh sách hóa đơn", actionHref: "#/receipts" })}</div></div>`;
      return;
    }
    paint();
  }

  const backLink = () =>
    `<a href="#/receipts${st.receipt?.group_id ? `?group=${st.receipt.group_id}` : ""}" class="d-inline-block mb-2" style="color:#7a62a3;text-decoration:none">‹ Danh sách hóa đơn</a>`;

  function paint() {
    const r = st.receipt;
    const s = st.summary;
    const items = r.items ?? [];
    const members = s.members; // mọi thành viên ACTIVE, kể cả chưa chọn
    const memberIds = members.map((m) => m.user_id);
    const isLeader = st.group?.my_role === "LEADER";
    const settled = r.status === "SETTLED";
    const canSelect = s.can_select && memberIds.includes(meId);
    const fee = num(s.fee_total);
    const selectorsByItem = new Map(items.map((i) => [i.id, members.filter((m) => m.selected_item_ids.includes(i.id))]));
    const freeIds = new Set(s.unselected_items.map((u) => u.id));
    const payer = members.find((m) => m.user_id === r.payer_id);
    const roleOf = new Map((st.group?.members ?? []).map((m) => [m.user_id, m.role]));
    const reasons = blockers({ status: r.status, payerId: r.payer_id, memberIds, items, selectorsByItem, subtotal: r.subtotal, total: r.total_amount, fee });
    const sumShares = members.reduce((t, m) => t + num(m.total), 0);
    const itemsSum = items.reduce((t, item) => t + num(item.line_total), 0);
    const statusInfo = STATUS[r.status] ?? { text: r.status, cls: "" };
    // Sau khi chốt: số tiền thật lấy từ công nợ (người ứng tiền nhận phần lẻ làm tròn = tổng - phần người khác)
    const finalOf = new Map();
    if (settled && st.debts?.items) {
      const owed = st.debts.items.reduce((t, d) => t + num(d.amount), 0);
      st.debts.items.forEach((d) => finalOf.set(d.debtor_id, num(d.amount)));
      finalOf.set(r.payer_id, num(r.total_amount) - owed);
    }
    const shareOf = (m) => finalOf.get(m.user_id) ?? num(m.total);
    const sumShown = members.reduce((t, m) => t + shareOf(m), 0);

    // Cột thành viên: tôi đứng đầu, sau đó người ứng tiền, rồi theo tên
    const cols = [...members].sort(
      (a, b) => (b.user_id === meId) - (a.user_id === meId) || (b.user_id === r.payer_id) - (a.user_id === r.payer_id) || a.full_name.localeCompare(b.full_name, "vi"),
    );
    const many = cols.length > MANY;
    const shareView = ui.shareView ?? (many ? "list" : "cards");
    const shownItems = items.filter((i) =>
      ui.filter === "mine" ? selectorsByItem.get(i.id).some((m) => m.user_id === meId) : ui.filter === "free" ? freeIds.has(i.id) : true,
    );
    // Phần tiền: tôi đứng đầu, sau đó ai nhiều tiền hơn đứng trước
    const shareOrder = [...cols].sort((a, b) => (b.user_id === meId) - (a.user_id === meId) || shareOf(b) - shareOf(a));
    const maxShare = Math.max(1, ...cols.map((m) => shareOf(m)));

    let notice = "";
    if (settled)
      notice = `<div class="notice notice-ok mb-3"><span>🔒</span><div><b>Hóa đơn đã chốt chia.</b> Các khoản nợ đã được tạo, không chọn món được nữa.</div></div>`;
    else if (r.status === "DRAFT")
      notice = `<div class="notice notice-warn mb-3"><span>⚠</span><div>Hóa đơn đang là <b>Nháp</b>. Mọi người vẫn tick món được, nhưng phải <a href="#/receipts/${r.id}">kiểm tra & xác nhận</a> trước khi chốt.</div></div>`;
    else
      notice = `<div class="notice notice-info mb-3"><span>ℹ</span><div>Mỗi người bấm nút <b>Tôi</b> ở <b>các món mình đã dùng</b>. Nhiều người cùng tick một món thì món đó được <b>chia đều</b>. Thuế và phí chia theo tỉ lệ tiền món.</div></div>`;

    const errorBox = st.error
      ? `<div class="notice notice-fail mb-3" role="alert" id="sp-error"><span>✕</span><div><b>${esc(st.error.message)}</b>
          ${st.error.details?.length ? `<ul class="reasons">${st.error.details.map((d) => `<li>${esc(d.message)}</li>`).join("")}</ul>` : ""}</div></div>`
      : "";

    const result = settled
      ? `<div class="card mt-3"><div class="card-body">
          <h5 class="mb-3">Kết quả chia</h5>
          <ul class="result-list">${cols
            .map((m) => `<li><span>${esc(m.full_name)}${m.user_id === r.payer_id ? ' <span class="mem-tag">· người ứng tiền</span>' : ""}</span><b>${formatVND(shareOf(m))}</b></li>`)
            .join("")}</ul>
          ${st.debts?.items?.length
            ? `<h6 class="mt-4 mb-2">Công nợ phát sinh</h6><ul class="result-list">${st.debts.items
                .map((d) => `<li><span>${esc(d.debtor_name)} → ${esc(d.creditor_name)}</span><b>${formatVND(d.amount)}</b></li>`)
                .join("")}</ul>`
            : ""}
        </div></div>`
      : "";

    box.innerHTML = `
      ${backLink()}
      <div class="d-flex flex-wrap align-items-center gap-2 mb-1">
        <h2 class="page-title mb-0">Chia hóa đơn</h2>
        <span class="sp-badge ${statusInfo.cls}" title="${esc(r.status)}">${statusInfo.text}</span>
        <button type="button" class="btn btn-sm btn-outline-secondary ms-auto" id="btn-reload" title="Xem lựa chọn mới nhất của mọi người">↻ Làm mới</button>
      </div>
      <div class="sp-facts mb-3">
        <span>${esc(r.merchant_name || "Hóa đơn chưa có tên")}</span>
        <span>Nhóm: <b>${esc(st.group?.name ?? "")}</b></span>
        <span>Tổng: <b>${formatVND(r.total_amount)}</b></span>
        <span>Thuế + phí: <b>${formatVND(fee)}</b></span>
        <span>Người ứng tiền: <b>${payer ? esc(payer.full_name) : "chưa chọn"}</b></span>
        <a href="#/receipts/${r.id}" style="color:#7a62a3">Xem / sửa hóa đơn</a>
      </div>
      ${notice}
      ${errorBox}

      <div class="mx-wrap mx-items-wrap mb-3">
        <table class="mx mx-items">
          <thead><tr>
            <th class="c-item" scope="col">Món</th>
            <th class="c-num" scope="col">SL</th>
            <th class="c-num" scope="col">Đơn giá</th>
            <th class="c-num" scope="col">Thành tiền</th>
          </tr></thead>
          <tbody>${items
            .map((i) => {
              const free = freeIds.has(i.id);
              return `<tr class="${free ? "free" : ""}">
                <th class="c-item" scope="row">${esc(i.item_name)}${free ? '<span class="free-tag">Chưa ai chọn</span>' : ""}</th>
                <td class="c-num">${formatNumber(i.quantity)}</td>
                <td class="c-num">${formatVND(i.unit_price)}</td>
                <td class="c-num">${formatVND(i.line_total)}</td>
              </tr>`;
            })
            .join("")}</tbody>
          <tfoot><tr class="grand">
            <td class="c-item" colspan="3">Tổng tiền món</td><td class="c-num">${formatVND(itemsSum)}</td>
          </tfoot>
        </table>
      </div>

      <div class="d-flex flex-wrap justify-content-between align-items-end gap-2 mb-2">
        <h3 class="mx-section-title mb-0">Chọn món theo thành viên</h3>
        <div class="pk-legend">
          ${canSelect ? '<span><span class="pill me on demo">✓ Tôi</span> bấm để chọn / bỏ</span>' : ""}
          <span><span class="pill on demo">✓</span> đã chọn</span>
          <span><span class="pill demo">–</span> chưa chọn</span>
        </div>
      </div>
      <div class="pk-toolbar mb-2">
        <div class="pk-seg" role="group" aria-label="Lọc món">
          ${[["all", `Tất cả (${items.length})`], ["mine", `Tôi đã chọn (${items.filter((i) => selectorsByItem.get(i.id).some((m) => m.user_id === meId)).length})`], ["free", `Chưa ai chọn (${freeIds.size})`]]
            .map(([k, t]) => `<button type="button" data-filter="${k}" aria-pressed="${ui.filter === k}">${t}</button>`).join("")}
        </div>
        ${many ? `<label class="pk-switch"><input type="checkbox" id="pk-showall" ${ui.showAll ? "checked" : ""}> Hiện cả người chưa chọn</label>` : ""}
      </div>
      <div class="pick-list mb-4">${shownItems.length ? "" : `<div class="text-muted text-center p-3 pick-row" style="display:block">${ui.filter === "free" ? "Món nào cũng đã có người chọn 🎉" : "Bạn chưa chọn món nào."}</div>`}${shownItems
        .map((i) => {
          const free = freeIds.has(i.id);
          const who = selectorsByItem.get(i.id);
          const each = who.length ? num(i.line_total) / who.length : 0;
          const open = !many || ui.showAll || ui.expanded.has(i.id);
          const hidden = open ? 0 : cols.filter((m) => m.user_id !== meId && !who.some((x) => x.user_id === m.user_id)).length;
          const pills = cols
            .map((m) => {
              const on = who.some((x) => x.user_id === m.user_id);
              const mine = m.user_id === meId;
              if (!open && !on && !mine) return ""; // gọn: ẩn người chưa chọn (trừ nút của tôi)
              const name = mine ? "Tôi" : m.full_name;
              const ava = `<span class="p-ava" aria-hidden="true">${on ? "✓" : esc(initials(m.full_name))}</span>`;
              if (mine && canSelect)
                return `<label class="pill me ${on ? "on" : ""}" title="${on ? "Bỏ chọn" : "Chọn"} món này">
                  <input type="checkbox" class="pill-input" data-item="${i.id}" ${on ? "checked" : ""} aria-label="Tôi đã dùng ${esc(i.item_name)}">${ava}<span>${esc(name)}</span></label>`;
              return `<span class="pill ${mine ? "me" : ""} ${on ? "on" : ""}" title="${esc(m.full_name)} ${on ? "đã chọn" : "chưa chọn"}">${ava}<span>${esc(name)}</span></span>`;
            })
            .join("");
          return `<div class="pick-row ${free ? "free" : ""}">
            <div class="pick-item">
              <div class="pick-name">${esc(i.item_name)}${free ? '<span class="free-tag">Chưa ai chọn</span>' : ""}</div>
              <div class="pick-sub">${formatNumber(i.quantity)} × ${formatVND(i.unit_price)} = <b>${formatVND(i.line_total)}</b></div>
            </div>
            <div class="pick-members">${pills}${hidden ? `<button type="button" class="pill more" data-expand="${i.id}" title="Xem những người chưa chọn món này">+${hidden} chưa chọn</button>` : ""}${many && !ui.showAll && ui.expanded.has(i.id) ? `<button type="button" class="pill more" data-collapse="${i.id}">Thu gọn</button>` : ""}</div>
            <div class="pick-split">${who.length ? `<b>${who.length}</b> người<span>${formatVND(Math.round(each))}/người</span>` : '<span class="text-warning-emphasis">Chưa chia</span>'}</div>
          </div>`;
        })
        .join("")}</div>

      <div class="d-flex flex-wrap justify-content-between align-items-end gap-2 mb-2">
        <h3 class="mx-section-title mb-0">${settled ? "Số tiền mỗi người (đã chốt)" : "Tạm tính mỗi người"}</h3>
        <div class="pk-seg" role="group" aria-label="Kiểu xem">
          <button type="button" data-share="list" aria-pressed="${shareView === "list"}">Danh sách</button>
          <button type="button" data-share="cards" aria-pressed="${shareView === "cards"}">Thẻ</button>
        </div>
      </div>
      ${shareView === "list" ? `<div class="share-list mb-2">${shareOrder
        .map((m) => {
          const share = shareOf(m);
          const pct = num(r.total_amount) ? (share / num(r.total_amount)) * 100 : 0;
          const tags = [m.user_id === meId ? "Tôi" : "", m.user_id === r.payer_id ? "Ứng tiền" : "", roleOf.get(m.user_id) === "LEADER" ? "Trưởng nhóm" : ""].filter(Boolean);
          return `<div class="sl-row ${m.user_id === meId ? "me" : ""}">
            <span class="mem-ava" aria-hidden="true">${esc(initials(m.full_name))}</span>
            <div class="sl-name"><div class="fw-semibold text-truncate">${esc(m.full_name)}</div>${tags.length ? `<div class="mem-tag">${tags.join(" · ")}</div>` : ""}</div>
            <div class="sl-bar"><div class="share-bar m-0"><i style="width:${Math.min(100, (share / maxShare) * 100)}%"></i></div>
              <div class="sl-detail">Món ${formatVND(m.item_amount)} · Thuế/phí ${formatVND(m.fee_amount)} · ${Math.round(pct)}%</div></div>
            <div class="sl-total">${formatVND(share)}</div>
          </div>`;
        })
        .join("")}</div>` : `<div class="share-grid mb-2">${shareOrder
        .map((m) => {
          const share = shareOf(m);
          const pct = num(r.total_amount) ? Math.round((share / num(r.total_amount)) * 100) : 0;
          const tags = [m.user_id === meId ? "Tôi" : "", m.user_id === r.payer_id ? "Ứng tiền" : "", roleOf.get(m.user_id) === "LEADER" ? "Trưởng nhóm" : ""].filter(Boolean);
          return `<div class="share-card ${m.user_id === meId ? "me" : ""}">
            <div class="d-flex align-items-center gap-2 mb-2">
              <span class="mem-ava" aria-hidden="true">${esc(initials(m.full_name))}</span>
              <div style="min-width:0"><div class="fw-semibold text-truncate">${esc(m.full_name)}</div>${tags.length ? `<div class="mem-tag">${tags.join(" · ")}</div>` : ""}</div>
            </div>
            <div class="share-total">${formatVND(share)}</div>
            <div class="share-bar"><i style="width:${Math.min(100, pct)}%"></i></div>
            <div class="share-rows"><span>Tiền món</span><span>${formatVND(m.item_amount)}</span></div>
            <div class="share-rows"><span>Thuế + phí</span><span>${formatVND(m.fee_amount)}</span></div>
            <div class="share-rows"><span>Tỉ lệ</span><span>${pct}%</span></div>
          </div>`;
        })
        .join("")}</div>`}
      <div class="share-sum mb-3">Tổng các phần: <b>${formatVND(sumShown)}</b> / hóa đơn ${formatVND(r.total_amount)}</div>

      ${settled ? "" : `<div class="card"><div class="card-body d-flex flex-wrap gap-3 align-items-center">
        <div class="flex-grow-1" style="min-width:240px">
          ${reasons.length
            ? `<div class="fw-semibold">Chưa đủ điều kiện chốt:</div><ul class="reasons small mb-0">${reasons.map((x) => `<li>${esc(x.text)}</li>`).join("")}</ul>`
            : `<div class="fw-semibold" style="color:#2f7a5a">✓ Đủ điều kiện chốt chia</div><div class="small text-muted">Tổng tạm tính các thành viên: ${formatVND(sumShares)} / ${formatVND(r.total_amount)}${Math.round(num(r.total_amount) - sumShares) > 0 ? ` (phần lẻ ${formatVND(num(r.total_amount) - sumShares)} do làm tròn sẽ tính cho người ứng tiền)` : ""}</div>`}
        </div>
        ${isLeader
          ? `<button type="button" class="btn btn-primary btn-lg" id="btn-finalize">Chốt chia</button>`
          : `<div class="small text-muted">Chỉ <b>Trưởng nhóm</b> mới chốt chia được.</div>`}
      </div></div>`}
      ${result}`;

    /* ----- Tick / bỏ tick món của tôi ----- */
    box.querySelectorAll("input[data-item]").forEach((cb) => {
      cb.onchange = async () => {
        const itemId = cb.dataset.item;
        const scrollLeft = [...box.querySelectorAll(".mx-wrap")].map((wrap) => wrap.scrollLeft);
        const scrollTop = window.scrollY;
        box.querySelectorAll(`input[data-item="${itemId}"]`).forEach((x) => (x.disabled = true, x.classList.add("busy")));
        try {
          st.summary = cb.checked
            ? await put(`/receipts/${id}/items/${itemId}/selection`)
            : await del(`/receipts/${id}/items/${itemId}/selection`);
          st.error = null;
        } catch (e) {
          toast.error(e);
          if (e.status === 409) return load(); // vừa có người chốt -> tải lại
        }
        paint();
        requestAnimationFrame(() => {
          box.querySelectorAll(".mx-wrap").forEach((wrap, index) => (wrap.scrollLeft = scrollLeft[index] ?? 0));
          window.scrollTo(0, scrollTop);
          const target = box.querySelector(`.pick-list input[data-item="${itemId}"]`);
          target?.focus({ preventScroll: true });
        });
      };
    });
    box.querySelectorAll("[data-filter]").forEach((b) => (b.onclick = () => ((ui.filter = b.dataset.filter), paint())));
    box.querySelectorAll("[data-expand]").forEach((b) => (b.onclick = () => (ui.expanded.add(Number(b.dataset.expand)), paint())));
    box.querySelectorAll("[data-collapse]").forEach((b) => (b.onclick = () => (ui.expanded.delete(Number(b.dataset.collapse)), paint())));
    box.querySelectorAll("[data-share]").forEach((b) => (b.onclick = () => ((ui.shareView = b.dataset.share), paint())));
    box.querySelector("#pk-showall")?.addEventListener("change", (e) => ((ui.showAll = e.target.checked), paint()));
    box.querySelector("#btn-reload").onclick = () => {
      st.error = null;
      load();
    };

    /* ----- Chốt chia (Trưởng nhóm) ----- */
    box.querySelector("#btn-finalize")?.addEventListener("click", async (ev) => {
      const btn = ev.currentTarget;
      const ok = await confirmDialog({
        title: "Chốt chia hóa đơn?",
        message: reasons.length
          ? `Còn ${reasons.length} vấn đề, hệ thống có thể từ chối. Sau khi chốt, công nợ được tạo và không chọn món được nữa.`
          : "Sau khi chốt, công nợ được tạo cho từng người và không chọn món được nữa.",
        okText: "Chốt chia",
      });
      if (!ok) return;
      try {
        await withBusy(btn, () => post(`/receipts/${id}/split`));
        st.error = null;
        toast.success("Đã chốt chia hóa đơn");
        await load();
      } catch (e) {
        // 422: liệt kê từng lý do; 409: sai trạng thái / đã chốt; 403: không phải Trưởng nhóm
        st.error = { message: e.message, details: e.details };
        paint();
        box.querySelector("#sp-error")?.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  }

  load();
}
