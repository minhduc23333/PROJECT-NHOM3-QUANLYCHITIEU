import { post } from "../api.js";
import { setSession } from "../auth.js";
import { navigate } from "../router.js";
import {
  clearFieldErrors,
  formValues,
  handleFormError,
  showFieldErrors,
  toast,
  withBusy,
} from "../ui.js";
import {
  EMAIL_RE,
  authField,
  goAfterLogin,
  mountAuth,
  shakeInvalid,
  showSuccess,
  wirePasswordFields,
} from "./auth-shell.js";

const IS_DEV = ["localhost", "127.0.0.1"].includes(location.hostname);
const REMEMBER_KEY = "smartsplit_last_email";

function validate(form, { email, password }) {
  clearFieldErrors(form);
  const errs = [];
  if (!email.trim())
    errs.push({ field: "email", message: "Nhập email của bạn" });
  else if (!EMAIL_RE.test(email.trim()))
    errs.push({
      field: "email",
      message: "Email chưa đúng định dạng, ví dụ ten@gmail.com",
    });
  if (!password) errs.push({ field: "password", message: "Nhập mật khẩu" });
  showFieldErrors(form, errs);
  if (errs.length) {
    shakeInvalid(form);
    form.elements[errs[0].field].focus();
  }
  return errs.length === 0;
}

export function render(el) {
  const remembered = localStorage.getItem(REMEMBER_KEY) ?? "";
  const body = mountAuth(el, {
    mode: "login",
    title: "Chào mừng trở lại",
    sub: "Đăng nhập để xem hóa đơn và công nợ của nhóm.",
    body: `<form id="login-form" novalidate>
        ${authField({ label: "Email", name: "email", type: "email", icon: "mail", placeholder: "ten@gmail.com", autocomplete: "username", value: remembered })}
        ${authField({ label: "Mật khẩu", name: "password", type: "password", icon: "lock", placeholder: "Mật khẩu của bạn", autocomplete: "current-password", toggle: true })}
        <div class="auth-row">
          <label class="auth-check"><input type="checkbox" name="remember" ${remembered ? "checked" : ""}> Ghi nhớ email</label>
        </div>
        <button class="auth-submit" type="submit">Đăng nhập</button>
      </form>
      ${
        IS_DEV
          ? `<div class="auth-divider">hoặc dùng thử</div>
        <div class="auth-demo"><span>Tài khoản demo: an@demo.vn / 123456</span>
        <button type="button" id="fill-demo">Điền sẵn</button></div>`
          : ""
      }
      <p class="auth-switch">Chưa có tài khoản? <a href="#/register">Tạo tài khoản</a></p>`,
  });

  const form = body.querySelector("#login-form");
  wirePasswordFields(form);
  (remembered ? form.elements.password : form.elements.email).focus();

  body.querySelector("#fill-demo")?.addEventListener("click", () => {
    form.elements.email.value = "an@demo.vn";
    form.elements.password.value = "123456";
    clearFieldErrors(form);
    form.querySelector(".auth-submit").focus();
  });

  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const data = formValues(form);
    if (!validate(form, data)) return;
    const btn = form.querySelector(".auth-submit");
    try {
      const email = data.email.trim();
      const res = await withBusy(btn, () =>
        post("/auth/login", { email, password: data.password }),
      );
      if (data.remember) localStorage.setItem(REMEMBER_KEY, email);
      else localStorage.removeItem(REMEMBER_KEY);
      setSession(res.access_token, res.user);
      await showSuccess(btn, "Đăng nhập thành công");
      toast.success(`Xin chào ${res.user.full_name}`);
      goAfterLogin(navigate);
    } catch (e) {
      if (e.status === 401) {
        // Sai email/mật khẩu: báo dưới ô mật khẩu, giữ email để sửa
        showFieldErrors(form, [{ field: "password", message: e.message }]);
        form.elements.password.select();
      } else {
        handleFormError(form, e);
      }
      shakeInvalid(form);
    }
  };
}
