// Chart.js 4 được nạp bằng <script> trong index.html (biến toàn cục Chart)
import { formatVND, formatVNDShort } from "./format.js";

const instances = new WeakMap();
const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// Hiệu ứng hover cho biểu đồ cột (giống cách "hoverOffset" làm miếng biểu đồ tròn trồi ra):
// cột được hover phóng to nhẹ, nhô lên và đổ bóng, chuyển động mượt. Tắt nếu người dùng bật "giảm chuyển động".
const LIFT_PX = 8; // nhô lên tối đa
const LIFT_GROW = 0.12; // rộng thêm tối đa (12%)
const barHoverLift = {
  id: "barHoverLift",
  afterEvent(chart, args) {
    const s = (chart.$lift ??= { cur: [], target: -1, raf: 0 });
    const hit = args.event.type === "mouseout" ? [] : chart.getElementsAtEventForMode(args.event, "index", { intersect: false }, false);
    const next = hit.length ? hit[0].index : -1;
    chart.canvas.style.cursor = next >= 0 ? "pointer" : "default";
    if (next === s.target) return;
    s.target = next;
    if (reduceMotion()) {
      // Người dùng bật "giảm chuyển động": nhô lên ngay, không tween
      s.cur = Array.from({ length: chart.data.labels.length }, (_, i) => (i === next ? 1 : 0));
      chart.draw();
      return;
    }
    cancelAnimationFrame(s.raf);
    const tick = () => {
      let moving = false;
      const n = chart.data.labels.length;
      for (let i = 0; i < n; i++) {
        const goal = i === s.target ? 1 : 0;
        const cur = s.cur[i] ?? 0;
        const nv = Math.abs(goal - cur) < 0.02 ? goal : cur + (goal - cur) * 0.28; // easing-out
        if (nv !== goal) moving = true;
        s.cur[i] = nv;
      }
      chart.draw();
      if (moving && chart.canvas.isConnected) s.raf = requestAnimationFrame(tick);
    };
    s.raf = requestAnimationFrame(tick);
  },
  afterDatasetsDraw(chart) {
    const s = chart.$lift;
    if (!s) return;
    const meta = chart.getDatasetMeta(0);
    const { ctx } = chart;
    meta.data.forEach((bar, i) => {
      const p = s.cur[i] ?? 0;
      if (p <= 0.01) return;
      const { x, y, base, width } = bar.getProps(["x", "y", "base", "width"], true);
      const h = Math.abs(base - y);
      if (h < 1) return; // cột 0 đ: không có gì để nhô lên
      const w = width * (1 + LIFT_GROW * p);
      const top = Math.min(y, base) - LIFT_PX * p;
      const bottom = Math.max(y, base);
      ctx.save();
      ctx.shadowColor = `rgba(122, 98, 163, ${0.35 * p})`;
      ctx.shadowBlur = 14 * p;
      ctx.shadowOffsetY = 4 * p;
      const grad = ctx.createLinearGradient(0, top, 0, bottom);
      grad.addColorStop(0, "#f6c6d6");
      grad.addColorStop(1, "#f0b0c3");
      ctx.fillStyle = grad;
      ctx.beginPath();
      if (ctx.roundRect) ctx.roundRect(x - w / 2, top, w, bottom - top, [6, 6, 0, 0]);
      else ctx.rect(x - w / 2, top, w, bottom - top);
      ctx.fill();
      ctx.restore();
    });
  },
  beforeDestroy(chart) {
    if (chart.$lift) cancelAnimationFrame(chart.$lift.raf);
  },
};

/** barChartVND(canvas, ['2026-10','2026-11'], [120000, 90000], 'Chi tiêu') */
export function barChartVND(canvas, labels, values, label = "Số tiền") {
  instances.get(canvas)?.destroy(); // vẽ lại không bị chồng chart cũ
  const chart = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label, data: values, backgroundColor: "#b6a1d4", hoverBackgroundColor: "#f0b0c3", borderRadius: 6 },
      ],
    },
    plugins: [barHoverLift],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { top: LIFT_PX + 4 } }, // chừa chỗ để cột nhô lên không bị cắt
      interaction: { mode: "index", intersect: false }, // rê vào vùng cột (kể cả chỗ trống phía trên) vẫn nhận hover
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
