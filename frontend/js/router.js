const routes = []   // { pattern, render, isPublic }

export function addRoute(pattern, render, { isPublic = false } = {}) {
  routes.push({ pattern, render, isPublic })
}

// '/receipts/:id' khớp '/receipts/12' -> params = { id: '12' }
export function match(path) {
  const parts = path.split('/')
  for (const r of routes) {
    const p = r.pattern.split('/')
    if (p.length !== parts.length) continue
    const params = {}
    const ok = p.every((seg, i) =>
      seg.startsWith(':') ? ((params[seg.slice(1)] = decodeURIComponent(parts[i])), true) : seg === parts[i])
    if (ok) return { ...r, params }
  }
  return null
}

export const currentPath = () => location.hash.slice(1) || '/'
export const navigate = (path) => { location.hash = '#' + path }