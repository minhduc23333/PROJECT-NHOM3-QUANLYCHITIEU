// T05E17C - UI-07: Công nợ (#/debts)
// Danh sách khoản nợ: người trả → người nhận, số tiền; tổng phải trả / được nhận;
// phân biệt rõ vai trò (bạn phải trả / bạn được nhận / giữa thành viên khác); trạng thái dữ liệu trống.
// Dữ liệu: GET /api/groups/{id}/debts (công nợ được tạo khi Trưởng nhóm chốt chia hóa đơn).
import { get, patch } from "../api.js";
import { getUser } from "../auth.js";
import { formatVND } from "../format.js";
import { confirmDialog, emptyHTML, esc, renderState, toast, withBusy } from "../ui.js";

const num = (v) => Number(v ?? 0) || 0;
const initials = (name = "") => {
  const p = String(name).trim().split(/\s+/).filter(Boolean);
  return p.length ? (p[0][0] + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase() : "?";
};

/** Vai trò của tôi trong một khoản nợ */
export const roleOf = (d, meId) => (d.debtor_id === meId ? "pay" : d.creditor_id === meId ? "receive" : "other");

/** Tổng phải trả / được nhận của tôi (chỉ khoản còn nợ) + gộp theo từng người. Tách riêng để dễ test. */
export function summarize(debts, meId) {
  let pay = 0;
  let receive = 0;
  const byPerson = new Map(); // id -> { name, net }: net > 0 người đó nợ tôi, net < 0 tôi nợ người đó
  for (const d of debts) {
    if (d.status !== "OPEN") continue;
    const role = roleOf(d, meId);
    if (role === "other") continue;
    const amt = num(d.amount);
    const otherId = role === "pay" ? d.creditor_id : d.debtor_id;
    const otherName = role === "pay" ? d.creditor_name : d.debtor_name;
    const cur = byPerson.get(otherId) ?? { id: otherId, name: otherName, net: 0 };
    if (role === "pay") {
      pay += amt;
      cur.net -= amt;
    } else {
      receive += amt;
      cur.net += amt;
    }
    byPerson.set(otherId, cur);
  }
  const people = [...byPerson.values()].filter((p) => Math.round(p.net) !== 0).sort((a, b) => Math.abs(b.net) - Math.abs(a.net));
  return { pay, receive, net: receive - pay, people };
}

const CSS = `
.page-debts { --ink:#464052; --muted:#6f687c; --line:#e9ddf7; --mist:#f3edfb; --brand-dark:#7a62a3;
  --grad: linear-gradient(100deg,#f0b0c3 0%,#d9b5d9 50%,#b6a1d4 100%);
  --pay:#b0587a; --pay-bg:#fdecf2; --recv:#2f7a5a; --recv-bg:#e6f6ee; color: var(--ink); }
.page-debts .page-title { font-size: clamp(1.8rem,3vw,2.3rem); font-weight:800 !important; letter-spacing:-.03em; line-height:1.15;
  background: linear-gradient(95deg,#464052 0%,#7a62a3 60%,#c27a9b 100%); -webkit-background-clip:text; background-clip:text; color:transparent !important; }
.page-debts .page-title-ico { width:46px; height:46px; border-radius:14px; display:grid; place-items:center; flex:none; background:var(--grad); color:var(--ink); box-shadow:0 8px 18px -12px rgba(182,161,212,.9); }
.page-debts .page-title-ico svg { width:24px; height:24px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
.page-debts .card { border:1px solid var(--line); border-radius:16px; }
.page-debts .form-select:focus { border-color:#b6a1d4; box-shadow:0 0 0 .2rem rgba(182,161,212,.35); }
.sum-card { padding:16px 18px; height:100%; border-radius:16px; border:1px solid var(--line); background:#fff; }
.sum-card .lbl { font-size:.85rem; color:var(--muted); display:flex; align-items:center; gap:6px; }
.sum-card .val { font-size:1.45rem; font-weight:800; letter-spacing:-.02em; margin-top:2px; }
.sum-card .sub { font-size:.8rem; color:var(--muted); }
.sum-card.pay { background:var(--pay-bg); border-color:#f6cfdd; } .sum-card.pay .val { color:var(--pay); }
.sum-card.recv { background:var(--recv-bg); border-color:#c6e9d6; } .sum-card.recv .val { color:var(--recv); }
.dot { width:10px; height:10px; border-radius:50%; display:inline-block; }
.dot.pay { background:var(--pay); } .dot.recv { background:var(--recv); }
.dchips { display:flex; flex-wrap:wrap; gap:8px; }
.dchip { border:1px solid var(--line); background:#fff; color:var(--ink); border-radius:999px; padding:4px 12px; font-size:.875rem; }
.dchip:hover { background:var(--mist); }
.dchip[aria-pressed="true"] { background:var(--grad); border-color:transparent; font-weight:600; }
.people { list-style:none; margin:0; padding:0; display:grid; gap:8px; }
.people li { display:flex; align-items:center; gap:10px; padding:10px 12px; border-radius:12px; border:1px solid var(--line); background:#fff; }
.ava { width:34px; height:34px; border-radius:50%; display:grid; place-items:center; font-size:.75rem; font-weight:700; flex:none; background:#e9ddf7; color:#6c56a0; }
.ava.me { background:var(--grad); color:var(--ink); }
.debt-list { list-style:none; margin:0; padding:0; display:grid; gap:10px; }
.debt { display:grid; grid-template-columns: minmax(0,1fr) auto; gap:6px 16px; padding:14px 16px; border-radius:14px; border:1px solid var(--line); background:#fff; border-left:5px solid #d8d1e3; }
.debt.pay { border-left-color:var(--pay); } .debt.receive { border-left-color:var(--recv); }
.debt.paid { opacity:.7; }
.flow { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.party { display:flex; align-items:center; gap:8px; min-width:0; }
.party .who { display:flex; flex-direction:column; min-width:0; }
.party .who small { font-size:.7rem; color:var(--muted); text-transform:uppercase; letter-spacing:.04em; }
.party .who b { white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.arrow { color:#b6a1d4; font-size:1.2rem; }
.amt { text-align:right; font-size:1.15rem; font-weight:800; white-space:nowrap; }
.debt.pay .amt { color:var(--pay); } .debt.receive .amt { color:var(--recv); }
.meta { grid-column:1 / -1; display:flex; flex-wrap:wrap; gap:6px 14px; font-size:.82rem; color:var(--muted); align-items:center; }
.meta a { color:var(--brand-dark); }
.role { padding:2px 9px; border-radius:999px; font-size:.75rem; font-weight:700; }
.role.pay { background:var(--pay-bg); color:var(--pay); } .role.receive { background:var(--recv-bg); color:var(--recv); } .role.other { background:#efecf3; color:#5b5568; }
.st { padding:2px 9px; border-radius:999px; font-size:.75rem; font-weight:600; }
.st.open { background:#fff1d6; color:#8a5a00; } .st.paid { background:#e6f6ee; color:#2f7a5a; }
.legend { display:flex; flex-wrap:wrap; gap:14px; font-size:.82rem; color:var(--muted); }
.bal { height:14px; border-radius:999px; overflow:hidden; display:flex; background:#efeaf6; }
.bal span { display:block; height:100%; }
.bal .p { background:linear-gradient(90deg,#e7a1bb,#c97a9c); } .bal .r { background:linear-gradient(90deg,#8fd1b2,#56a886); }
.bal-legend { display:flex; justify-content:space-between; font-size:.8rem; color:var(--muted); margin-top:6px; }
.mini-stats { display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }
.mini-stats span { background:var(--mist); border-radius:999px; padding:3px 10px; font-size:.8rem; }
.side { position:sticky; top:76px; display:grid; gap:16px; }
.side h6 { font-weight:700; margin:0 0 10px; }
.pbar { height:6px; border-radius:999px; background:#efeaf6; margin-top:6px; overflow:hidden; }
.pbar i { display:block; height:100%; }
.people li { flex-wrap:wrap; }
.people .pinfo { flex:1; min-width:0; }
.copy-btn { border:1px solid var(--line); background:#fff; color:var(--brand-dark); border-radius:8px; font-size:.75rem; font-weight:600; padding:2px 8px; }
.copy-btn:hover { background:var(--mist); }
.steps-mini { list-style:none; margin:0; padding:0; display:grid; gap:10px; font-size:.86rem; }
.steps-mini li { display:flex; gap:10px; }
.steps-mini b.n { width:22px; height:22px; border-radius:50%; display:grid; place-items:center; flex:none; background:var(--mist); color:var(--brand-dark); font-size:.75rem; }
.grp-head { display:flex; justify-content:space-between; align-items:baseline; gap:8px; margin:18px 0 8px; font-weight:700; }
.grp-head:first-child { margin-top:0; }
.grp-head small { font-weight:500; color:var(--muted); }
@media (max-width: 991.98px) { .side { position:static; } }
@media (max-width: 575.98px) {
  .sum-card { padding:12px 14px; }
  .sum-card .sub { display:none; }
  .grp-head { flex-direction:column; gap:2px; }
  .debt { grid-template-columns: 1fr; }
  .amt { text-align:left; }
  .sum-card .val { font-size:1.2rem; }
}
`;
function ensureStyles() {
  if (document.getElementById("debts-css")) return;
  const st = document.createElement("style");
  st.id = "debts-css";
  st.textContent = CSS;
  document.head.appendChild(st);
}

const ICON =
  '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h13v4"/><path d="M3 7v11a2 2 0 0 0 2 2h15V9H5a2 2 0 0 1-2-2z"/><circle cx="16" cy="14.5" r="1.3"/></svg>';
const ROLE = {
  pay: { text: "Bạn phải trả", cls: "pay" },
  receive: { text: "Bạn được nhận", cls: "receive" },
  other: { text: "Giữa thành viên khác", cls: "other" },
};

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
}
const plainVND = (v) => formatVND(v).replace(/\u00a0/g, " ");
// Nội dung để gửi nhắc nợ / ghi chú chuyển khoản (bấm là sao chép)
const remindText = (name, amount, what) => `Chào ${name}, bạn còn nợ mình ${plainVND(amount)}${what ? ` (${what})` : ""} trên SmartSplit nhé. Cảm ơn bạn!`;
// Nội dung chuyển khoản ngân hàng: không dấu, số tiền không kèm ký hiệu ₫
const noAccent = (t) => String(t ?? "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D");
const transferText = (myName, amount, what) =>
  noAccent(`${myName} chuyen tien ${what ? `${what} ` : ""}${plainVND(amount).replace(/\s*₫/, "")}`).trim();

export function render(el, params) {
  ensureStyles();
  const me = getUser();
  const meId = me?.id;
  const state = {
    groupId: params.group ?? "all",
    status: ["OPEN", "PAID", "ALL"].includes(params.status) ? params.status : "OPEN",
    groups: [],
    debts: [],
  };

  el.innerHTML = `<div class="page-debts">
    <div class="d-flex align-items-center gap-3 mb-3">
      <span class="page-title-ico" aria-hidden="true">${ICON}</span>
      <div>
        <h2 class="page-title mb-0">Công nợ</h2>
        <div class="text-muted">Ai cần trả ai, bao nhiêu, sau khi hóa đơn được chốt chia</div>
      </div>
    </div>
    <div id="body"></div>
  </div>`;
  const body = el.querySelector("#body");

  const syncUrl = (push = true) => {
    const qs = new URLSearchParams();
    if (state.groupId !== "all") qs.set("group", state.groupId);
    if (state.status !== "OPEN") qs.set("status", state.status);
    const nextHash = `#/debts${qs.toString() ? `?${qs}` : ""}`;
    if (location.hash !== nextHash) {
      if (push) history.pushState(null, "", nextHash);
      else history.replaceState(null, "", nextHash);
    }
  };

  const canConfirmPayment = (d) =>
    d.status === "OPEN" &&
    (d.creditor_id === meId ||
      state.groups.some((g) => String(g.id) === String(d.group_id) && g.my_role === "LEADER"));

  const person = (id, name, label) => `<div class="party">
      <span class="ava ${id === meId ? "me" : ""}" aria-hidden="true">${esc(initials(name))}</span>
      <span class="who"><small>${label}</small><b>${id === meId ? "Bạn" : esc(name)}</b></span>
    </div>`;

  function paint() {
    const groupName = new Map(state.groups.map((g) => [g.id, g.name]));
    const inScope = state.debts.filter((d) => state.groupId === "all" || String(d.group_id) === String(state.groupId));
    const s = summarize(inScope, meId);
    const shown = inScope
      .filter((d) => roleOf(d, meId) !== "other")
      .filter((d) => state.status === "ALL" || d.status === state.status)
      .sort((a, b) => (a.status === b.status ? b.id - a.id : a.status === "OPEN" ? -1 : 1));

    const chip = (key, val, text) =>
      `<button type="button" class="dchip" data-${key}="${val}" aria-pressed="${state[key] === val}">${text}</button>`;
    const netText =
      Math.round(s.net) > 0
        ? `<div class="val" style="color:var(--recv)">+${formatVND(s.net)}</div><div class="sub">Nhìn chung bạn sẽ được nhận lại</div>`
        : Math.round(s.net) < 0
          ? `<div class="val" style="color:var(--pay)">−${formatVND(-s.net)}</div><div class="sub">Nhìn chung bạn còn phải trả</div>`
          : `<div class="val">0 ₫</div><div class="sub">${s.pay > 0 ? "Số phải trả bằng số được nhận" : "Không ai nợ ai 🎉"}</div>`;

    let listHTML;
    if (!state.debts.length) {
      listHTML = emptyHTML("Chưa có khoản nợ nào. Công nợ được tạo khi Trưởng nhóm chốt chia một hóa đơn.", {
        actionText: "Xem hóa đơn để chia tiền",
        actionHref: "#/receipts",
      });
    } else if (!shown.length) {
      listHTML = `<div class="text-center text-muted p-4 card">${
        state.status === "OPEN"
          ? "Bạn không còn khoản nợ nào chưa thanh toán ở đây. 🎉"
          : "Không có khoản nợ nào khớp bộ lọc."
      } <button type="button" class="btn btn-link p-0 align-baseline" id="btn-clear">Xem tất cả</button></div>`;
    } else {
      const card = (d) => {
          const role = roleOf(d, meId);
          const r = ROLE[role];
          return `<li class="debt ${r.cls} ${d.status === "PAID" ? "paid" : ""}">
            <div class="flow">
              ${person(d.debtor_id, d.debtor_name, "Người trả")}
              <span class="arrow" aria-label="trả cho">→</span>
              ${person(d.creditor_id, d.creditor_name, "Người nhận")}
            </div>
            <div class="amt">${role === "pay" ? "−" : role === "receive" ? "+" : ""}${formatVND(d.amount)}</div>
            <div class="meta">
              <span class="role ${r.cls}">${r.text}</span>
              <span class="st ${d.status === "PAID" ? "paid" : "open"}">${d.status === "PAID" ? "Đã trả" : "Còn nợ"}</span>
              <span>Hóa đơn: <a href="#/receipts/${d.receipt_id}/split">${esc(d.merchant_name || `#${d.receipt_id}`)}</a></span>
              ${d.status === "OPEN" && role === "receive" ? `<button type="button" class="copy-btn ms-auto" data-copy="${esc(remindText(d.debtor_name, d.amount, d.merchant_name))}" data-done="Đã sao chép lời nhắc">Nhắc nợ</button>` : ""}
              ${d.status === "OPEN" && role === "pay" ? `<button type="button" class="copy-btn ms-auto" data-copy="${esc(transferText(me?.full_name ?? "", d.amount, d.merchant_name))}" data-done="Đã sao chép nội dung chuyển khoản">Sao chép ND chuyển khoản</button>` : ""}
              ${canConfirmPayment(d) ? `<button type="button" class="copy-btn ms-auto" data-pay="${d.id}">✓ Đã nhận tiền</button>` : ""}
            </div>
          </li>`;
      };
      // Xem "Tất cả nhóm": chia thành từng nhóm, mỗi nhóm có dòng tổng của tôi
      const groupsShown = [...new Set(shown.map((d) => d.group_id))];
      listHTML =
        state.groupId === "all" && groupsShown.length > 1
          ? groupsShown
              .map((gid) => {
                const ds = shown.filter((d) => d.group_id === gid);
                const g = summarize(ds, meId);
                const sub = [g.pay ? `phải trả ${formatVND(g.pay)}` : "", g.receive ? `được nhận ${formatVND(g.receive)}` : ""].filter(Boolean).join(" · ");
                return `<div class="grp-head"><span>${esc(groupName.get(gid) ?? "Nhóm")}</span><small>${ds.length} khoản${sub ? ` · ${sub}` : ""}</small></div>
                  <ul class="debt-list">${ds.map(card).join("")}</ul>`;
              })
              .join("")
          : `<ul class="debt-list">${shown.map(card).join("")}</ul>`;
    }

    const openMine = inScope.filter((d) => d.status === "OPEN" && roleOf(d, meId) !== "other");
    const paidMine = inScope.filter((d) => d.status === "PAID" && roleOf(d, meId) !== "other");
    const maxNet = Math.max(1, ...s.people.map((p) => Math.abs(p.net)));

    body.innerHTML = `
      <div class="d-flex flex-wrap gap-3 align-items-end mb-3">
        <div style="min-width:240px">
          <label class="form-label" for="f-group">Nhóm</label>
          <select class="form-select" id="f-group">
            <option value="all">Tất cả nhóm</option>
            ${state.groups.map((g) => `<option value="${g.id}" ${String(g.id) === String(state.groupId) ? "selected" : ""}>${esc(g.name)}</option>`).join("")}
          </select>
        </div>
      </div>

      <div class="row g-3 mb-4">
        <div class="col-6 col-sm-4"><div class="sum-card pay">
          <div class="lbl"><span class="dot pay"></span>Bạn phải trả</div>
          <div class="val">${formatVND(s.pay)}</div><div class="sub">Tổng các khoản bạn còn nợ người khác</div>
        </div></div>
        <div class="col-6 col-sm-4"><div class="sum-card recv">
          <div class="lbl"><span class="dot recv"></span>Bạn được nhận</div>
          <div class="val">${formatVND(s.receive)}</div><div class="sub">Tổng người khác còn nợ bạn</div>
        </div></div>
        <div class="col-12 col-sm-4"><div class="sum-card">
          <div class="lbl">Số dư</div>${netText}
        </div></div>
      </div>

      ${s.pay + s.receive > 0 ? `<div class="card mb-4"><div class="card-body">
        <div class="d-flex justify-content-between mb-2"><b>Phải trả và được nhận</b><span class="text-muted small">các khoản còn nợ</span></div>
        <div class="bal" role="img" aria-label="Phải trả ${formatVND(s.pay)}, được nhận ${formatVND(s.receive)}">
          <span class="p" style="width:${(s.pay / (s.pay + s.receive)) * 100}%"></span><span class="r" style="width:${(s.receive / (s.pay + s.receive)) * 100}%"></span>
        </div>
        <div class="bal-legend"><span>Phải trả ${Math.round((s.pay / (s.pay + s.receive)) * 100)}%</span><span>Được nhận ${Math.round((s.receive / (s.pay + s.receive)) * 100)}%</span></div>
        <div class="mini-stats">
          <span>${openMine.length} khoản liên quan tới bạn còn nợ</span>
          <span>${s.people.length} người cần thanh toán với bạn</span>
          <span>${paidMine.length} khoản đã trả xong</span>
        </div>
      </div></div>` : ""}

      <div class="row g-4">
      <div class="col-lg-4 order-lg-2">
        <div class="side">
          ${s.people.length ? `<div class="card"><div class="card-body">
            <h6>Gộp theo từng người</h6>
            <ul class="people">${s.people
              .map((p) => `<li><span class="ava" aria-hidden="true">${esc(initials(p.name))}</span>
                <div class="pinfo">
                  <div class="d-flex justify-content-between gap-2"><span>${p.net < 0 ? `Bạn cần trả <b>${esc(p.name)}</b>` : `<b>${esc(p.name)}</b> cần trả bạn`}</span>
                  <b style="color:${p.net < 0 ? "var(--pay)" : "var(--recv)"}">${formatVND(Math.abs(p.net))}</b></div>
                  <div class="pbar"><i style="width:${(Math.abs(p.net) / maxNet) * 100}%;background:${p.net < 0 ? "#d58aa8" : "#6dbb98"}"></i></div>
                  <div class="mt-2"><button type="button" class="copy-btn"
                    data-copy="${esc(p.net < 0 ? transferText(me?.full_name ?? "", Math.abs(p.net), "") : remindText(p.name, p.net, ""))}"
                    data-done="${p.net < 0 ? "Đã sao chép nội dung chuyển khoản" : "Đã sao chép lời nhắc"}">${p.net < 0 ? "Sao chép ND chuyển khoản" : "Nhắc nợ"}</button></div>
                </div></li>`)
              .join("")}</ul>
          </div></div>` : ""}
          <div class="card d-none d-lg-block"><div class="card-body">
            <h6>Công nợ đến từ đâu?</h6>
            <ol class="steps-mini">
              <li><b class="n">1</b><span>Tải ảnh hóa đơn, kiểm tra và <b>xác nhận</b>, chọn người ứng tiền.</span></li>
              <li><b class="n">2</b><span>Mỗi người <b>tick các món</b> mình đã dùng ở trang Chia hóa đơn.</span></li>
              <li><b class="n">3</b><span><b>Trưởng nhóm chốt chia</b>: mỗi người nợ người ứng tiền đúng phần của mình.</span></li>
            </ol>
          </div></div>
        </div>
      </div>
      <div class="col-lg-8 order-lg-1">
      <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
        <div class="dchips" role="group" aria-label="Trạng thái">
          ${chip("status", "OPEN", "Còn nợ")}${chip("status", "PAID", "Đã trả")}${chip("status", "ALL", "Tất cả")}
        </div>
      </div>
      <div class="legend mb-3">
        <span><span class="dot pay"></span> Bạn phải trả</span>
        <span><span class="dot recv"></span> Bạn được nhận</span>
      </div>
      ${listHTML}
      </div>
      </div>`;

    body.querySelector("#f-group").onchange = (e) => {
      state.groupId = e.target.value;
      syncUrl();
      paint();
    };
    body.querySelectorAll("[data-status]").forEach((b) => (b.onclick = () => ((state.status = b.dataset.status), syncUrl(), paint())));
    body.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.onclick = async () => {
        await copyText(btn.dataset.copy);
        toast.success(btn.dataset.done);
      };
    });
    body.querySelectorAll("[data-pay]").forEach((button) => {
      button.onclick = async () => {
        const debtId = Number(button.dataset.pay);
        const debt = state.debts.find((d) => d.id === debtId);
        const ok = await confirmDialog({
          title: "Xác nhận đã nhận tiền?",
          message: `Xác nhận khoản ${formatVND(debt?.amount)} từ ${debt?.debtor_name ?? "thành viên"} đã được thanh toán?`,
          okText: "Đã nhận tiền",
        });
        if (!ok) return;
        try {
          const updated = await withBusy(button, () => patch(`/debts/${debtId}/pay`));
          state.debts = state.debts.map((d) => (d.id === updated.id ? updated : d));
          paint();
          toast.success("Đã xác nhận khoản nợ đã thanh toán");
        } catch (e) {
          toast.error(e);
        }
      };
    });
    body.querySelector("#btn-clear")?.addEventListener("click", () => {
      state.status = "ALL";
      syncUrl();
      paint();
    });
  }

  renderState(
    body,
    async () => {
      const groups = await get("/groups");
      // Lấy công nợ của từng nhóm, lọc các khoản liên quan tới tôi ngay ở giao diện
      const lists = await Promise.all(groups.map((g) => get(`/groups/${g.id}/debts`).then((r) => r.items).catch(() => [])));
      return { groups, debts: lists.flat() };
    },
    (_, data) => {
      Object.assign(state, data);
      if (state.groupId !== "all" && !state.groups.some((g) => String(g.id) === String(state.groupId))) state.groupId = "all";
      syncUrl(false);
      paint();
    },
    {
      isEmpty: (d) => !d.groups.length,
      emptyText: "Bạn chưa ở nhóm nào nên chưa có công nợ.",
      emptyAction: { actionText: "Tạo hoặc tham gia nhóm", actionHref: "#/groups" },
      loading: "skeleton",
    },
  );
}
