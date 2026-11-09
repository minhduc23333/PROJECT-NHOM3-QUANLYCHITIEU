import { get } from "../api.js";
import { barChartVND } from "../charts.js";
import { formatVND } from "../format.js";
import { esc, renderState } from "../ui.js";

const card = (title, value, cls = "") => `
  <div class="col-6 col-lg-3"><div class="card stat-card h-100"><div class="card-body">
    <div class="text-muted small">${esc(title)}</div>
    <div class="value ${cls}">${value}</div>
  </div></div></div>`;

export function render(el) {
  el.innerHTML = `<h2 class="mb-3">Tổng quan</h2><div id="dash"></div>`;

  renderState(
    el.querySelector("#dash"),
    () => get("/dashboard/summary"),
    (box, s) => {
      box.innerHTML = `
      <div class="row g-3 mb-4">
        ${card("Nhóm tham gia", s.group_count)}
        ${card("Hóa đơn", s.receipt_count)}
        ${card("Tôi đang nợ", formatVND(s.i_owe), "text-danger")}
        ${card("Người khác nợ tôi", formatVND(s.owed_to_me), "text-success")}
      </div>
      <div class="card"><div class="card-body">
        <h5 class="card-title">Chi tiêu tôi đã trả, 6 tháng gần nhất</h5>
        <div class="chart-box"><canvas id="chart-monthly"></canvas></div>
      </div></div>`;
      const labels = s.monthly.map((m) =>
        m.month.split("-").reverse().join("/"),
      );
      barChartVND(
        box.querySelector("#chart-monthly"),
        labels,
        s.monthly.map((m) => Number(m.total)),
        "Chi tiêu",
      );
    },
  );
}
