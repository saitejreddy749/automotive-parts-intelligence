export async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, options)
  let body
  try { body = await response.json() } catch { body = {} }
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`
    throw new Error(detail)
  }
  return body
}

export function post(path, data) {
  return request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}
