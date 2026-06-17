const cache = new Map<string, { data: any; expiry: number }>()
const DEFAULT_TTL = 30_000

export async function fetchAPI(path: string, ttl = DEFAULT_TTL) {
  const key = `GET:${path}`
  const cached = cache.get(key)
  if (cached && cached.expiry > Date.now()) return cached.data
  const res = await fetch(`/api/v1${path}`)
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  const data = await res.json()
  cache.set(key, { data, expiry: Date.now() + ttl })
  return data
}

export function clearCache() { cache.clear() }

export async function postAPI(path: string, body: any) {
  const res = await fetch(`/api/v1${path}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function putAPI(path: string, body: any) {
  const res = await fetch(`/api/v1${path}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function deleteAPI(path: string) {
  const res = await fetch(`/api/v1${path}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export function fmt(n: number | null | undefined): string {
  if (n == null) return 'N/A'
  return n.toLocaleString('vi-VN')
}

export function fmtPct(n: number | null | undefined): string {
  if (n == null) return 'N/A'
  return n >= 0 ? `+${n.toFixed(2)}%` : `${n.toFixed(2)}%`
}
