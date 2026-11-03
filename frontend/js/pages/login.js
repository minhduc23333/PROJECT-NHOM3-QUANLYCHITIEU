import { field } from '../ui.js'

export function render(el) {
  el.innerHTML = `<h3 class="mb-3">Đăng nhập</h3>
    <form id="login-form" novalidate>
      ${field({ label: 'Email', name: 'email', type: 'email', required: true })}
      ${field({ label: 'Mật khẩu', name: 'password', type: 'password', required: true })}
      <button class="btn btn-primary w-100">Đăng nhập</button>
    </form>`
}