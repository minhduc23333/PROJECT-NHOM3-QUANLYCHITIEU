// Trang "Đặt mật khẩu mới": mở từ liên kết trong email (#/reset-password/<token>)
import { post } from "../api.js";
import { navigate } from "../router.js";
import {
  clearFieldErrors,
  formValues,
  handleFormError,
  showFieldErrors,
  toast,
  withBusy,
} from "../ui.js";
import { authField, mountAuth, shakeInvalid, showSuccess, wirePasswordFields } from "./auth-shell.js";

function validate(form, d) {
  clearFieldErrors(form);
  const errs = [];
  if (d.password.length < 6) errs.push({ field: "password", message: "Mật khẩu cần ít nhất 6 ký tự" });
  else if (d.password.length > 72) errs.push({ field: "password", message: "Mật khẩu tối đa 72 ký tự" });
  if (!d.password2) errs.push({ field: "password2", message: "Nhập lại mật khẩu mới" });
  else if (d.password2 !== d.password) errs.push({ field: "password2", message: "Mật khẩu nhập lại không khớp" });
  showFieldErrors(form, errs);
  if (errs.length) {
    shakeInvalid(form);
    form.elements[errs[0].field].focus();
  }
  return errs.length === 0;
}

export function render(el, { token } = {}) {
  const body = mountAuth(el, {
    mode: "forgot",
    title: "Đặt mật khẩu mới",
    sub: "Chọn mật khẩu mới cho tài khoản của bạn. Liên kết chỉ dùng được một lần.",
    body: `<form id="reset-form" novalidate>
        ${authField({ label: "Mật khẩu mới", name: "password", type: "password", icon: "lock", placeholder: "Ít nhất 6 ký tự", autocomplete: "new-password", toggle: true })}
        ${authField({ label: "Nhập lại mật khẩu mới", name: "password2", type: "password", icon: "lock", placeholder: "Nhập lại mật khẩu mới", autocomplete: "new-password", toggle: true })}
        <button class="auth-submit" type="submit">Đặt lại mật khẩu</button>
      </form>
      <p class="auth-switch"><a href="#/login">← Quay lại đăng nhập</a></p>`,
  });

  const form = body.querySelector("#reset-form");
  wirePasswordFields(form);
  form.elements.password.focus();

  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const d = formValues(form);
    if (!validate(form, d)) return;
    const btn = form.querySelector(".auth-submit");
    try {
      await withBusy(btn, () => post("/auth/reset-password", { token, new_password: d.password }));
      await showSuccess(btn, "Đã đặt lại mật khẩu");
      navigate("/login"); // chuyển trang trước, thông báo sau
      toast.success("Đã đặt lại mật khẩu, hãy đăng nhập bằng mật khẩu mới");
    } catch (e) {
      if (e.code === "RESET_TOKEN_INVALID") {
        // Liên kết hết hạn / đã dùng: báo rõ và mời xin liên kết mới
        showFieldErrors(form, [{ field: "password", message: e.message }]);
        body.querySelector(".auth-switch").innerHTML =
          '<a href="#/forgot-password">Gửi lại liên kết đặt mật khẩu mới</a> · <a href="#/login">Đăng nhập</a>';
      } else {
        handleFormError(form, e);
      }
      shakeInvalid(form);
    }
  };
}
