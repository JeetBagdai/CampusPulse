// Same-origin in production; Vite proxies /api and /ws to the backend in dev.
async function req(method, path, body, isForm = false) {
  const opts = { method, headers: {} }
  if (body !== undefined) {
    if (isForm) opts.body = body
    else {
      opts.body = JSON.stringify(body)
      opts.headers['Content-Type'] = 'application/json'
    }
  }
  const r = await fetch(path, opts)
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail || detail } catch { /* not JSON */ }
    throw new Error(detail)
  }
  return r.json()
}

export const api = {
  get: (p) => req('GET', p),
  post: (p, b) => req('POST', p, b),
  form: (p, fd) => req('POST', p, fd, true),
}

export function wsUrl(path) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${location.host}${path}`
}

export const inr = (n) => '₹' + Math.round(n ?? 0).toLocaleString('en-IN')
export const num = (n, d = 0) => (n ?? 0).toLocaleString('en-IN', { maximumFractionDigits: d })
export const hhmm = (iso) => (iso ? iso.slice(11, 16) : '')
