// Khung chung cho trang đăng nhập / đăng ký.
// Cột trái: nền gradient + hóa đơn minh họa có hiệu ứng in. Cột phải: form.
// Khi chuyển qua lại giữa 2 trang, khung được giữ nguyên, chỉ thay phần form (không chạy lại hiệu ứng in).
import { formatVND } from "../format.js";
import { esc } from "../ui.js";

const LOGO = `<span class="auth-brand-mark" aria-hidden="true">
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
    <path d="M6 3h12v18l-3-2-3 2-3-2-3 2z"/><path d="M9.5 8h5M9.5 12h5"/></svg></span>`;
const brand = () =>
  `<a class="auth-brand" href="#/login">${LOGO}SmartSplit AI</a>`;

export const ICONS = {
  mail: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>',
  lock: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>',
  user: '<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/></svg>',
  check:
    '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>',
};

// Hóa đơn mẫu: các số cộng lại đúng (tổng 180.000 = 85.000 + 75.000 + 20.000)
const ITEMS = [
  { name: "Phở bò tái", price: 65000, who: [["An", true]] },
  { name: "Bún chả", price: 55000, who: [["Bình"]] },
  {
    name: "Gỏi cuốn (3 cuốn)",
    price: 45000,
    who: [["An", true], ["Bình"], ["Chi"]],
  },
  { name: "Trà đá × 3", price: 15000, who: [["An", true], ["Bình"], ["Chi"]] },
];
const SPLIT = [
  ["An", 85000, true],
  ["Bình", 75000],
  ["Chi", 20000],
];

function receipt() {
  let i = 0;
  const items = ITEMS.map(
    (it) => `<li>
      <span>${esc(it.name)}</span><span>${formatVND(it.price)}</span>
      <span class="who">${it.who.map(([n, me]) => `<span class="chip${me ? " me" : ""}" style="--i:${i++}">${esc(n)}</span>`).join("")}</span>
    </li>`,
  ).join("");
  const total = ITEMS.reduce((s, it) => s + it.price, 0);
  const split = SPLIT.map(
    ([n, v, me]) =>
      `<div class="${me ? "me" : ""}"><span>${esc(n)}</span><span data-count="${v}">${formatVND(v)}</span></div>`,
  ).join("");
  return `<div class="receipt-stage" aria-hidden="true">
    <div class="printer"></div>
    <div class="receipt-slot"><div class="receipt-tilt"><div class="receipt">
      <div class="receipt-head"><strong>Quán Phở Hòa</strong><span>Bàn 4, 19:42</span></div>
      <ul class="receipt-items">${items}</ul>
      <div class="receipt-total"><span>Tổng cộng</span><span>${formatVND(total)}</span></div>
      <div class="receipt-split">${split}</div>
    </div></div></div>
    <div class="float-badge fb1"><span class="dot"></span>Đã đọc 4 món</div>
    <div class="float-badge fb2">Thuế và phí chia đều</div>
  </div>`;
}

const reduceMotion = () =>
  matchMedia("(prefers-reduced-motion: reduce)").matches;

// Số tiền ở phần chia đếm từ 0 lên khi hóa đơn in xong
function countUp(root) {
  root.querySelectorAll("[data-count]").forEach((el) => {
    const target = Number(el.dataset.count);
    if (reduceMotion()) return;
    el.textContent = formatVND(0);
    const start = performance.now() + 1900;
    const dur = 900;
    const tick = (now) => {
      if (!el.isConnected) return;
      const t = Math.min(1, Math.max(0, (now - start) / dur));
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = formatVND(Math.round((target * eased) / 1000) * 1000);
      if (t < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

// Hóa đơn nghiêng nhẹ theo con trỏ chuột
function tilt(visual) {
  const card = visual.querySelector(".receipt-tilt");
  if (!card || reduceMotion()) return;
  visual.addEventListener("pointermove", (e) => {
    const r = visual.getBoundingClientRect();
    const x = (e.clientX - r.left) / r.width - 0.5;
    const y = (e.clientY - r.top) / r.height - 0.5;
    card.style.setProperty("--ry", `${(x * 14).toFixed(2)}deg`);
    card.style.setProperty("--rx", `${(-y * 10).toFixed(2)}deg`);
  });
  visual.addEventListener("pointerleave", () => {
    card.style.setProperty("--ry", "0deg");
    card.style.setProperty("--rx", "0deg");
  });
}

/**
 * mountAuth(el, { mode, title, sub, body }) -> phần tử .auth-body chứa form
 * Lần đầu vẽ cả trang; những lần sau (chuyển tab) chỉ thay nội dung form, có hiệu ứng trượt.
 */
export function mountAuth(el, { mode, title, sub, body }) {
  const inner = `<h2>${esc(title)}</h2><p class="sub">${esc(sub)}</p>${body}`;
  let page = el.querySelector(".auth-page");

  if (!page) {
    el.innerHTML = `<div class="auth-page" data-mode="${mode}">
      <section class="auth-visual">
        <span class="blob b1"></span><span class="blob b2"></span><span class="blob b3"></span>
        ${brand()}
        <div>
          <h1>Chụp hóa đơn, mỗi người thấy ngay phần mình trả.</h1>
          <p class="lead-text">Chọn món mình đã ăn, thuế và phí được chia theo tỉ lệ, công nợ trong nhóm tự cập nhật.</p>
        </div>
        ${receipt()}
        <div class="auth-mobile-cta">
          <a class="auth-submit" href="#/register" data-go="register">Đăng ký</a>
          <a class="auth-cta-secondary" href="#/login" data-go="login">Đăng nhập</a>
        </div>
      </section>
      <section class="auth-panel">
        <div class="auth-card">
          <button type="button" class="auth-back" aria-label="Quay lại màn hình giới thiệu">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>
            Quay lại
          </button>
          ${brand()}
          <nav class="auth-tabs" aria-label="Chọn đăng nhập hoặc đăng ký">
            <a href="#/login" data-tab="login">Đăng nhập</a>
            <a href="#/register" data-tab="register">Đăng ký</a>
          </nav>
          <div class="auth-body"></div>
        </div>
      </section>
    </div>`;
    page = el.querySelector(".auth-page");
    countUp(page);
    tilt(page.querySelector(".auth-visual"));
    wireMobileSteps(page);
  }

  const prev = page.dataset.mode;
  page.dataset.mode = mode;
  page.querySelectorAll("[data-tab]").forEach((a) => {
    if (a.dataset.tab === mode) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });

  const bodyEl = page.querySelector(".auth-body");
  bodyEl.innerHTML = inner;
  if (prev && prev !== mode) {
    bodyEl.style.setProperty("--from", mode === "register" ? "24px" : "-24px");
    bodyEl.classList.remove("swap");
    void bodyEl.offsetWidth; // chạy lại animation
    bodyEl.classList.add("swap");
  }
  document.title = `${title} | SmartSplit AI`;
  return bodyEl;
}

// Điện thoại: màn giới thiệu (hóa đơn + 2 nút) -> bấm nút mới hiện form. Máy tính không dùng tới.
function wireMobileSteps(page) {
  page.dataset.step = "welcome";
  page.querySelectorAll("[data-go]").forEach((a) => {
    a.addEventListener("click", () => {
      page.dataset.step = "form";
      window.scrollTo(0, 0);
      // Cùng trang hiện tại thì hash không đổi, router không chạy lại -> tự focus ô đầu tiên
      setTimeout(() => page.querySelector(".auth-body input")?.focus(), 50);
    });
  });
  page.querySelector(".auth-back").addEventListener("click", () => {
    page.dataset.step = "welcome";
    window.scrollTo(0, 0);
  });
}

/** Ô nhập kiểu trang auth. Tương thích showFieldErrors / clearFieldErrors trong ui.js */
export function authField({
  label,
  name,
  type = "text",
  icon = "",
  placeholder = "",
  autocomplete = "",
  hint = "",
  toggle = false,
  meter = false,
  value = "",
}) {
  return `<div class="auth-field">
    <label for="f-${name}">${esc(label)}</label>
    <div class="auth-input${toggle ? " has-toggle" : ""}">
      <input id="f-${name}" name="${name}" type="${type}" required placeholder="${esc(placeholder)}" value="${esc(value)}"
             ${autocomplete ? `autocomplete="${autocomplete}"` : ""} ${type === "email" ? 'inputmode="email" spellcheck="false" autocapitalize="off"' : ""}>
      ${ICONS[icon] ?? ""}
      ${toggle ? `<button type="button" class="pw-toggle" data-toggle="${name}" aria-pressed="false" aria-label="Hiện mật khẩu">Hiện</button>` : ""}
      <div class="invalid-feedback"></div>
    </div>
    ${meter ? '<div class="pw-meter" data-level="0" aria-hidden="true"><i></i><i></i><i></i></div>' : ""}
    <div class="field-hint" data-hint="${name}" aria-live="polite">${esc(hint)}</div>
  </div>`;
}

/** Gắn nút Hiện/Ẩn mật khẩu và cảnh báo Caps Lock cho mọi ô password trong form */
export function wirePasswordFields(form) {
  form.querySelectorAll("[data-toggle]").forEach((btn) => {
    const input = form.elements[btn.dataset.toggle];
    btn.onclick = () => {
      const show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.textContent = show ? "Ẩn" : "Hiện";
      btn.setAttribute("aria-pressed", String(show));
      btn.setAttribute("aria-label", show ? "Ẩn mật khẩu" : "Hiện mật khẩu");
      input.focus();
    };
  });
  form.querySelectorAll("input[type=password]").forEach((input) => {
    const hint = form.querySelector(`[data-hint="${input.name}"]`);
    const original = hint?.textContent ?? "";
    const check = (e) => {
      if (!hint || !e.getModifierState) return;
      const on = e.getModifierState("CapsLock");
      hint.textContent = on
        ? "Caps Lock đang bật"
        : (hint.dataset.base ?? original);
      hint.classList.toggle("warn", on);
    };
    input.addEventListener("keyup", check);
    input.addEventListener("keydown", check);
  });
}

/** Rung nhẹ các ô đang lỗi */
export function shakeInvalid(form) {
  form.querySelectorAll(".is-invalid").forEach((input) => {
    const box = input.closest(".auth-input, .auth-check") ?? input;
    box.classList.remove("shake");
    void box.offsetWidth;
    box.classList.add("shake");
  });
}

/** Nút chuyển sang trạng thái thành công (dấu tích) trước khi chuyển trang */
export function showSuccess(button, text) {
  button.classList.add("is-success");
  button.innerHTML = `${ICONS.check}${esc(text)}`;
  button.disabled = true;
  return new Promise((r) => setTimeout(r, reduceMotion() ? 0 : 650));
}

/** Sau khi đăng nhập: quay lại trang người dùng định vào trước đó (nếu có) */
export function goAfterLogin(navigate) {
  const back = sessionStorage.getItem("after_login");
  sessionStorage.removeItem("after_login");
  navigate(
    back && !back.startsWith("/login") && !back.startsWith("/register")
      ? back
      : "/",
  );
}

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
