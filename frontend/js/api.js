import { getToken, logout } from './auth.js'

export class ApiError extends Error {
  constructor(status, message, details = null) {
    super(message)
    this.status = status
    this.details = details
  }
}

export async function api(path, { method = 'GET', body, formData } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  let payload
  if (formData) {
    payload = formData            // upload file: không tự đặt Content-Type
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  let res
  try {
    res = await fetch(path, { method, headers, body: payload })
  } catch {
    throw new ApiError(0, 'Không kết nối được máy chủ')
  }

  if (res.status === 401 && !path.startsWith('/auth/login')) {
    logout()
    throw new ApiError(401, 'Phiên đăng nhập đã hết hạn')
  }
  const data = res.status === 204 ? null : await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data?.error?.message ?? 'Có lỗi xảy ra', data?.error?.details)
  return data
}

export const get = (p) => api(p)
export const post = (p, body) => api(p, { method: 'POST', body })
export const put = (p, body) => api(p, { method: 'PUT', body })
export const del = (p) => api(p, { method: 'DELETE' })