const KEY = 'smartsplit_token'
let currentUser = null

export const getToken = () => localStorage.getItem(KEY)
export const isLoggedIn = () => !!getToken()
export const getUser = () => currentUser
export const setUser = (u) => { currentUser = u }

export function setSession(token, user) {
  localStorage.setItem(KEY, token)
  currentUser = user
}

export function logout() {
  localStorage.removeItem(KEY)
  currentUser = null
  location.hash = '#/login'
}

// Tải lại thông tin user từ token đang lưu (gọi khi mở / F5 trang).
// 401 đã được api.js xử lý (tự logout); lỗi khác (mất mạng...) thì bỏ qua, không đá user ra.
export async function loadUser() {
  if (!isLoggedIn() || currentUser) return currentUser
  const { get } = await import('./api.js')
  try { currentUser = await get('/auth/me') } catch { /* giữ nguyên */ }
  return currentUser
}
