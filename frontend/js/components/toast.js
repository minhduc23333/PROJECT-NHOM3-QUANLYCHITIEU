// Thông báo nổi ở góc màn hình (thành công / thông tin / lỗi), tự ẩn sau 3 giây.
import { esc } from "./dom.js";

function toastBox() {
  let c = document.getElementById("toasts");
  if (!c) {
    c = document.createElement("div");
    c.id = "toasts";
    c.className = "toast-container position-fixed end-0 p-3";
    c.style.top = "56px"; // nằm dưới thanh điều hướng
    c.setAttribute("aria-live", "polite");
    document.body.appendChild(c);
  }
  return c;
}

function showToast(text, kind) {
  const el = document.createElement("div");
  el.className = `toast align-items-center text-bg-${kind} border-0`;
  el.setAttribute("role", kind === "danger" ? "alert" : "status");
  el.innerHTML = `<div class="d-flex"><div class="toast-body">${esc(text)}</div>
    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Đóng"></button></div>`;
  toastBox().appendChild(el);
  el.addEventListener("hidden.bs.toast", () => el.remove());
  if (window.bootstrap?.Toast) {
    new bootstrap.Toast(el, { delay: 3000 }).show();
  } else {
    // Bootstrap chưa tải được: vẫn hiện thông báo và tự ẩn, không làm hỏng luồng đang chạy
    el.classList.add("show");
    el.querySelector(".btn-close").onclick = () => el.remove();
    setTimeout(() => el.remove(), 3000);
  }
}

export const toast = {
  success: (t) => showToast(t, "success"),
  info: (t) => showToast(t, "primary"),
  error: (e) => showToast(typeof e === "string" ? e : (e?.message ?? "Có lỗi xảy ra"), "danger"),
};
