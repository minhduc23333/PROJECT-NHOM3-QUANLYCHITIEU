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
export function blockers({ status, payerId, memberIds, items, selectorsByItem, subtotal, total, fee, discount = 0 }) {
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
  const expectedTotal = itemsSum + fee - discount;
  if (total == null) out.push({ kind: "total", text: "Hóa đơn chưa có tổng tiền." });
  else if (Math.round(num(total)) !== Math.round(expectedTotal))
    out.push({ kind: "total", text: `Tổng tiền ${formatVND(total)} khác tổng món + thuế + phí${discount ? " − giảm giá" : ""} ${formatVND(expectedTotal)}.` });
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
.page-split { --line:#e7e1ef; --mist:#f7f4fb; }
.sp-header { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:16px; align-items:center; padding:4px 0 16px; }
.sp-header-main { min-width:0; }
.sp-header-title { display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
.sp-header-title .page-title { font-size:clamp(1.45rem,2.4vw,1.8rem); }
.sp-merchant { margin-top:3px; font-size:1.05rem; font-weight:650; overflow-wrap:anywhere; }
.sp-header-meta { display:flex; flex-wrap:wrap; gap:4px 14px; margin-top:5px; color:var(--muted); font-size:.84rem; }
.sp-header-meta b { color:var(--ink); }
.sp-header-actions { display:flex; flex-wrap:wrap; align-items:center; justify-content:flex-end; gap:8px; }
.sp-header-actions .btn { white-space:nowrap; }
.sp-summary { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); margin-bottom:16px; border:1px solid var(--line); border-radius:14px; background:#fff; }
.sp-metric { min-width:0; padding:12px 16px; }
.sp-metric + .sp-metric { border-left:1px solid var(--line); }
.sp-metric-label { color:var(--muted); font-size:.78rem; }
.sp-metric-value { margin-top:3px; font-size:1.05rem; font-weight:750; font-variant-numeric:tabular-nums; overflow-wrap:anywhere; }
.sp-layout { display:grid; grid-template-columns:minmax(0,7fr) minmax(290px,3fr); gap:18px; align-items:start; }
.sp-main, .sp-sidebar { min-width:0; }
.sp-sidebar { position:sticky; top:1rem; }
.sp-panel { border:1px solid var(--line); border-radius:14px; background:#fff; }
.sp-panel + .sp-panel { margin-top:12px; }
.sp-panel-head { display:flex; justify-content:space-between; align-items:center; gap:10px; padding:14px 16px 10px; }
.sp-panel-body { padding:0 16px 16px; }
.sp-panel-title { margin:0; font-size:1rem; font-weight:750; }
.sp-items-head { display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:8px; margin-bottom:10px; }
.sp-items-count { color:var(--muted); font-size:.84rem; }
.sp-jump { padding:0; border:0; background:none; color:var(--brand-dark); font-weight:650; text-decoration:underline; text-underline-offset:2px; }
.sp-jump:hover { color:#56417f; }
.sp-tip { margin:0 0 12px; color:var(--muted); font-size:.82rem; }
.sp-tip summary, .sp-member-details summary, .sp-debts summary { width:max-content; cursor:pointer; color:var(--brand-dark); font-weight:600; }
.sp-tip[open] > div { padding:8px 0 0; }
.pk-toolbar { margin-bottom:10px; }
.pk-seg button { min-height:36px; }
.pk-seg button:focus-visible, .sp-jump:focus-visible, .sp-tip summary:focus-visible,
.sp-member-details summary:focus-visible, .sp-debts summary:focus-visible {
  outline:3px solid rgba(122,98,163,.35); outline-offset:2px; border-radius:5px;
}
.pick-list { gap:7px; margin-bottom:0 !important; }
.pick-row { grid-template-columns:minmax(130px,1fr) minmax(0,1.5fr) minmax(95px,auto); gap:8px 12px; padding:10px 12px; border-radius:12px; }
.pick-row:hover { box-shadow:none; border-color:#d5c9e6; }
.pick-row.free { border-color:#f0d7a4; }
.pick-name { display:flex; flex-wrap:wrap; align-items:center; gap:4px 8px; }
.pick-sub { margin-top:3px; font-size:.78rem; }
.pick-split { font-size:.78rem; }
.pick-split b { font-size:.92rem; }
.sp-item-status { display:inline-flex; align-items:center; gap:4px; padding:2px 7px; border-radius:999px; background:#f0edf4; color:#5f586b; font-size:.69rem; font-weight:650; white-space:nowrap; }
.sp-item-status.chosen { background:#eee8f8; color:#5c4786; }
.sp-item-status.shared { background:#f6eaf1; color:#793e61; }
.sp-item-status.free { background:#fff0cf; color:#704b08; }
.pk-legend { gap:7px 10px; font-size:.75rem; }
.pk-legend .pill.demo { padding:1px 6px; }
.sp-share-head { padding-bottom:12px; }
.sp-share-head .pk-seg { flex:none; }
.sp-share-list { display:grid; gap:4px; }
.sl-row { grid-template-columns:32px minmax(0,1fr) auto; gap:8px 10px; padding:9px 10px; border:0; border-bottom:1px solid #f1edf5; border-radius:0; }
.sl-row:last-child { border-bottom:0; }
.sl-row.me { border-radius:9px; }
.sl-total { font-size:.95rem; }
.sl-details { grid-column:2 / -1; margin-top:-4px; font-size:.78rem; }
.sl-details summary { width:max-content; cursor:pointer; color:var(--brand-dark); }
.sl-details .sl-detail { margin-top:4px; }
.share-grid { grid-template-columns:1fr; gap:6px; margin-bottom:0 !important; }
.share-card { display:grid; grid-template-columns:minmax(0,1fr) auto; gap:4px 8px; padding:10px 12px; border:0; border-bottom:1px solid #f1edf5; border-radius:0; }
.share-card.me { border-radius:9px; }
.share-card > .d-flex { grid-column:1; grid-row:1; margin:0 !important; }
.share-card > .share-total { grid-column:2; grid-row:1; align-self:center; font-size:.95rem; }
.share-card > .share-bar { display:none; }
.share-card > .sp-member-details { grid-column:1 / -1; font-size:.78rem; }
.share-rows { padding:2px 0; }
.sp-allocation { padding:14px 16px; }
.sp-allocation-total { display:flex; justify-content:space-between; align-items:baseline; gap:8px; font-size:.84rem; color:var(--muted); }
.sp-allocation-total b { color:var(--ink); font-size:1rem; font-variant-numeric:tabular-nums; }
.sp-allocation-bar { height:6px; margin:8px 0; overflow:hidden; border-radius:999px; background:#eee9f4; }
.sp-allocation-bar i { display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,#d9b5d9,#9b83bc); }
.sp-allocation-note { color:var(--muted); font-size:.78rem; }
.sp-finalize { padding:14px 16px; }
.sp-finalize-status { display:flex; align-items:flex-start; gap:8px; font-size:.9rem; font-weight:700; }
.sp-finalize-status.ok { color:#286348; }
.sp-finalize-status.blocked { color:var(--ink); }
.sp-finalize-details { margin-top:6px; font-size:.8rem; }
.sp-finalize-details summary { cursor:pointer; color:var(--brand-dark); }
.sp-finalize-details ul { padding-left:18px; margin:6px 0 0; color:var(--muted); }
.sp-finalize .btn { width:100%; margin-top:12px; }
.sp-debts { margin-top:12px; padding-top:10px; border-top:1px solid var(--line); font-size:.84rem; }
.sp-debts .result-list { margin-top:8px; gap:5px; }
.sp-debts .result-list li { padding:8px 10px; border-radius:9px; }
.sp-share-sum { margin-top:8px; color:var(--muted); font-size:.78rem; text-align:right; }
.sp-error { margin-bottom:12px; }
.sp-notice { margin-bottom:12px !important; padding:9px 12px; font-size:.86rem; }
@media (max-width: 991.98px) {
  .sp-layout { grid-template-columns:minmax(0,1fr); gap:14px; }
  .sp-sidebar { position:static; }
}
@media (max-width: 767.98px) {
  .sp-header { grid-template-columns:1fr; gap:10px; }
  .sp-header-actions { justify-content:flex-start; }
  .pick-row { grid-template-columns:minmax(0,1fr) auto; }
  .pick-members { grid-column:1 / -1; order:3; }
  .pick-split { grid-column:2; grid-row:1; }
}
@media (max-width: 575.98px) {
  .sp-summary { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .sp-metric { padding:10px 12px; }
  .sp-metric:first-child { grid-column:1 / -1; border-bottom:1px solid var(--line); }
  .sp-metric + .sp-metric { border-left:0; }
  .sp-metric:last-child { border-left:1px solid var(--line); }
  .sp-header-actions .btn { flex:1 1 auto; }
  .sp-panel-head, .sp-panel-body, .sp-allocation, .sp-finalize { padding-left:12px; padding-right:12px; }
  .pk-seg { width:100%; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); }
  .pk-seg button { padding:5px 6px; font-size:.77rem; }
  .pk-legend { display:none; }
  .pick-row { grid-template-columns:minmax(0,1fr); }
  .pick-split { grid-column:1; grid-row:auto; text-align:left; }
  .pick-split span { display:inline; margin-left:5px; }
  .pick-members { grid-column:1; }
  .sp-share-head { align-items:flex-start; flex-direction:column; }
  .sp-share-head .pk-seg { width:auto; display:inline-flex; }
  .sp-share-head .pk-seg button { padding:4px 10px; }
  .share-card { padding:8px; }
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
    const canManageSelections = canSelect && isLeader;
    const fee = num(s.fee_total);
    const discount = num(s.discount_amount ?? r.discount_amount);
    const selectorsByItem = new Map(items.map((i) => [i.id, members.filter((m) => m.selected_item_ids.includes(i.id))]));
    const freeIds = new Set(s.unselected_items.map((u) => u.id));
    const payer = members.find((m) => m.user_id === r.payer_id);
    const roleOf = new Map((st.group?.members ?? []).map((m) => [m.user_id, m.role]));
    const reasons = blockers({ status: r.status, payerId: r.payer_id, memberIds, items, selectorsByItem, subtotal: r.subtotal, total: r.total_amount, fee, discount });
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
    const shareView = ui.shareView ?? "list";
    const shownItems = items.filter((i) =>
      ui.filter === "mine" ? selectorsByItem.get(i.id).some((m) => m.user_id === meId) : ui.filter === "free" ? freeIds.has(i.id) : true,
    );
    // Phần tiền: tôi đứng đầu, sau đó ai nhiều tiền hơn đứng trước
    const shareOrder = [...cols].sort((a, b) => (b.user_id === meId) - (a.user_id === meId) || shareOf(b) - shareOf(a));

    let notice = "";
    if (settled)
      notice = `<div class="notice notice-ok sp-notice"><span aria-hidden="true">✓</span><div><b>Đã chốt chia.</b> Không thể thay đổi lựa chọn món nữa.</div></div>`;
    else if (r.status === "DRAFT")
      notice = `<div class="notice notice-warn sp-notice"><span aria-hidden="true">!</span><div>Hóa đơn đang là <b>Nháp</b>. Vẫn chọn được món; cần <a href="#/receipts/${r.id}">xác nhận hóa đơn</a> trước khi chốt chia.</div></div>`;

    const errorBox = st.error
      ? `<div class="notice notice-fail mb-3" role="alert" id="sp-error"><span>✕</span><div><b>${esc(st.error.message)}</b>
          ${st.error.details?.length ? `<ul class="reasons">${st.error.details.map((d) => `<li>${esc(d.message)}</li>`).join("")}</ul>` : ""}</div></div>`
      : "";

    const result = settled && st.debts?.items?.length
      ? `<details class="sp-debts"><summary>Công nợ phát sinh (${st.debts.items.length})</summary>
          <ul class="result-list">${st.debts.items
            .map((d) => `<li><span>${esc(d.debtor_name)} → ${esc(d.creditor_name)}</span><b>${formatVND(d.amount)}</b></li>`)
            .join("")}</ul>
        </details>`
      : "";
    const allocatedPercent = num(r.total_amount) > 0 ? Math.min(100, Math.max(0, (sumShown / num(r.total_amount)) * 100)) : 0;
    const freeCount = freeIds.size;

    box.innerHTML = `
      ${backLink()}
      <header class="sp-header">
        <div class="sp-header-main">
          <div class="sp-header-title">
            <h2 class="page-title mb-0">Chia hóa đơn</h2>
            <span class="sp-badge ${statusInfo.cls}" title="${esc(r.status)}">${statusInfo.text}</span>
          </div>
          <div class="sp-merchant">${esc(r.merchant_name || "Hóa đơn chưa có tên")}</div>
          <div class="sp-header-meta">
            <span>Nhóm: <b>${esc(st.group?.name ?? "")}</b></span>
            <span>Người ứng tiền: <b>${payer ? esc(payer.full_name) : "chưa chọn"}</b></span>
          </div>
        </div>
        <div class="sp-header-actions">
          <a class="btn btn-sm btn-outline-secondary" href="#/receipts/${r.id}">Xem / sửa</a>
          <button type="button" class="btn btn-sm btn-outline-secondary" id="btn-reload" title="Tải lựa chọn mới nhất của mọi người">↻ Làm mới</button>
        </div>
      </header>
      <section class="sp-summary" aria-label="Tổng quan hóa đơn">
        <div class="sp-metric"><div class="sp-metric-label">Tổng hóa đơn</div><div class="sp-metric-value">${formatVND(r.total_amount)}</div></div>
        <div class="sp-metric"><div class="sp-metric-label">Tổng tiền món</div><div class="sp-metric-value">${formatVND(itemsSum)}</div></div>
        <div class="sp-metric"><div class="sp-metric-label">${discount > 0 ? "Thuế/phí · Giảm giá" : "Thuế và phí"}</div><div class="sp-metric-value">${discount > 0 ? `${formatVND(fee)} · −${formatVND(discount)}` : formatVND(fee)}</div></div>
      </section>
      ${notice}
      ${errorBox}

      <div class="sp-layout">
        <main class="sp-main">
          <section class="sp-panel" aria-labelledby="sp-items-title">
            <div class="sp-panel-head">
              <div>
                <h3 class="sp-panel-title" id="sp-items-title">Chọn món</h3>
                <div class="sp-items-count">${items.length} món · ${freeCount ? `${freeCount} chưa chia` : "đã có người chọn hết"}</div>
              </div>
              ${freeCount ? `<button type="button" class="sp-jump" data-filter="free">Xem ${freeCount} món chưa chia ↓</button>` : ""}
            </div>
            <div class="sp-panel-body">
              <details class="sp-tip">
                <summary>Cách chia món, thuế và phí</summary>
                <div>Mỗi người chọn món mình đã dùng. Nhiều người chọn cùng món thì chia đều; thuế và phí chia theo tỉ lệ tiền món.</div>
              </details>
              <div class="pk-toolbar">
                <div class="pk-seg" role="group" aria-label="Lọc món">
                  ${[
                    ["all", `Tất cả ${items.length}`],
                    ["mine", `Tôi đã chọn ${items.filter((i) => selectorsByItem.get(i.id).some((m) => m.user_id === meId)).length}`],
                    ["free", `Chưa chia ${freeCount}`],
                  ]
                    .map(([k, t]) => `<button type="button" data-filter="${k}" aria-pressed="${ui.filter === k}">${t}</button>`)
                    .join("")}
                </div>
                ${many ? `<label class="pk-switch"><input type="checkbox" id="pk-showall" ${ui.showAll ? "checked" : ""}> Hiện cả người chưa chọn</label>` : ""}
              </div>
              <div class="pk-legend mb-2" aria-label="Trạng thái chọn món">
                ${canManageSelections
                  ? '<span>Trưởng nhóm có thể chọn / bỏ chọn cho mọi thành viên</span>'
                  : canSelect
                    ? '<span><span class="pill me on demo">✓ Tôi</span> chọn / bỏ chọn</span>'
                    : ""}
                <span>Đã chọn</span><span>Chưa chọn</span>
              </div>
              <div class="pick-list">${shownItems.length ? "" : `<div class="text-muted text-center p-3 pick-row" style="display:block">${ui.filter === "free" ? "Món nào cũng đã có người chọn." : ui.filter === "mine" ? "Bạn chưa chọn món nào." : "Hóa đơn chưa có dòng món."}</div>`}${shownItems
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
                      if (!open && !on && !mine) return "";
                      const name = mine ? "Tôi" : m.full_name;
                      const ava = `<span class="p-ava" aria-hidden="true">${on ? "✓" : esc(initials(m.full_name))}</span>`;
                      if ((mine && canSelect) || canManageSelections)
                        return `<label class="pill ${mine ? "me" : ""} ${on ? "on" : ""}" title="${on ? "Bỏ chọn" : "Chọn"} món này">
                          <input type="checkbox" class="pill-input" data-item="${i.id}" data-user="${m.user_id}" ${on ? "checked" : ""} aria-label="${mine ? "Tôi" : esc(m.full_name)} đã dùng ${esc(i.item_name)}">${ava}<span>${esc(name)}</span></label>`;
                      return `<span class="pill ${mine ? "me" : ""} ${on ? "on" : ""}" title="${esc(m.full_name)} ${on ? "đã chọn" : "chưa chọn"}">${ava}<span>${esc(name)}</span></span>`;
                    })
                    .join("");
                  const itemStatus = free
                    ? '<span class="sp-item-status free">Chưa chọn</span>'
                    : who.length > 1
                      ? '<span class="sp-item-status shared">Đang chia</span>'
                      : '<span class="sp-item-status chosen">Đã chọn</span>';
                  return `<div class="pick-row ${free ? "free" : ""}">
                    <div class="pick-item">
                      <div class="pick-name">${esc(i.item_name)}${itemStatus}</div>
                      <div class="pick-sub">${formatNumber(i.quantity)} × ${formatVND(i.unit_price)} = <b>${formatVND(i.line_total)}</b></div>
                    </div>
                    <div class="pick-members">${pills}${hidden ? `<button type="button" class="pill more" data-expand="${i.id}" title="Xem những người chưa chọn món này">+${hidden} chưa chọn</button>` : ""}${many && !ui.showAll && ui.expanded.has(i.id) ? `<button type="button" class="pill more" data-collapse="${i.id}">Thu gọn</button>` : ""}</div>
                    <div class="pick-split">${who.length ? `<b>${who.length} người</b><span>${formatVND(Math.round(each))}/người</span>` : '<span>Chưa chia</span>'}</div>
                  </div>`;
                })
                .join("")}</div>
            </div>
          </section>
        </main>
        <aside class="sp-sidebar" aria-label="Tổng kết chia hóa đơn">
          <section class="sp-panel" aria-labelledby="sp-shares-title">
            <div class="sp-panel-head sp-share-head">
              <h3 class="sp-panel-title" id="sp-shares-title">${settled ? "Số tiền mỗi người" : "Tạm tính mỗi người"}</h3>
              <div class="pk-seg" role="group" aria-label="Kiểu xem thành viên">
                <button type="button" data-share="list" aria-pressed="${shareView === "list"}">Danh sách</button>
                <button type="button" data-share="cards" aria-pressed="${shareView === "cards"}">Thẻ</button>
              </div>
            </div>
            <div class="sp-panel-body">
              ${shareView === "list" ? `<div class="sp-share-list">${shareOrder
                .map((m) => {
                  const share = shareOf(m);
                  const pct = num(r.total_amount) ? Math.round((share / num(r.total_amount)) * 100) : 0;
                  const tags = [m.user_id === meId ? "Tôi" : "", m.user_id === r.payer_id ? "Ứng tiền" : "", roleOf.get(m.user_id) === "LEADER" ? "Trưởng nhóm" : ""].filter(Boolean);
                  return `<div class="sl-row ${m.user_id === meId ? "me" : ""}">
                    <span class="mem-ava" aria-hidden="true">${esc(initials(m.full_name))}</span>
                    <div class="sl-name"><div class="fw-semibold text-truncate">${esc(m.full_name)}</div>${tags.length ? `<div class="mem-tag">${tags.join(" · ")}</div>` : ""}</div>
                    <div class="sl-total">${formatVND(share)}</div>
                    <details class="sl-details"><summary>Chi tiết</summary><div class="sl-detail">Tiền món ${formatVND(m.item_amount)} · Thuế/phí ${formatVND(m.fee_amount)} · ${pct}% hóa đơn</div></details>
                  </div>`;
                })
                .join("")}</div>` : `<div class="share-grid">${shareOrder
                .map((m) => {
                  const share = shareOf(m);
                  const pct = num(r.total_amount) ? Math.round((share / num(r.total_amount)) * 100) : 0;
                  const tags = [m.user_id === meId ? "Tôi" : "", m.user_id === r.payer_id ? "Ứng tiền" : "", roleOf.get(m.user_id) === "LEADER" ? "Trưởng nhóm" : ""].filter(Boolean);
                  return `<div class="share-card ${m.user_id === meId ? "me" : ""}">
                    <div class="d-flex align-items-center gap-2">
                      <span class="mem-ava" aria-hidden="true">${esc(initials(m.full_name))}</span>
                      <div style="min-width:0"><div class="fw-semibold text-truncate">${esc(m.full_name)}</div>${tags.length ? `<div class="mem-tag">${tags.join(" · ")}</div>` : ""}</div>
                    </div>
                    <div class="share-total">${formatVND(share)}</div>
                    <details class="sp-member-details"><summary>Chi tiết</summary>
                      <div class="share-rows"><span>Tiền món</span><span>${formatVND(m.item_amount)}</span></div>
                      <div class="share-rows"><span>Thuế + phí</span><span>${formatVND(m.fee_amount)}</span></div>
                      <div class="share-rows"><span>Tỉ lệ</span><span>${pct}%</span></div>
                    </details>
                  </div>`;
                })
                .join("")}</div>`}
              ${result}
            </div>
          </section>
          <section class="sp-panel sp-allocation" aria-label="Tiến độ phân bổ">
            <div class="sp-allocation-total"><span>Đã phân bổ</span><b>${formatVND(sumShown)}</b></div>
            <div class="sp-allocation-bar" role="progressbar" aria-label="Tỉ lệ tiền đã phân bổ" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(allocatedPercent)}"><i style="width:${allocatedPercent}%"></i></div>
            <div class="sp-allocation-total"><span>Tổng hóa đơn</span><span>${formatVND(r.total_amount)}</span></div>
            <div class="sp-allocation-note">${freeCount
              ? `Còn ${freeCount} món chưa được phân bổ.`
              : settled
                ? "Đã chốt; phần chia khớp tổng hóa đơn."
                : reasons.length
                  ? "Cần kiểm tra điều kiện chốt bên dưới."
                : "Phần lẻ do làm tròn sẽ được tính cho người ứng tiền."}</div>
          </section>
          ${settled ? "" : `<section class="sp-panel sp-finalize" aria-label="Điều kiện chốt chia">
            ${reasons.length
              ? `<div class="sp-finalize-status blocked"><span aria-hidden="true">!</span><span>${freeCount ? `Còn ${freeCount} món chưa được chia.` : esc(reasons[0].text)}</span></div>
                  ${freeCount ? `<button type="button" class="sp-jump mt-1" data-filter="free">Đến món chưa chia ↓</button>` : ""}
                  ${reasons.length > (freeCount ? 1 : 0) ? `<details class="sp-finalize-details"><summary>Xem điều kiện chưa đạt</summary><ul>${reasons.map((x) => `<li>${esc(x.text)}</li>`).join("")}</ul></details>` : ""}`
              : `<div class="sp-finalize-status ok"><span aria-hidden="true">✓</span><span>Đủ điều kiện chốt chia</span></div>
                  <div class="sp-allocation-note mt-1">Tổng tạm tính: ${formatVND(sumShares)} / ${formatVND(r.total_amount)}${Math.round(num(r.total_amount) - sumShares) > 0 ? ` · Phần lẻ ${formatVND(num(r.total_amount) - sumShares)} tính cho người ứng tiền` : ""}</div>`}
            ${isLeader
              ? `<button type="button" class="btn btn-primary" id="btn-finalize">Chốt chia</button>`
              : `<div class="small text-muted mt-2">Chỉ <b>Trưởng nhóm</b> mới chốt chia được.</div>`}
          </section>`}
        </aside>
      </div>`;

    /* ----- Tick / bỏ tick món của tôi ----- */
    box.querySelectorAll("input[data-item]").forEach((cb) => {
      cb.onchange = async () => {
        const itemId = cb.dataset.item;
        const userId = cb.dataset.user;
        const targetQuery = userId === String(meId) ? "" : `?user_id=${encodeURIComponent(userId)}`;
        const scrollLeft = [...box.querySelectorAll(".mx-wrap")].map((wrap) => wrap.scrollLeft);
        const scrollTop = window.scrollY;
        box.querySelectorAll(`input[data-item="${itemId}"]`).forEach((x) => (x.disabled = true, x.classList.add("busy")));
        try {
          st.summary = cb.checked
            ? await put(`/receipts/${id}/items/${itemId}/selection${targetQuery}`)
            : await del(`/receipts/${id}/items/${itemId}/selection${targetQuery}`);
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
    box.querySelectorAll("[data-filter]").forEach((b) => (b.onclick = () => {
      ui.filter = b.dataset.filter;
      paint();
      if (ui.filter === "free") requestAnimationFrame(() => box.querySelector(".pick-list")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    }));
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
