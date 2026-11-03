import { getUser, isLoggedIn, logout } from './auth.js'
import { addRoute, currentPath, match, navigate } from './router.js'
import * as login from './pages/login.js'
import * as dashboard from './pages/dashboard.js'
import * as groups from './pages/groups.js'
import * as receipts from './pages/receipts.js'
import * as debts from './pages/debts.js'

addRoute('/login', login.render, { isPublic: true })
addRoute('/', dashboard.render)
addRoute('/groups', groups.render)
addRoute('/receipts', receipts.render)
addRoute('/debts', debts.render)

async function route() {
  const found = match(currentPath())
  if (!found) return navigate('/')
  if (!found.isPublic && !isLoggedIn()) return navigate('/login')   // route guard
  if (found.isPublic && isLoggedIn()) return navigate('/')

  document.body.classList.toggle('public', found.isPublic)
  document.getElementById('user-name').textContent = getUser()?.full_name ?? ''
  document.querySelectorAll('#menu a, #mobile-menu a').forEach((a) => {
      const r = a.dataset.route
      a.classList.toggle('active', r === '/' ? currentPath() === '/' : currentPath().startsWith(r))
  })
    const view = document.getElementById('view')
  view.innerHTML = ''
  await found.render(view, found.params)
}

document.getElementById('btn-logout').onclick = logout
window.addEventListener('hashchange', route)
route()