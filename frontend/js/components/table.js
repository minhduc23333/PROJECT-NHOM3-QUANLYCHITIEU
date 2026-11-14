// Bảng dữ liệu: cột tiền canh phải, có dòng tổng, tự hiện trạng thái trống.
import { esc } from "./dom.js";
import { emptyHTML } from "./state.js";

/**
 * dataTable(
 *   [{ key: "name", title: "Món" }, { key: "amount", title: "Tiền", align: "end", render: (v) => formatVND(v) }],
 *   rows,
 *   { emptyText: "Chưa có món", footer: { name: "Tổng", amount: formatVND(total) } },
 * )
 * Cột không có render -> tự esc(). Có render -> nhớ esc() phần dữ liệu người dùng trong render.
 * footer: giá trị đã định dạng sẵn theo key (không esc lại để có thể truyền HTML đơn giản).
 */
export function dataTable(columns, rows, { emptyText = "Chưa có dữ liệu", footer, caption } = {}) {
  if (!rows?.length) return emptyHTML(emptyText);
  const cls = (c) => (c.align === "end" ? "text-end text-nowrap" : c.align === "center" ? "text-center" : "");
  const head = columns.map((c) => `<th scope="col" class="${cls(c)}">${esc(c.title)}</th>`).join("");
  const body = rows
    .map((r) => `<tr>${columns.map((c) => `<td class="${cls(c)}">${c.render ? c.render(r[c.key], r) : esc(r[c.key])}</td>`).join("")}</tr>`)
    .join("");
  const foot = footer
    ? `<tfoot><tr>${columns.map((c) => `<td class="${cls(c)} fw-semibold">${footer[c.key] ?? ""}</td>`).join("")}</tr></tfoot>`
    : "";
  return `<div class="table-responsive"><table class="table table-hover align-middle ui-table">
    ${caption ? `<caption>${esc(caption)}</caption>` : ""}
    <thead class="table-light"><tr>${head}</tr></thead><tbody>${body}</tbody>${foot}</table></div>`;
}
