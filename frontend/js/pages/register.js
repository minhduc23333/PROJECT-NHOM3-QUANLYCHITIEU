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

// 0 = trống, 1 = yếu, 2 = vừa, 3 = mạnh
function strength(pw) {
  if (!pw) return 0;
  if (pw.length < 6) return 1;
  let score = 0;
  if (pw.length >= 8) score++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++;
  if (/\d/.test(pw)) score++;
  if (/[^A-Za-z0-9]/.test(pw)) score++;
  return score <= 1 ? 1 : score === 2 ? 2 : 3;
}
const STRENGTH_TEXT = [
  "Ít nhất 6 ký tự",
  "Mật khẩu yếu, thêm chữ hoa, số hoặc ký tự đặc biệt",
  "Mật khẩu tạm ổn",
  "Mật khẩu mạnh",
];

function validate(form, d) {
  clearFieldErrors(form);
  const errs = [];
  if (d.full_name.trim().length < 2)
    errs.push({ field: "full_name", message: "Nhập họ tên, ít nhất 2 ký tự" });
  if (!d.email.trim())
    errs.push({ field: "email", message: "Nhập email của bạn" });
  else if (!EMAIL_RE.test(d.email.trim()))
    errs.push({
      field: "email",
      message: "Email chưa đúng định dạng, ví dụ ten@gmail.com",
    });
  if (d.password.length < 6)
    errs.push({ field: "password", message: "Mật khẩu cần ít nhất 6 ký tự" });
  else if (d.password.length > 72)
    errs.push({ field: "password", message: "Mật khẩu tối đa 72 ký tự" });
  if (!d.password2)
    errs.push({ field: "password2", message: "Nhập lại mật khẩu" });
  else if (d.password2 !== d.password)
    errs.push({ field: "password2", message: "Mật khẩu nhập lại không khớp" });
  showFieldErrors(form, errs);

  const agree = form.querySelector(".auth-check");
  agree.classList.toggle("is-invalid", !d.agree);

  if (errs.length) form.elements[errs[0].field].focus();
  else if (!d.agree) form.elements.agree.focus();
  if (errs.length || !d.agree) shakeInvalid(form);
  return errs.length === 0 && !!d.agree;
}

export function render(el) {
  const body = mountAuth(el, {
    mode: "register",
    title: "Tạo tài khoản",
    sub: "Chỉ mất một phút, sau đó bạn có thể tạo nhóm và mời bạn bè.",
    body: `<form id="register-form" novalidate>
        ${authField({ label: "Họ tên", name: "full_name", icon: "user", placeholder: "Nguyễn Văn An", autocomplete: "name" })}
        ${authField({ label: "Email", name: "email", type: "email", icon: "mail", placeholder: "ten@gmail.com", autocomplete: "email" })}
        ${authField({ label: "Mật khẩu", name: "password", type: "password", icon: "lock", placeholder: "Ít nhất 6 ký tự", autocomplete: "new-password", toggle: true, meter: true, hint: STRENGTH_TEXT[0] })}
        ${authField({ label: "Nhập lại mật khẩu", name: "password2", type: "password", icon: "lock", placeholder: "Nhập lại mật khẩu", autocomplete: "new-password", toggle: true })}
        <div class="auth-row">
          <label class="auth-check"><input type="checkbox" name="agree">
            Tôi đồng ý để thành viên trong nhóm thấy họ tên và email của tôi</label>
        </div>
        <button class="auth-submit" type="submit">Tạo tài khoản</button>
      </form>
      <p class="auth-switch">Đã có tài khoản? <a href="#/login">Đăng nhập</a></p>`,
  });

  const form = body.querySelector("#register-form");
  wirePasswordFields(form);
  form.elements.full_name.focus();

  const meter = form.querySelector(".pw-meter");
  const hint = form.querySelector('[data-hint="password"]');
  const pw2Hint = form.querySelector('[data-hint="password2"]');
  const syncMatch = () => {
    const { password, password2 } = form.elements;
    pw2Hint.textContent =
      password2.value && password2.value === password.value
        ? "Mật khẩu khớp"
        : "";
    pw2Hint.style.color = pw2Hint.textContent ? "var(--brand-dark)" : "";
  };
  form.elements.password.addEventListener("input", (e) => {
    const lv = strength(e.target.value);
    meter.dataset.level = lv;
    hint.dataset.base = STRENGTH_TEXT[lv];
    if (!hint.classList.contains("warn")) hint.textContent = STRENGTH_TEXT[lv];
    syncMatch();
  });
  form.elements.password2.addEventListener("input", syncMatch);
  form.elements.agree.addEventListener("change", (e) => {
    if (e.target.checked)
      form.querySelector(".auth-check").classList.remove("is-invalid");
  });

  form.onsubmit = async (ev) => {
    ev.preventDefault();
    const d = formValues(form);
    if (!validate(form, d)) return;
    const btn = form.querySelector(".auth-submit");
    try {
      const res = await withBusy(btn, () =>
        post("/auth/register", {
          full_name: d.full_name.trim(),
          email: d.email.trim(),
          password: d.password,
        }),
      );
      setSession(res.access_token, res.user);
      await showSuccess(btn, "Đã tạo tài khoản");
      toast.success(`Chào mừng ${res.user.full_name}`);
      goAfterLogin(navigate);
    } catch (e) {
      handleFormError(form, e); // 409 trùng email -> đỏ ô email, 422 -> đỏ từng ô
      shakeInvalid(form);
    }
  };
}
