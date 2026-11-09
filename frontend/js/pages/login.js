import { post } from '../api.js'
import { setSession } from '../auth.js'
import { navigate } from '../router.js'
import { clearFieldErrors, field, formValues, showFieldErrors, toast } from '../ui.js'

export function render(el) {
  el.innerHTML = `<h3 class="mb-3">Đăng nhập</h3>
    <form id="login-form" novalidate>
      ${field({ label: 'Email', name: 'email', type: 'email', required: true })}
      ${field({ label: 'Mật khẩu', name: 'password', type: 'password', required: true })}
      <button class="btn btn-primary w-100">Đăng nhập</button>
    </form>
    <p class="text-center mt-3 mb-0">Chưa có tài khoản? <a href="#/register">Đăng ký</a></p>`

  const form = el.querySelector('#login-form')
  form.onsubmit = async (e) => {
    e.preventDefault()
    clearFieldErrors(form)
    const btn = form.querySelector('button')
    btn.disabled = true
    try {
      const { access_token, user } = await post('/auth/login', formValues(form))
      setSession(access_token, user)
      navigate('/')
    } catch (err) {
      showFieldErrors(form, err.details)
      toast.error(err)
    } finally {
      btn.disabled = false
    }
  }
}
