// Trang Tổng quan (Dashboard)
// Dữ liệu: GET /api/dashboard/summary (chỉ tính hóa đơn đã chốt) + GET /api/groups
import { get } from "../api.js";
import { getUser } from "../auth.js";
import { barChartVND } from "../charts.js";
import { formatDate, formatVND } from "../format.js";
import { emptyHTML, esc, renderState } from "../ui.js";

// Kiểu dáng riêng của trang, cùng bảng màu Pink & Lavender, chỉ áp dụng trong .page-dash
const CSS = `
.page-dash { --ink: #464052; --muted: #6f687c; --line: #e9ddf7; --mist: #f3edfb; --lav: #b6a1d4; --pink: #f0b0c3;
  --grad: linear-gradient(100deg, #f0b0c3 0%, #d9b5d9 50%, #b6a1d4 100%); color: var(--ink); }
.page-dash .card { border: 1px solid var(--line); border-radius: 16px; }
.page-dash .card-title { font-weight: 700; color: var(--ink); }
.dash-hero { position: relative; overflow: hidden; border-radius: 20px; padding: 24px 26px;
  background: linear-gradient(115deg, #fce4ec 0%, #f3e6f7 45%, #e9ddf7 100%); border: 1px solid var(--line); }
.dash-hero::after { content: ""; position: absolute; width: 220px; height: 220px; right: -60px; top: -90px;
  border-radius: 50%; background: radial-gradient(circle, rgba(255,255,255,.8), rgba(255,255,255,0) 70%); }
.dash-hero h2 { font-size: clamp(1.6rem, 3vw, 2.2rem); font-weight: 800; letter-spacing: -.03em; margin: 0 0 4px;
  background: linear-gradient(95deg, #464052 0%, #7a62a3 60%, #c27a9b 100%); -webkit-background-clip: text; background-clip: text; color: transparent; }
.dash-hero p { color: var(--muted); margin: 0; }
.dash-actions .btn { border-radius: 12px; font-weight: 600; }
.dash-actions .btn-main { background: var(--grad); border: 0; color: var(--ink); box-shadow: 0 8px 18px -12px rgba(182,161,212,.9); }
.dash-actions .btn-main:hover { color: var(--ink); filter: brightness(.97); }
.dash-actions .btn-soft { background: rgba(255,255,255,.75); border: 1px solid #fff; color: var(--ink); }
.dash-actions .btn-soft:hover { background: #fff; color: var(--ink); }
.stat { display: flex; gap: 14px; align-items: center; padding: 16px 18px; height: 100%; }
.stat-ico { width: 46px; height: 46px; border-radius: 14px; display: grid; place-items: center; flex: none; }
.stat-ico svg { width: 22px; height: 22px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
.stat-label { color: var(--muted); font-size: .85rem; }
.stat-value { font-size: 1.35rem; font-weight: 800; letter-spacing: -.02em; line-height: 1.2; }
.stat-sub { font-size: .8rem; color: var(--muted); }
.t-pink { background: #fce4ec; color: #b0587a; } .t-lav { background: #e9ddf7; color: #6c56a0; }
.t-mint { background: #dff3ea; color: #2f7a5a; } .t-peach { background: #fde8d8; color: #a5523a; }
.v-good { color: #2f7a5a; } .v-bad { color: #b0587a; }
.dash-chart { position: relative; height: 260px; }
.dash-empty { display: grid; place-items: center; text-align: center; height: 220px; color: var(--muted);
  background: #faf8fd; border: 1px dashed #dcd3ea; border-radius: 14px; padding: 16px; }
.cat-legend { list-style: none; padding: 0; margin: 12px 0 0; display: grid; gap: 6px; font-size: .875rem; }
.cat-legend li { display: flex; align-items: center; gap: 8px; }
.cat-dot { width: 10px; height: 10px; border-radius: 3px; flex: none; }
.cat-legend .amt { margin-left: auto; font-weight: 600; }
.recent-list { list-style: none; margin: 0; padding: 0; }
.recent-list li { display: flex; align-items: center; gap: 12px; padding: 10px 0; border-bottom: 1px solid #f1ecf8; }
.recent-list li:last-child { border-bottom: 0; }
.r-ico { width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center; flex: none; background: var(--mist); color: #6c56a0; font-weight: 700; font-size: .8rem; }
.r-mine { font-size: .8rem; color: var(--muted); }
.g-chip { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 12px; border: 1px solid var(--line);
  background: #fff; text-decoration: none; color: var(--ink); transition: box-shadow .15s, transform .15s; }
.g-chip:hover { box-shadow: 0 10px 22px -14px rgba(122,98,163,.5); transform: translateY(-1px); color: var(--ink); }
.g-ava { width: 34px; height: 34px; border-radius: 50%; display: grid; place-items: center; font-weight: 700; font-size: .75rem; background: #e9ddf7; color: #6c56a0; flex: none; }
.steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.steps li { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 14px; background: #fff; border: 1px solid var(--line); }
.step-n { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; font-weight: 700; flex: none; background: var(--mist); color: #6c56a0; }
.steps li.done .step-n { background: #dff3ea; color: #2f7a5a; }
.steps li.done .step-t { color: var(--muted); text-decoration: line-through; }
.link-more { color: #7a62a3; font-weight: 600; text-decoration: none; font-size: .9rem; }
.link-more:hover { text-decoration: underline; }
@media (max-width: 575.98px) {
  .dash-hero { padding: 20px 18px; }
  .stat { flex-direction: column; align-items: flex-start; gap: 8px; padding: 14px; }
  .stat-ico { width: 38px; height: 38px; border-radius: 12px; }
  .stat-value { font-size: 1.1rem; white-space: nowrap; }
  .recent-list .r-sub { white-space: normal; }
}
`;
function ensureStyles() {
  if (document.getElementById("dash-css")) return;
  const st = document.createElement("style");
  st.id = "dash-css";
  st.textContent = CSS;
  document.head.appendChild(st);
}

const svg = (d) => `<svg viewBox="0 0 24 24" aria-hidden="true">${d}</svg>`;
const ICONS = {
  wallet: svg('<path d="M3 7a2 2 0 0 1 2-2h13v4"/><path d="M3 7v11a2 2 0 0 0 2 2h15V9H5a2 2 0 0 1-2-2z"/><circle cx="16" cy="14.5" r="1.3"/>'),
  group: svg('<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7M18 14.5a6.5 6.5 0 0 1 3.5 5.5"/>'),
  scale: svg('<path d="M12 3v18M7 21h10"/><path d="M5 7h14"/><path d="m5 7-3 6a3 3 0 0 0 6 0zM19 7l-3 6a3 3 0 0 0 6 0z"/>'),
  receipt: svg('<path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9.5 8h5M9.5 12h5M9.5 16h3"/>'),
};
const CAT_COLORS = ["#b6a1d4", "#f0b0c3", "#9fd3c0", "#f5c99b", "#a9c2ec", "#d9b5d9", "#e8d38f"];

const num = (v) => Number(v ?? 0) || 0;
const initials = (name = "") => {
  const p = String(name).trim().split(/\s+/).filter(Boolean);
  return p.length ? (p[0][0] + (p.length > 1 ? p[p.length - 1][0] : "")).toUpperCase() : "?";
};
function greeting() {
  const h = new Date().getHours();
  return h < 11 ? "Chào buổi sáng" : h < 14 ? "Chào buổi trưa" : h < 18 ? "Chào buổi chiều" : "Chào buổi tối";
}

const stat = (tone, icon, label, value, sub = "", valueCls = "") => `
  <div class="col-6 col-xl-3"><div class="card h-100"><div class="stat">
    <span class="stat-ico ${tone}">${icon}</span>
    <div style="min-width:0">
      <div class="stat-label">${esc(label)}</div>
      <div class="stat-value ${valueCls}">${value}</div>
      ${sub ? `<div class="stat-sub">${sub}</div>` : ""}
    </div>
  </div></div></div>`;

function balanceStat(s) {
  const net = num(s.owed_to_me) - num(s.i_owe);
  if (net > 0) return stat("t-mint", ICONS.scale, "Số dư công nợ", formatVND(net), "Bạn sẽ được nhận lại", "v-good");
  if (net < 0) return stat("t-pink", ICONS.scale, "Số dư công nợ", formatVND(-net), "Bạn cần trả thêm", "v-bad");
  return stat("t-mint", ICONS.scale, "Số dư công nợ", formatVND(0), "Không ai nợ ai 🎉");
}

function onboarding(groups, s) {
  const hasGroup = groups.length > 0;
  const hasMember = groups.some((g) => num(g.member_count) > 1);
  const hasSettled = num(s.receipt_count) > 0;
  const step = (done, n, text, href, cta) => `
    <li class="${done ? "done" : ""}">
      <span class="step-n">${done ? "✓" : n}</span>
      <span class="step-t flex-grow-1">${esc(text)}</span>
      ${done ? "" : `<a class="link-more" href="${href}">${esc(cta)} →</a>`}
    </li>`;
  return `<div class="card mb-4"><div class="card-body">
    <h5 class="card-title mb-1">Bắt đầu chia tiền trong 3 bước</h5>
    <p class="text-muted small mb-3">Số liệu ở trang này được tính từ các hóa đơn đã chốt.</p>
    <ol class="steps">
      ${step(hasGroup, 1, "Tạo một nhóm (phòng trọ, chuyến đi, bạn bè...)", "#/groups", "Tạo nhóm")}
      ${step(hasMember, 2, "Thêm bạn bè vào nhóm bằng email", "#/groups", "Thêm thành viên")}
      ${step(hasSettled, 3, "Tải ảnh hóa đơn, xác nhận và chốt hóa đơn đầu tiên", "#/receipts", "Thêm hóa đơn")}
    </ol>
  </div></div>`;
}

function categoryChart(canvas, cats) {
  if (!window.Chart) return;
  // eslint-disable-next-line no-new
  new Chart(canvas, {
    type: "doughnut",
    data: {
      labels: cats.map((c) => c.category),
      datasets: [{ data: cats.map((c) => num(c.total)), backgroundColor: cats.map((_, i) => CAT_COLORS[i % CAT_COLORS.length]), borderColor: "#fff", borderWidth: 3, hoverOffset: 6 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${formatVND(ctx.parsed)}` } } },
    },
  });
}

function recentList(rows) {
  if (!rows.length) return '<div class="dash-empty" style="height:auto;min-height:140px">Chưa có hóa đơn nào được chốt.</div>';
  return `<ul class="recent-list">${rows
    .map(
      (r) => `<li>
        <span class="r-ico">${esc(initials(r.merchant_name || "HĐ"))}</span>
        <div class="flex-grow-1" style="min-width:0">
          <div class="fw-semibold text-truncate">${esc(r.merchant_name || "Hóa đơn chưa có tên")}</div>
          <div class="text-muted small text-truncate r-sub">${esc(r.group_name || "Cá nhân")} · ${formatDate(r.receipt_date)}${r.category ? ` · ${esc(r.category)}` : ""}</div>
        </div>
        <div class="text-end flex-shrink-0">
          <div class="fw-semibold">${formatVND(r.total_amount)}</div>
          <div class="r-mine">Phần tôi: ${formatVND(r.my_amount)}</div>
        </div>
      </li>`,
    )
    .join("")}</ul>`;
}

function groupList(groups) {
  if (!groups.length) return emptyHTML("Bạn chưa ở nhóm nào", { actionText: "Tạo nhóm", actionHref: "#/groups" });
  return `<div class="d-grid gap-2">${groups
    .slice(0, 4)
    .map(
      (g) => `<a class="g-chip" href="#/groups/${g.id}">
        <span class="g-ava">${esc(initials(g.name))}</span>
        <span class="flex-grow-1 text-truncate fw-semibold">${esc(g.name)}</span>
        <span class="text-muted small flex-shrink-0">${num(g.member_count)} người</span>
      </a>`,
    )
    .join("")}</div>`;
}

export function render(el) {
  ensureStyles();
  const name = getUser()?.full_name?.trim() ?? "";
  el.innerHTML = `<div class="page-dash">
    <section class="dash-hero mb-4 d-flex flex-wrap align-items-center justify-content-between gap-3">
      <div style="position:relative;z-index:1">
        <h2>${greeting()}${name ? `, ${esc(name)}` : ""} 👋</h2>
        <p>Tổng quan chi tiêu và công nợ của bạn</p>
      </div>
      <div class="dash-actions d-flex flex-wrap gap-2" style="position:relative;z-index:1">
        <a class="btn btn-main" href="#/receipts">+ Thêm hóa đơn</a>
        <a class="btn btn-soft" href="#/groups">+ Tạo nhóm</a>
        <a class="btn btn-soft" href="#/debts">Xem công nợ</a>
      </div>
    </section>
    <div id="dash"></div>
  </div>`;

  renderState(
    el.querySelector("#dash"),
    () => Promise.all([get("/dashboard/summary"), get("/groups").catch(() => [])]),
    (box, [s, groups]) => {
      const monthly = s.monthly ?? [];
      const cats = (s.by_category ?? []).filter((c) => num(c.total) > 0);
      const recent = [...(s.recent_receipts ?? [])].sort(
        (a, b) => new Date(b.receipt_date ?? 0) - new Date(a.receipt_date ?? 0),
      );
      const hasSpend = monthly.some((m) => num(m.total) > 0);
      const monthlyTotal = monthly.reduce((total, m) => total + num(m.total), 0);
      const catTotal = cats.reduce((t, c) => t + num(c.total), 0);

      box.innerHTML = `
        <div class="row g-3 mb-4">
          ${stat("t-lav", ICONS.wallet, "Tôi đã chi", formatVND(s.personal_spent ?? s.total_spent), "Phần của tôi trong các hóa đơn")}
          ${stat("t-peach", ICONS.group, "Nhóm đã chi", formatVND(s.group_spent ?? 0), `${num(s.group_count)} nhóm đang tham gia`)}
          ${balanceStat(s)}
          ${stat("t-pink", ICONS.receipt, "Hóa đơn đã chốt", num(s.receipt_count), `Nợ: ${formatVND(s.i_owe)} · Được nợ: ${formatVND(s.owed_to_me)}`)}
        </div>

        ${num(s.receipt_count) === 0 ? onboarding(groups, s) : ""}

        <div class="row g-3 mb-4">
          <div class="col-lg-7"><div class="card h-100"><div class="card-body">
            <div class="d-flex justify-content-between align-items-center gap-2 mb-1">
              <h5 class="card-title mb-0">Chi tiêu của tôi, 6 tháng gần nhất</h5>
              <a class="link-more" href="#/reports">Xem báo cáo →</a>
            </div>
            <p class="text-muted small mb-2">Tổng trong 6 tháng: ${formatVND(monthlyTotal)} · Tổng chi và danh mục tính mọi hóa đơn đã chốt.</p>
            ${hasSpend ? '<div class="dash-chart"><canvas id="chart-monthly"></canvas></div>'
                       : '<div class="dash-empty">Chưa có chi tiêu nào trong 6 tháng qua.<br>Biểu đồ sẽ hiện khi có hóa đơn được chốt.</div>'}
          </div></div></div>
          <div class="col-lg-5"><div class="card h-100"><div class="card-body">
            <h5 class="card-title">Theo danh mục</h5>
            ${cats.length
              ? `<div class="dash-chart" style="height:190px"><canvas id="chart-cat"></canvas></div>
                 <ul class="cat-legend">${cats
                   .map((c, i) => `<li><span class="cat-dot" style="background:${CAT_COLORS[i % CAT_COLORS.length]}"></span>${esc(c.category)}
                     <span class="text-muted small">${Math.round((num(c.total) / catTotal) * 100)}%</span><span class="amt">${formatVND(c.total)}</span></li>`)
                   .join("")}</ul>`
              : '<div class="dash-empty">Chưa có dữ liệu theo danh mục.</div>'}
          </div></div></div>
        </div>

        <div class="row g-3">
          <div class="col-lg-7"><div class="card h-100"><div class="card-body">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <h5 class="card-title mb-0">Hóa đơn gần đây</h5>
              <a class="link-more" href="#/receipts">Xem tất cả →</a>
            </div>
            ${recentList(recent)}
          </div></div></div>
          <div class="col-lg-5"><div class="card h-100"><div class="card-body">
            <div class="d-flex justify-content-between align-items-center mb-2">
              <h5 class="card-title mb-0">Nhóm của tôi</h5>
              <a class="link-more" href="#/groups">Tất cả nhóm →</a>
            </div>
            ${groupList(groups)}
          </div></div></div>
        </div>`;

      if (hasSpend) {
        barChartVND(
          box.querySelector("#chart-monthly"),
          monthly.map((m) => m.month.split("-").reverse().join("/")),
          monthly.map((m) => num(m.total)),
          "Chi tiêu",
        );
      }
      if (cats.length) categoryChart(box.querySelector("#chart-cat"), cats);
    },
  );
}
