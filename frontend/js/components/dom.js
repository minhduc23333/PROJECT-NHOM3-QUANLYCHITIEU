// Tiện ích dùng chung cho mọi component.

/** Chống chèn HTML: luôn esc() dữ liệu người dùng trước khi ghép vào chuỗi HTML. */
export function esc(s) {
  return String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c],
  );
}

// Biểu tượng SVG nhỏ dùng trong các trạng thái
export const ICONS = {
  empty:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16l-1.5 11a2 2 0 0 1-2 1.7H7.5a2 2 0 0 1-2-1.7L4 7z"/><path d="M9 7V5a3 3 0 0 1 6 0v2"/></svg>',
  error:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.5v.01"/></svg>',
  success:
    '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8 12.5 2.7 2.7L16.5 9.5"/></svg>',
};
