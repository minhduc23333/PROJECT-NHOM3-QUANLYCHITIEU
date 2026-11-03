export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
}

export const loadingHTML = () =>
  `<div class="text-center p-5"><div class="spinner-border" role="status"></div><div class="mt-2 text-muted">Đang tải...</div></div>`

export const emptyHTML = (text = 'Chưa có dữ liệu') => `<div class="text-center text-muted p-5">${esc(text)}</div>`

export const errorHTML = (msg) =>
  `<div class="alert alert-danger d-flex justify-content-between align-items-center">
     <span>${esc(msg)}</span><button class="btn btn-sm btn-outline-danger" data-retry>Thử lại</button>
   </div>`

/**
 * Hiện loading -> gọi loader() -> trống / lỗi / dữ liệu.
 * renderState(el, () => get('/groups'), (el, data) => {...}, { isEmpty: d => d.length === 0, emptyText: 'Chưa có nhóm' })
 */
export async function renderState(container, loader, renderFn, { isEmpty = () => false, emptyText } = {}) {
  container.innerHTML = loadingHTML()
  try {
    const data = await loader()
    if (isEmpty(data)) container.innerHTML = emptyHTML(emptyText)
    else renderFn(container, data)
  } catch (e) {
    container.innerHTML = errorHTML(e.message)
    container.querySelector('[data-retry]').onclick = () => renderState(container, loader, renderFn, { isEmpty, emptyText })
  }
}
function toastBox() {
  let c = document.getElementById('toasts')
  if (!c) {
    c = document.createElement('div')
    c.id = 'toasts'
    c.className = 'toast-container position-fixed top-0 end-0 p-3'
    document.body.appendChild(c)
  }
  return c
}

function showToast(text, kind) {
  const el = document.createElement('div')
  el.className = `toast align-items-center text-bg-${kind} border-0`
  el.innerHTML = `<div class="d-flex"><div class="toast-body">${esc(text)}</div>
    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`
  toastBox().appendChild(el)
  el.addEventListener('hidden.bs.toast', () => el.remove())
  new bootstrap.Toast(el, { delay: 3000 }).show()
}

export const toast = {
  success: (t) => showToast(t, 'success'),
  info: (t) => showToast(t, 'primary'),
  error: (e) => showToast(typeof e === 'string' ? e : e?.message ?? 'Có lỗi xảy ra', 'danger'),
}

export function field({ label, name, type = 'text', required = false, placeholder = '', value = '' }) {
  return `<div class="mb-3">
    <label class="form-label" for="f-${name}">${esc(label)}${required ? ' <span class="text-danger">*</span>' : ''}</label>
    <input class="form-control" id="f-${name}" name="${name}" type="${type}" ${required ? 'required' : ''}
           placeholder="${esc(placeholder)}" value="${esc(value)}">
    <div class="invalid-feedback"></div>
  </div>`
}

export const formValues = (form) => Object.fromEntries(new FormData(form))

export function clearFieldErrors(form) {
  form.querySelectorAll('.is-invalid').forEach((i) => i.classList.remove('is-invalid'))
}

// details từ BE: [{ field: 'email', message: '...' }]
export function showFieldErrors(form, details) {
  for (const d of details ?? []) {
    const input = form.elements[d.field]
    if (input) {
      input.classList.add('is-invalid')
      input.nextElementSibling.textContent = d.message
    }
  }
}

/**
 * dataTable([{ key:'name', title:'Món' }, { key:'amount', title:'Tiền', align:'end', render:(v,row)=>formatVND(v) }], rows)
 * Không có render -> tự esc. Có render -> bạn tự esc() phần dữ liệu người dùng.
 */
export function dataTable(columns, rows, { emptyText = 'Chưa có dữ liệu' } = {}) {
  if (!rows.length) return emptyHTML(emptyText)
  const cls = (c) => (c.align === 'end' ? 'text-end' : '')
  const head = columns.map((c) => `<th class="${cls(c)}">${esc(c.title)}</th>`).join('')
  const body = rows
    .map((r) => `<tr>${columns.map((c) => `<td class="${cls(c)}">${c.render ? c.render(r[c.key], r) : esc(r[c.key])}</td>`).join('')}</tr>`)
    .join('')
  return `<div class="table-responsive"><table class="table table-hover align-middle">
    <thead class="table-light"><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`
}

// if (await confirmDialog({ title: 'Chốt hóa đơn?', message: '...' })) { ... }
export function confirmDialog({ title = 'Xác nhận', message = '', okText = 'Đồng ý', danger = false } = {}) {
  return new Promise((resolve) => {
    const el = document.createElement('div')
    el.className = 'modal fade'
    el.tabIndex = -1
    el.innerHTML = `<div class="modal-dialog modal-dialog-centered"><div class="modal-content">
      <div class="modal-header"><h5 class="modal-title">${esc(title)}</h5>
        <button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
      <div class="modal-body">${esc(message)}</div>
      <div class="modal-footer">
        <button class="btn btn-secondary" data-bs-dismiss="modal">Hủy</button>
        <button class="btn btn-${danger ? 'danger' : 'primary'}" data-ok>${esc(okText)}</button>
      </div></div></div>`
    document.body.appendChild(el)
    const modal = new bootstrap.Modal(el)
    let result = false
    el.querySelector('[data-ok]').onclick = () => { result = true; modal.hide() }
    el.addEventListener('hidden.bs.modal', () => { el.remove(); resolve(result) })
    modal.show()
  })
}