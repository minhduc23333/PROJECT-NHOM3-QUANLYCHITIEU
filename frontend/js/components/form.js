// Form field (input / select / textarea / tiền VND) + kiểm tra lỗi + hiển thị lỗi từ server.
import { formatNumber, parseVND } from "../format.js";
import { esc } from "./dom.js";
import { toast } from "./toast.js";

const labelHTML = (name, label, required) =>
  `<label class="form-label" for="f-${name}">${esc(label)}${required ? ' <span class="text-danger" aria-hidden="true">*</span>' : ""}</label>`;
const hintHTML = (name, hint) => (hint ? `<div class="form-text" id="h-${name}">${esc(hint)}</div>` : "");

/** field({ label: "Email", name: "email", type: "email", required: true, hint: "Email dùng để đăng nhập" }) */
export function field({ label, name, type = "text", required = false, placeholder = "", value = "", attrs = "", hint = "" }) {
  return `<div class="mb-3">
    ${labelHTML(name, label, required)}
    <input class="form-control" id="f-${name}" name="${name}" type="${type}" ${required ? "required" : ""}
           placeholder="${esc(placeholder)}" value="${esc(value)}" ${hint ? `aria-describedby="h-${name}"` : ""} ${attrs}>
    <div class="invalid-feedback"></div>
    ${hintHTML(name, hint)}
  </div>`;
}

/** selectField({ label: "Nhóm", name: "group_id", options: [{ value: 1, text: "Nhóm A" }], value: 1 }) */
export function selectField({ label, name, options = [], required = false, value = "", placeholder = "" }) {
  const opts = options
    .map((o) => `<option value="${esc(o.value)}" ${String(o.value) === String(value) ? "selected" : ""}>${esc(o.text)}</option>`)
    .join("");
  return `<div class="mb-3">
    ${labelHTML(name, label, required)}
    <select class="form-select" id="f-${name}" name="${name}" ${required ? "required" : ""}>
      ${placeholder ? `<option value="">${esc(placeholder)}</option>` : ""}${opts}
    </select>
    <div class="invalid-feedback"></div>
  </div>`;
}

export function textareaField({ label, name, required = false, placeholder = "", value = "", rows = 3 }) {
  return `<div class="mb-3">
    ${labelHTML(name, label, required)}
    <textarea class="form-control" id="f-${name}" name="${name}" rows="${rows}" ${required ? "required" : ""}
              placeholder="${esc(placeholder)}">${esc(value)}</textarea>
    <div class="invalid-feedback"></div>
  </div>`;
}

/**
 * Ô nhập tiền VND: tự thêm dấu chấm khi gõ (90000 -> 90.000), đuôi "₫".
 * Lấy số khi submit: moneyValue(form.elements.amount) -> 90000
 * Sau khi chèn HTML vào trang, gọi bindMoneyInputs(container) để bật tự định dạng.
 */
export function moneyField({ label, name, required = false, value = "", placeholder = "0", hint = "" }) {
  const shown = value === "" || value == null ? "" : formatNumber(value);
  return `<div class="mb-3">
    ${labelHTML(name, label, required)}
    <div class="input-group has-validation">
      <input class="form-control text-end" id="f-${name}" name="${name}" inputmode="numeric" autocomplete="off"
             data-money ${required ? "required" : ""} placeholder="${esc(placeholder)}" value="${esc(shown)}">
      <span class="input-group-text">₫</span>
      <div class="invalid-feedback"></div>
    </div>
    ${hintHTML(name, hint)}
  </div>`;
}

export function bindMoneyInputs(root) {
  root.querySelectorAll("input[data-money]").forEach((input) => {
    input.addEventListener("input", () => {
      const digits = input.value.replace(/\D/g, "");
      input.value = digits ? formatNumber(Number(digits)) : "";
    });
  });
}

export const moneyValue = (input) => parseVND(input.value);

export const formValues = (form) => Object.fromEntries(new FormData(form));

const feedbackOf = (input) =>
  input.closest(".input-group")?.querySelector(".invalid-feedback") ??
  input.parentElement.querySelector(".invalid-feedback");

export function clearFieldErrors(form) {
  form.querySelectorAll(".is-invalid").forEach((i) => {
    i.classList.remove("is-invalid");
    i.removeAttribute("aria-invalid");
    const fb = feedbackOf(i);
    if (fb) fb.textContent = "";
  });
}

/** details từ backend (lỗi 422/409): [{ field: "email", message: "..." }] -> tô đỏ đúng ô */
export function showFieldErrors(form, details) {
  for (const d of details ?? []) {
    const input = form.elements[d.field];
    if (input) {
      input.classList.add("is-invalid");
      input.setAttribute("aria-invalid", "true");
      const fb = feedbackOf(input);
      if (fb) fb.textContent = d.message;
    }
  }
}

/** Kiểm tra các ô required phía trình duyệt. Trả về true nếu hợp lệ, false thì focus ô lỗi đầu tiên. */
export function validateRequired(form) {
  clearFieldErrors(form);
  const missing = [...form.elements]
    .filter((el) => el.required && !String(el.value).trim())
    .map((el) => ({ field: el.name, message: "Không được để trống" }));
  showFieldErrors(form, missing);
  if (missing.length) form.elements[missing[0].field]?.focus();
  return missing.length === 0;
}

/** Lỗi khi submit: có details -> đỏ từng ô; không có -> toast. */
export function handleFormError(form, e) {
  if (e?.details?.length) showFieldErrors(form, e.details);
  else toast.error(e);
}

/** Khóa nút + spinner trong lúc chờ: await withBusy(btn, () => post(...)) */
export async function withBusy(button, fn) {
  const html = button.innerHTML;
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  button.innerHTML = `<span class="spinner-border spinner-border-sm me-1" aria-hidden="true"></span>${html}`;
  try {
    return await fn();
  } finally {
    button.disabled = false;
    button.removeAttribute("aria-busy");
    button.innerHTML = html;
  }
}
