// Chart.js 4 được nạp bằng <script> trong index.html (biến toàn cục Chart)
import { formatVND, formatVNDShort } from "./format.js";

const instances = new WeakMap();

/** barChartVND(canvas, ['2026-10','2026-11'], [120000, 90000], 'Chi tiêu') */
export function barChartVND(canvas, labels, values, label = "Số tiền") {
  instances.get(canvas)?.destroy(); // vẽ lại không bị chồng chart cũ
  const chart = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label, data: values, backgroundColor: "#0d6efd", borderRadius: 4 },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => formatVND(ctx.parsed.y) } },
      },
      scales: {
        y: { beginAtZero: true, ticks: { callback: (v) => formatVNDShort(v) } },
      },
    },
  });
  instances.set(canvas, chart);
  return chart;
}
