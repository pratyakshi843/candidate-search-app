async function request(path, options = {}) {
  let res
  try {
    res = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...options })
  } catch (e) {
    if (e.name === 'AbortError') throw e
    throw new Error('Cannot reach the search service. Is the backend running?')
  }
  const body = await res.json().catch(() => ({}))
  // The Vite dev proxy answers 502/504 with no JSON body when the backend isn't running.
  if ((res.status === 502 || res.status === 504) && !body.detail) {
    throw new Error('Cannot reach the search service. Start the backend on port 8000.')
  }
  if (!res.ok) {
    const detail = Array.isArray(body.detail)
      ? body.detail.map((d) => d.msg.replace(/^Value error, /, '')).join(' ')
      : body.detail
    throw new Error(detail || `Request failed (${res.status})`)
  }
  return body
}

export const getHealth = () => request('/api/health')

// criteria = { query, filters, dismissed }: the typed query, the Filters-panel values and removed chip keys
export const searchCandidates = (criteria, page, sort, pageSize = 12) =>
  request('/api/search', { method: 'POST', body: JSON.stringify({ ...criteria, page, sort, page_size: pageSize }) })

export const resolveFilters = (criteria, signal) =>
  request('/api/resolve', { method: 'POST', body: JSON.stringify(criteria), signal })

export const suggest = (field, q, limit = 10, signal) =>
  request(`/api/suggest?${new URLSearchParams({ field, q, limit })}`, { signal })

export const getCandidate = (id) => request(`/api/candidate/${encodeURIComponent(id)}`)
