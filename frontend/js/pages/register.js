import { post } from '../api.js'
import { setSession } from '../auth.js'
import { navigate } from '../router.js'
import { clearFieldErrors, field, formValues, showFieldErrors, toast } from '../ui.js'

export function render(el) {
  el.innerHTML = `<h3 class="mb-3">Đăng ký</h3>
    <form id="register-form" novalidate>
      ${field({ label: 'Họ tên', name: 'full_name', required: true })}
      ${field({ label: 'Email', name: 'email', type: 'email', required: true })}
      ${field({ label: 'Mật khẩu (tối thiểu 8 ký tự)', name: 'password', type: 'password', required: true })}
      <button class="btn btn-primary w-100">Tạo tài khoản</button>
    </form>
    <p class="text-center mt-3 mb-0">Đã có tài khoản? <a href="#/login">Đăng nhập</a></p>`

  const form = el.querySelector('#register-form')
  form.onsubmit = async (e) => {
    e.preventDefault()
    clearFieldErrors(form)
    const btn = form.querySelector('button')
    btn.disabled = true
    try {
      const { access_token, user } = await post('/auth/register', formValues(form))
      setSession(access_token, user)
      toast.success('Đăng ký thành công')
      navigate('/')
    } catch (err) {
      showFieldErrors(form, err.details)
      toast.error(err)
    } finally {
      btn.disabled = false
    }
  }
}
