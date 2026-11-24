// T05E180 - UI-08: Báo cáo chi tiêu theo thời gian / danh mục (#/reports)
// Dữ liệu: GET /api/dashboard/report (chỉ hóa đơn SETTLED). Biểu đồ dùng Chart.js (vendor/chart.umd.js).
import { get } from "../api.js";
import { formatVND, formatVNDShort } from "../format.js";
import { emptyHTML, esc, toast } from "../ui.js";

const COLORS = ["#b6a1d4", "#f0b0c3", "#9fd3c0", "#f5c99b", "#a9c2ec", "#d9b5d9", "#e8d38f", "#c7b8a3"];
const num = (v) => Number(v ?? 0) || 0;
const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const parse = (s) => {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
};
const fmtDate = (s) => s.split("-").reverse().join("/");
const UNIT = { day: "ngày", week: "tuần", month: "tháng" };

/** Khoảng ngày theo nút chọn nhanh */
export function presetRange(key, today = new Date()) {
  const t = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const monthsBack = (n) => new Date(t.getFullYear(), t.getMonth() - (n - 1), 1);
  switch (key) {
    case "this-month": return [monthsBack(1), t];
    case "3m": return [monthsBack(3), t];
    case "12m": return [monthsBack(12), t];
    case "this-year": return [new Date(t.getFullYear(), 0, 1), t];
    default: return [monthsBack(6), t]; // 6m
  }
}

/** Khoảng liền trước, cùng độ dài, để so sánh */
export function previousRange(from, to) {
  const days = Math.round((parse(to) - parse(from)) / 86400000) + 1;
  const prevTo = new Date(parse(from).getTime() - 86400000);
  const prevFrom = new Date(prevTo.getTime() - (days - 1) * 86400000);
  return [iso(prevFrom), iso(prevTo)];
}

const PRESETS = [
  ["this-month", "Tháng này"],
  ["3m", "3 tháng"],
  ["6m", "6 tháng"],
  ["12m", "12 tháng"],
  ["this-year", "Năm nay"],
  ["custom", "Tùy chọn"],
];

const CSS = `
.page-reports { --ink:#464052; --muted:#6f687c; --line:#e9ddf7; --mist:#f3edfb; --brand-dark:#7a62a3;
  --grad: linear-gradient(100deg,#f0b0c3 0%,#d9b5d9 50%,#b6a1d4 100%); color: var(--ink); }
.page-reports .page-title { font-size: clamp(1.8rem,3vw,2.3rem); font-weight:800 !important; letter-spacing:-.03em; line-height:1.15;
  background: linear-gradient(95deg,#464052 0%,#7a62a3 60%,#c27a9b 100%); -webkit-background-clip:text; background-clip:text; color:transparent !important; }
.page-reports .page-title-ico { width:46px; height:46px; border-radius:14px; display:grid; place-items:center; flex:none; background:var(--grad); color:var(--ink); box-shadow:0 8px 18px -12px rgba(182,161,212,.9); }
.page-reports .page-title-ico svg { width:24px; height:24px; fill:none; stroke:currentColor; stroke-width:2; stroke-linecap:round; stroke-linejoin:round; }
.page-reports .card { border:1px solid var(--line); border-radius:16px; }
.page-reports .card-title { font-weight:700; }
.page-reports .form-select:focus, .page-reports .form-control:focus { border-color:#b6a1d4; box-shadow:0 0 0 .2rem rgba(182,161,212,.35); }
.page-reports .btn-soft { border:1px solid var(--line); background:#fff; color:var(--brand-dark); font-weight:600; border-radius:10px; }
.page-reports .btn-soft:hover { background:var(--mist); }
.rp-chips { display:flex; flex-wrap:wrap; gap:8px; }
.rp-chip { border:1px solid var(--line); background:#fff; color:var(--ink); border-radius:999px; padding:5px 12px; font-size:.875rem; }
.rp-chip:hover { background:var(--mist); }
.rp-chip[aria-pressed="true"] { background:var(--grad); border-color:transparent; font-weight:600; }
.seg { display:inline-flex; border:1px solid var(--line); border-radius:10px; overflow:hidden; background:#fff; }
.seg button { border:0; background:transparent; padding:6px 12px; font-size:.875rem; color:var(--ink); }
.seg button[aria-pressed="true"] { background:var(--grad); font-weight:600; }
.kpi { padding:16px 18px; height:100%; }
.kpi .lbl { color:var(--muted); font-size:.85rem; }
.kpi .val { font-size:1.45rem; font-weight:800; letter-spacing:-.02em; line-height:1.2; margin-top:2px; }
.kpi .sub { font-size:.8rem; color:var(--muted); margin-top:2px; }
.delta { display:inline-block; padding:1px 8px; border-radius:999px; font-size:.75rem; font-weight:700; }
.delta.up { background:#fdecf2; color:#b0587a; } .delta.down { background:#e6f6ee; color:#2f7a5a; } .delta.same { background:#efecf3; color:#5b5568; }
.chart-box { position:relative; height:300px; }
.chart-box.sm { height:220px; }
.cat-table { width:100%; font-size:.9rem; }
.cat-table td { padding:7px 4px; border-bottom:1px solid #f1ecf8; }
.cat-table tr:last-child td { border-bottom:0; }
.cat-dot { width:10px; height:10px; border-radius:3px; display:inline-block; margin-right:6px; }
.bar-line { height:6px; border-radius:999px; background:#efeaf6; margin-top:6px; overflow:hidden; }
.bar-line i { display:block; height:100%; background:linear-gradient(90deg,#d9b5d9,#b6a1d4); }
.merchants { list-style:none; margin:0; padding:0; display:grid; gap:12px; }
.rp-note { font-size:.8rem; color:var(--muted); }
@media (max-width: 575.98px) {
  .kpi { padding:12px 14px; } .kpi .val { font-size:1.15rem; } .kpi .sub:not(.keep) { display:none; }
  .chart-box { height:240px; }
}
`;
function ensureStyles() {
  if (document.getElementById("reports-css")) return;
  const st = document.createElement("style");
  st.id = "reports-css";
  st.textContent = CSS;
  document.head.appendChild(st);
}
const ICON = '<svg viewBox="0 0 24 24"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>';

function downloadCSV(r) {
  const rows = [["Kỳ", "Từ ngày", "Đến ngày", "Tổng (VND)"]];
  r.periods.forEach((p) => rows.push([p.label, p.start, p.end, Math.round(num(p.total))]));
  rows.push([], ["Danh mục", "Số hóa đơn", "Tổng (VND)", "%"]);
  r.by_category.forEach((c) => rows.push([c.category, c.receipt_count, Math.round(num(c.total)), c.percent]));
  const csv = "\ufeff" + rows.map((row) => row.map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`).join(",")).join("\r\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  a.download = `bao-cao-chi-tieu_${r.date_from}_${r.date_to}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function render(el, params) {
  ensureStyles();
  const [df, dt] = presetRange(params.preset ?? "6m");
  const state = {
    preset: PRESETS.some(([k]) => k === params.preset) ? params.preset : params.from ? "custom" : "6m",
    from: params.from ?? iso(df),
    to: params.to ?? iso(dt),
    granularity: ["auto", "day", "week", "month"].includes(params.g) ? params.g : "auto",
    scope: params.scope === "group" ? "group" : "me",
    groupId: params.group ?? "",
    chartMode: "stack",
    groups: [],
  };
  const charts = [];
  window.addEventListener("hashchange", () => charts.forEach((c) => c.destroy()), { once: true });

  el.innerHTML = `<div class="page-reports">
    <div class="d-flex flex-wrap align-items-center gap-3 mb-3">
      <span class="page-title-ico" aria-hidden="true">${ICON}</span>
      <div class="flex-grow-1">
        <h2 class="page-title mb-0">Báo cáo chi tiêu</h2>
        <div class="text-muted">Theo thời gian và danh mục · chỉ tính hóa đơn <b>đã chốt chia</b></div>
      </div>
      <button type="button" class="btn btn-soft" id="btn-csv" disabled>⤓ Tải CSV</button>
    </div>
    <div class="card mb-3"><div class="card-body" id="filters"></div></div>
    <div id="report"></div>
  </div>`;
  const filters = el.querySelector("#filters");
  const box = el.querySelector("#report");
  const csvBtn = el.querySelector("#btn-csv");
  let current = null;
  csvBtn.onclick = () => current && downloadCSV(current);

  const syncUrl = () => {
    const qs = new URLSearchParams();
    if (state.preset === "custom") qs.set("from", state.from), qs.set("to", state.to);
    else if (state.preset !== "6m") qs.set("preset", state.preset);
    if (state.granularity !== "auto") qs.set("g", state.granularity);
    if (state.scope !== "me") qs.set("scope", state.scope);
    if (state.groupId) qs.set("group", state.groupId);
    history.replaceState(null, "", `#/reports${qs.toString() ? `?${qs}` : ""}`);
  };

  function paintFilters() {
    filters.innerHTML = `
      <div class="d-flex flex-wrap gap-3 align-items-end justify-content-between">
        <div>
          <div class="form-label mb-1">Khoảng thời gian</div>
          <div class="rp-chips" role="group" aria-label="Khoảng thời gian">
            ${PRESETS.map(([k, t]) => `<button type="button" class="rp-chip" data-preset="${k}" aria-pressed="${state.preset === k}">${t}</button>`).join("")}
          </div>
        </div>
        <div class="d-flex flex-wrap gap-2 align-items-end">
          <div>
            <label class="form-label mb-1" for="f-g">Gom theo</label>
            <select class="form-select form-select-sm" id="f-g">
              ${[["auto", "Tự động"], ["day", "Ngày"], ["week", "Tuần"], ["month", "Tháng"]].map(([v, t]) => `<option value="${v}" ${state.granularity === v ? "selected" : ""}>${t}</option>`).join("")}
            </select>
          </div>
          <div>
            <label class="form-label mb-1" for="f-group">Nhóm</label>
            <select class="form-select form-select-sm" id="f-group">
              <option value="">${state.scope === "me" ? "Tất cả (kể cả hóa đơn cá nhân)" : "Tất cả nhóm"}</option>
              ${state.groups.map((g) => `<option value="${g.id}" ${String(g.id) === String(state.groupId) ? "selected" : ""}>${esc(g.name)}</option>`).join("")}
            </select>
          </div>
          <div>
            <div class="form-label mb-1">Tính theo</div>
            <div class="seg" role="group" aria-label="Tính theo">
              <button type="button" data-scope="me" aria-pressed="${state.scope === "me"}" title="Chỉ phần tiền của bạn trong mỗi hóa đơn">Phần của tôi</button>
              <button type="button" data-scope="group" aria-pressed="${state.scope === "group"}" title="Tổng tiền cả hóa đơn của nhóm">Cả nhóm</button>
            </div>
          </div>
        </div>
      </div>
      <div class="d-flex flex-wrap gap-2 align-items-end mt-3 ${state.preset === "custom" ? "" : "d-none"}" id="custom">
        <div><label class="form-label mb-1" for="f-from">Từ ngày</label><input type="date" class="form-control form-control-sm" id="f-from" value="${state.from}" max="${iso(new Date())}"></div>
        <div><label class="form-label mb-1" for="f-to">Đến ngày</label><input type="date" class="form-control form-control-sm" id="f-to" value="${state.to}"></div>
        <button type="button" class="btn btn-sm btn-soft" id="btn-apply">Xem báo cáo</button>
        <div class="invalid-feedback d-block" id="range-err"></div>
      </div>`;

    filters.querySelectorAll("[data-preset]").forEach((b) => {
      b.onclick = () => {
        state.preset = b.dataset.preset;
        if (state.preset !== "custom") {
          const [f, t] = presetRange(state.preset);
          state.from = iso(f);
          state.to = iso(t);
          load();
        }
        paintFilters();
      };
    });
    filters.querySelector("#f-g").onchange = (e) => ((state.granularity = e.target.value), load());
    filters.querySelector("#f-group").onchange = (e) => ((state.groupId = e.target.value), load());
    filters.querySelectorAll("[data-scope]").forEach((b) => (b.onclick = () => ((state.scope = b.dataset.scope), paintFilters(), load())));
    filters.querySelector("#btn-apply").onclick = () => {
      const f = filters.querySelector("#f-from").value;
      const t = filters.querySelector("#f-to").value;
      const err = filters.querySelector("#range-err");
      err.textContent = !f || !t ? "Chọn đủ hai ngày" : f > t ? "Ngày bắt đầu phải trước ngày kết thúc" : "";
      if (err.textContent) return;
      Object.assign(state, { from: f, to: t });
      load();
    };
  }

  const query = (from, to) => {
    const qs = new URLSearchParams({ date_from: from, date_to: to, granularity: state.granularity, scope: state.scope });
    if (state.groupId) qs.set("group_id", state.groupId);
    return get(`/dashboard/report?${qs}`);
  };

  let seq = 0;
  async function load() {
    syncUrl();
    const my = ++seq;
    box.innerHTML = `<div class="card"><div class="card-body"><div class="ui-skeleton">${'<div class="ui-skeleton-row"></div>'.repeat(5)}</div></div></div>`;
    csvBtn.disabled = true;
    let r, prev;
    try {
      [r, prev] = await Promise.all([query(state.from, state.to), query(...previousRange(state.from, state.to)).catch(() => null)]);
    } catch (e) {
      if (my !== seq) return;
      box.innerHTML = `<div class="card"><div class="card-body">${emptyHTML(e.message)}</div></div>`;
      if (e.status === 422) toast.error(e);
      return;
    }
    if (my !== seq) return; // đã đổi bộ lọc trong lúc chờ
    current = r;
    paint(r, prev);
  }

  function paint(r, prev) {
    charts.splice(0).forEach((c) => c.destroy());
    const total = num(r.total);
    const unit = UNIT[r.granularity];
    csvBtn.disabled = total === 0;
    const rangeText = `${fmtDate(r.date_from)} – ${fmtDate(r.date_to)}`;
    if (total === 0) {
      box.innerHTML = `<div class="card"><div class="card-body">${emptyHTML(
        `Chưa có hóa đơn đã chốt chia nào trong khoảng ${rangeText}${state.groupId ? " của nhóm này" : ""}. Báo cáo chỉ tính các hóa đơn đã được Trưởng nhóm chốt chia.`,
        { actionText: "Xem hóa đơn", actionHref: "#/receipts" },
      )}</div></div>`;
      return;
    }
    const prevTotal = prev ? num(prev.total) : null;
    let delta = "";
    if (prevTotal !== null) {
      if (prevTotal === 0) delta = `<span class="delta same">Kỳ trước chưa có chi tiêu</span>`;
      else {
        const pct = Math.round(((total - prevTotal) / prevTotal) * 100);
        delta = `<span class="delta ${pct > 0 ? "up" : pct < 0 ? "down" : "same"}">${pct > 0 ? "▲" : pct < 0 ? "▼" : "="} ${Math.abs(pct)}% so với kỳ trước</span>`;
      }
    }
    const top = r.by_category[0];
    const peak = r.periods.reduce((a, b) => (num(b.total) > num(a.total) ? b : a), r.periods[0]);
    const cats = r.by_category.map((c) => c.category);
    const colorOf = new Map(cats.map((c, i) => [c, COLORS[i % COLORS.length]]));
    const maxMerchant = Math.max(1, ...r.top_merchants.map((m) => num(m.total)));

    box.innerHTML = `
      <div class="rp-note mb-2">${rangeText} · ${r.scope === "me" ? "phần chi tiêu của bạn" : "tổng tiền hóa đơn của nhóm"} · gom theo ${unit}</div>
      <div class="row g-3 mb-3">
        <div class="col-6 col-xl-3"><div class="card kpi"><div class="lbl">Tổng chi</div><div class="val">${formatVND(total)}</div><div class="sub keep">${delta}</div></div></div>
        <div class="col-6 col-xl-3"><div class="card kpi"><div class="lbl">Số hóa đơn</div><div class="val">${r.receipt_count}</div><div class="sub">đã chốt chia</div></div></div>
        <div class="col-6 col-xl-3"><div class="card kpi"><div class="lbl">Trung bình mỗi ${unit}</div><div class="val">${formatVND(r.average_per_period)}</div><div class="sub">${unit} cao nhất: ${esc(peak.label)} (${formatVNDShort(peak.total)})</div></div></div>
        <div class="col-6 col-xl-3"><div class="card kpi"><div class="lbl">Danh mục lớn nhất</div><div class="val text-truncate">${esc(top.category)}</div><div class="sub">${top.percent}% · ${formatVND(top.total)}</div></div></div>
      </div>

      <div class="card mb-3"><div class="card-body">
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-2">
          <h5 class="card-title mb-0">Chi tiêu theo thời gian</h5>
          <div class="seg" role="group" aria-label="Kiểu biểu đồ">
            <button type="button" data-mode="stack" aria-pressed="${state.chartMode === "stack"}">Theo danh mục</button>
            <button type="button" data-mode="total" aria-pressed="${state.chartMode === "total"}">Tổng</button>
          </div>
        </div>
        <div class="chart-box"><canvas id="c-time" aria-label="Biểu đồ chi tiêu theo ${unit}" role="img"></canvas></div>
      </div></div>

      <div class="row g-3">
        <div class="col-lg-7"><div class="card h-100"><div class="card-body">
          <h5 class="card-title">Theo danh mục</h5>
          <div class="row g-3 align-items-center">
            <div class="col-sm-5"><div class="chart-box sm"><canvas id="c-cat" role="img" aria-label="Tỉ lệ chi tiêu theo danh mục"></canvas></div></div>
            <div class="col-sm-7">
              <table class="cat-table"><tbody>${r.by_category
                .map((c) => `<tr><td><span class="cat-dot" style="background:${colorOf.get(c.category)}"></span>${esc(c.category)}</td>
                  <td class="text-muted text-end">${c.receipt_count} HĐ</td><td class="text-end">${c.percent}%</td><td class="text-end fw-semibold">${formatVND(c.total)}</td></tr>`)
                .join("")}</tbody></table>
            </div>
          </div>
        </div></div></div>
        <div class="col-lg-5"><div class="card h-100"><div class="card-body">
          <h5 class="card-title">Chi nhiều nhất ở đâu</h5>
          ${r.top_merchants.length
            ? `<ul class="merchants">${r.top_merchants
                .map((m) => `<li><div class="d-flex justify-content-between gap-2"><span class="text-truncate">${esc(m.merchant)} <span class="text-muted small">· ${m.receipt_count} lần</span></span><b>${formatVND(m.total)}</b></div>
                  <div class="bar-line"><i style="width:${(num(m.total) / maxMerchant) * 100}%"></i></div></li>`)
                .join("")}</ul>`
            : '<div class="text-muted small">Các hóa đơn chưa có tên cửa hàng.</div>'}
        </div></div></div>
      </div>`;

    if (!window.Chart) return;
    const money = { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${formatVND(ctx.parsed.y ?? ctx.parsed)}` } };
    const labels = r.periods.map((p) => p.label);
    const datasets =
      state.chartMode === "stack"
        ? cats.map((c) => ({ label: c, data: r.periods.map((p) => num(p.by_category[c])), backgroundColor: colorOf.get(c), borderRadius: 4, stack: "s" }))
        : [{ label: "Tổng chi", data: r.periods.map((p) => num(p.total)), backgroundColor: "#b6a1d4", hoverBackgroundColor: "#f0b0c3", borderRadius: 6 }];
    charts.push(
      new Chart(box.querySelector("#c-time"), {
        type: "bar",
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: state.chartMode === "stack", position: "bottom", labels: { boxWidth: 12 } },
            tooltip: {
              ...money,
              callbacks: {
                ...money.callbacks,
                title: (items) => {
                  const p = r.periods[items[0].dataIndex];
                  return p.start === p.end ? fmtDate(p.start) : `${fmtDate(p.start)} – ${fmtDate(p.end)}`;
                },
                footer: (items) => (state.chartMode === "stack" ? `Tổng: ${formatVND(r.periods[items[0].dataIndex].total)}` : ""),
              },
            },
          },
          scales: {
            x: { stacked: state.chartMode === "stack", grid: { display: false } },
            y: { stacked: state.chartMode === "stack", beginAtZero: true, ticks: { callback: (v) => formatVNDShort(v) } },
          },
        },
      }),
      new Chart(box.querySelector("#c-cat"), {
        type: "doughnut",
        data: { labels: cats, datasets: [{ data: r.by_category.map((c) => num(c.total)), backgroundColor: cats.map((c) => colorOf.get(c)), borderColor: "#fff", borderWidth: 3 }] },
        options: { responsive: true, maintainAspectRatio: false, cutout: "65%", plugins: { legend: { display: false }, tooltip: { callbacks: { label: (ctx) => `${ctx.label}: ${formatVND(ctx.parsed)}` } } } },
      }),
    );
    box.querySelectorAll("[data-mode]").forEach((b) => (b.onclick = () => ((state.chartMode = b.dataset.mode), paint(r, prev))));
  }

  get("/groups")
    .then((g) => (state.groups = g))
    .catch(() => {})
    .finally(() => {
      if (state.groupId && !state.groups.some((g) => String(g.id) === String(state.groupId))) state.groupId = "";
      paintFilters();
      load();
    });
}
