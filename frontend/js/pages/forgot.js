// Trang "Quên mật khẩu": nhập email -> hệ thống gửi liên kết đặt lại mật khẩu
import { post } from "../api.js";
import {
  clearFieldErrors,
  esc,
  formValues,
  handleFormError,
  showFieldErrors,
  withBusy,
} from "../ui.js";
import { EMAIL_RE, authField, mountAuth, shakeInvalid } from "./auth-shell.js";

function validate(form, { email }) {
  clearFieldErrors(form);
  const errs = [];
  if (!email.trim()) errs.push({ field: "email", message: "Nhập email đã đăng ký" });
  else if (!EMAIL_RE.test(email.trim()))
    errs.push({ field: "email", message: "Email chưa đúng định dạng, ví dụ ten@gmail.com" });
  showFieldErrors(form, errs);
  if (errs.length) {
    shakeInvalid(form);
    form.elements.email.focus();
  }
  return errs.length === 0;
}

export function render(el) {
  const remembered = sessionStorage.getItem("forgot_email") ?? "";
  sessionStorage.removeItem("forgot_email");
  const body = mountAuth(el, {
    mode: "forgot",
    title: "Quên mật khẩu?",
    sub: "Nhập email đã đăng ký, chúng tôi sẽ gửi liên kết để bạn đặt mật khẩu mới.",
    body: `<form id="forgot-form" novalidate>
        ${authField({ label: "Email", name: "email", type: "email", icon: "mail", placeholder: "ten@gmail.com", autocomplete: "email", value: remembered })}
        <button class="auth-submit" type="submit">Gửi liên kết đặt lại mật khẩu</button>
      </form>
      <div id="forgot-result"></div>
      <p class="auth-switch"><a href="#/login">← Quay lại đăng nhập</a></p>`,
  });

  const form = body.querySelector("#forgot-form");
  const result = body.querySelector("#forgot-result");
  form.elements.email.focus();

  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const data = formValues(form);
    if (!validate(form, data)) return;
    const btn = form.querySelector(".auth-submit");
    try {
      const res = await withBusy(btn, () => post("/auth/forgot-password", { email: data.email.trim() }));
      // Chỉ chế độ dev (chưa cấu hình SMTP) backend mới trả dev_reset_link để thử không cần email thật
      result.innerHTML = `<div class="auth-note" role="status">
          <strong>Đã gửi yêu cầu</strong>
          <p>${esc(res.message)}</p>
          ${res.dev_reset_link ? `<p class="auth-note-dev">Chế độ thử nghiệm (chưa cấu hình email): <a href="${esc(res.dev_reset_link)}">bấm vào đây để đặt lại mật khẩu</a></p>` : ""}
        </div>`;
      form.querySelector(".auth-submit").textContent = "Gửi lại liên kết";
    } catch (e) {
      handleFormError(form, e); // 422 -> đỏ ô email; 429 -> thông báo "thử quá nhiều lần"
      shakeInvalid(form);
    }
  };
}
