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