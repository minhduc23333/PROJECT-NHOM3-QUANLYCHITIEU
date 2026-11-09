const vnd = new Intl.NumberFormat("vi-VN", {
  style: "currency",
  currency: "VND",
  maximumFractionDigits: 0,
});
const num = new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 });

// formatVND(90000) -> "90.000 ₫" ; formatVND("90000.00") -> "90.000 ₫"
export function formatVND(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  return Number.isFinite(n) ? vnd.format(n) : "—";
}

// Rút gọn cho trục biểu đồ: 1.500.000 -> "1,5 tr"
export function formatVNDShort(value) {
  const n = Number(value) || 0;
  if (Math.abs(n) >= 1e9)
    return `${(n / 1e9).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} tỷ`;
  if (Math.abs(n) >= 1e6)
    return `${(n / 1e6).toLocaleString("vi-VN", { maximumFractionDigits: 1 })} tr`;
  if (Math.abs(n) >= 1e3)
    return `${(n / 1e3).toLocaleString("vi-VN", { maximumFractionDigits: 0 })}k`;
  return num.format(n);
}

// Ô nhập tiền: "90.000" -> 90000
export const parseVND = (text) =>
  Number(String(text ?? "").replace(/[^\d-]/g, "")) || 0;

export function formatDate(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString("vi-VN");
}

export function formatDateTime(value) {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleString("vi-VN", { dateStyle: "short", timeStyle: "short" });
}
