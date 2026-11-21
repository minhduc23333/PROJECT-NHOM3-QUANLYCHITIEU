// Hộp thoại xác nhận trước khi làm thao tác quan trọng (xóa, chốt hóa đơn...).
import { esc } from "./dom.js";

/**
 * if (await confirmDialog({ title: "Xóa hóa đơn?", message: "Không hoàn tác được.", okText: "Xóa", danger: true })) { ... }
 * Trả về true nếu bấm nút đồng ý; false nếu bấm Hủy, dấu X, Esc hoặc bấm ra ngoài.
 */
export function confirmDialog({ title = "Xác nhận", message = "", okText = "Đồng ý", cancelText = "Hủy", danger = false } = {}) {
  if (!window.bootstrap?.Modal) return Promise.resolve(window.confirm(`${title}\n\n${message}`));
  return new Promise((resolve) => {
    const el = document.createElement("div");
    el.className = "modal fade";
    el.tabIndex = -1;
    el.setAttribute("aria-labelledby", "confirm-title");
    el.innerHTML = `<div class="modal-dialog modal-dialog-centered"><div class="modal-content">
      <div class="modal-header"><h5 class="modal-title" id="confirm-title">${esc(title)}</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Đóng"></button></div>
      ${message ? `<div class="modal-body">${esc(message)}</div>` : ""}
      <div class="modal-footer">
        <button type="button" class="btn btn-outline-secondary" data-bs-dismiss="modal">${esc(cancelText)}</button>
        <button type="button" class="btn btn-${danger ? "danger" : "primary"}" data-ok>${esc(okText)}</button>
      </div></div></div>`;
    document.body.appendChild(el);
    const modal = new bootstrap.Modal(el);
    let result = false;
    el.querySelector("[data-ok]").onclick = () => {
      result = true;
      modal.hide();
    };
    el.addEventListener("shown.bs.modal", () => el.querySelector("[data-ok]").focus());
    el.addEventListener("hidden.bs.modal", () => {
      el.remove();
      resolve(result);
    });
    modal.show();
  });
}
