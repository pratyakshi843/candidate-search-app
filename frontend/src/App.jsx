import { useCallback, useEffect, useRef, useState } from 'react'
import { getHealth, resolveFilters, searchCandidates } from './api'
import CandidateCard from './components/CandidateCard'
import FilterPanel from './components/FilterPanel'
import ProfilePanel from './components/ProfilePanel'
import SearchBar from './components/SearchBar'

const EXAMPLES = [
  'Find Software Engineers',
  'Find Senior Backend Developers with 5+ years of experience',
  'Find React Developers in India',
  'Find MERN Stack Developers',
  'Find Python Developers who have worked in fintech companies',
  'Find current employees at Google',
]

const SORTS = [
  ['relevance', 'Most relevant'],
  ['experience_desc', 'Most experience'],
  ['experience_asc', 'Least experience'],
  ['recent', 'Recently updated'],
]

// Values chosen in the Filters panel (same shape as the backend's Filters model).
const NO_FILTERS = {
  role: null, skills: [], skills_mode: 'any', experience: null, country: null, city: null,
  company: null, company_status: 'any', industry: null,
}
const NOTHING_RESOLVED = { filters: null, auto: null, chips: [], notes: [] }
const EMPTY_SEARCH = "Type what you're looking for or choose at least one filter."

const hasManual = (m) => Boolean(m.role || m.skills.length || m.experience || m.country || m.city || m.company || m.industry)
const lower = (s) => (s || '').toLowerCase()

export default function App() {
  const [query, setQuery] = useState('')
  const [manual, setManual] = useState(NO_FILTERS)     // chosen in the Filters panel
  const [dismissed, setDismissed] = useState([])       // keys of query-derived chips the recruiter removed
  const [resolved, setResolved] = useState(NOTHING_RESOLVED)
  const [panelOpen, setPanelOpen] = useState(false)
  const [panelVersion, setPanelVersion] = useState(0)  // bumps when filters change from outside the panel
  const [submitted, setSubmitted] = useState(null)
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState('relevance')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [health, setHealth] = useState(null)
  const lastQuery = useRef('')

  useEffect(() => {
    let timer
    const poll = () => getHealth().then((h) => {
      setHealth(h)
      if (h.status !== 'ready') timer = setTimeout(poll, 3000)
    }).catch(() => { setHealth({ status: 'offline' }); timer = setTimeout(poll, 5000) })
    poll()
    return () => clearTimeout(timer)
  }, [])

  // Keep the chips in sync with what a search would apply: parse while typing (debounced),
  // update straight away for panel changes and chip removals.
  useEffect(() => {
    const typing = query !== lastQuery.current
    lastQuery.current = query
    const ctrl = new AbortController()
    const t = setTimeout(() => {
      if (!query.trim() && !hasManual(manual)) { setResolved(NOTHING_RESOLVED); return }
      resolveFilters({ query, filters: manual, dismissed }, ctrl.signal)
        .then(setResolved)
        .catch(() => {})
    }, typing ? 300 : 0)
    return () => { clearTimeout(t); ctrl.abort() }
  }, [query, manual, dismissed])

  const run = useCallback(async (criteria, p, s) => {
    setLoading(true)
    setError(null)
    try {
      const res = await searchCandidates(criteria, p, s)
      setData(res)
      window.scrollTo({ top: 0, behavior: 'smooth' })
    } catch (e) {
      setError(e.message)
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const startSearch = (criteria) => {
    if (!criteria.query && !hasManual(criteria.filters)) {
      setError(EMPTY_SEARCH)
      return
    }
    setSubmitted(criteria)
    setPage(1)
    setPanelOpen(false)
    run(criteria, 1, sort)
  }

  const submit = (e) => {
    e?.preventDefault()
    startSearch({ query: query.trim(), filters: manual, dismissed })
  }

  const changeQuery = (q) => {
    setQuery(q)
    if (!q.trim()) setDismissed([])
  }

  const runExample = (ex) => {
    setQuery(ex)
    setDismissed([])
    startSearch({ query: ex, filters: manual, dismissed: [] })
  }

  // --- chip and panel edits. A removed query-derived chip is remembered in `dismissed`
  // so it stays removed while the query text is unchanged.
  const dismiss = (key) => setDismissed((d) => (d.includes(key) ? d : [...d, key]))
  const autoChip = (key) => resolved.chips.find((c) => c.key === key && c.auto)

  const removeChip = (chip) => {
    setManual((m) => {
      if (chip.key.startsWith('skill:')) {
        const drop = new Set(chip.manual.map(lower))
        return { ...m, skills: m.skills.filter((s) => !drop.has(lower(s))) }
      }
      if (chip.key === 'company') return { ...m, company: null, company_status: 'any' }
      return chip.manual.length ? { ...m, [chip.key]: null } : m
    })
    if (chip.auto) dismiss(chip.key)
    setPanelVersion((v) => v + 1)
  }

  const clearAll = () => {
    setQuery('')
    setManual(NO_FILTERS)
    setDismissed([])
    setResolved(NOTHING_RESOLVED)
    setPanelVersion((v) => v + 1)
    setError(null)
  }

  const actions = {
    setSingle: (key, value) => {
      setManual((m) => ({ ...m, [key]: value || null }))
      if (!value && autoChip(key)) dismiss(key)
    },
    setExperience: (exp) => {
      setManual((m) => ({ ...m, experience: exp }))
      if (!exp && autoChip('experience')) dismiss('experience')
    },
    setCompany: (company, status) => {
      setManual((m) => ({ ...m, company: company || null, company_status: status || 'any' }))
      if (!company && autoChip('company')) dismiss('company')
    },
    addSkill: (s) => {
      setManual((m) => (m.skills.some((x) => lower(x) === lower(s)) ? m : { ...m, skills: [...m.skills, s] }))
      setDismissed((d) => d.filter((k) => k !== `skill:${lower(s)}`))
    },
    setSkillsMode: (mode) => setManual((m) => ({ ...m, skills_mode: mode })),
  }

  // What the panel shows: its own values, else the (not removed) values the query produced.
  // Derived locally so it is correct immediately, before the next /api/resolve answer arrives.
  const auto = resolved.auto || {}
  const fromQuery = (k) => (dismissed.includes(k) ? null : auto[k] || null)
  const panelSkills = [...manual.skills]
  for (const s of auto.skills || []) {
    if (!dismissed.includes(`skill:${lower(s)}`) && !panelSkills.some((x) => lower(x) === lower(s))) panelSkills.push(s)
  }
  const panelValue = {
    ...Object.fromEntries(['role', 'experience', 'country', 'city', 'industry'].map((k) => [k, manual[k] || fromQuery(k)])),
    skills: panelSkills,
    skills_mode: manual.skills_mode,
    company: manual.company || fromQuery('company'),
    company_status: manual.company ? manual.company_status : (fromQuery('company') ? auto.company_status : 'any'),
  }

  const changeSort = (s) => {
    setSort(s)
    setPage(1)
    if (submitted) run(submitted, 1, s)
  }

  const goTo = (p) => {
    setPage(p)
    run(submitted, p, sort)
  }

  return (
    <div className="min-h-screen">
      <header className="bg-white border-b border-slate-200">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between gap-4">
          <h1 className="text-xl font-semibold text-slate-900">Candidate Search</h1>
          <DataBadge health={health} />
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        <SearchBar
          query={query}
          onQueryChange={changeQuery}
          chips={resolved.chips}
          notes={resolved.notes}
          loading={loading}
          panelOpen={panelOpen}
          onTogglePanel={() => setPanelOpen((o) => !o)}
          onRemoveChip={removeChip}
          onClearAll={clearAll}
          onSubmit={submit}
          examples={EXAMPLES}
          onExample={runExample}
        >
          {panelOpen && (
            <FilterPanel value={panelValue} auto={resolved.auto} version={panelVersion} actions={actions}
                         onClose={() => setPanelOpen(false)} />
          )}
        </SearchBar>

        {error && (
          <div role="alert" className="mt-6 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        {data && !loading && (
          <>
            {data.chips.length > 0 && (
              <div className="mt-6 flex flex-wrap items-center gap-2 text-xs">
                <span className="text-slate-500">Results for:</span>
                {data.chips.map((c) => (
                  <span key={c.key} className="rounded-full bg-slate-100 text-slate-700 px-3 py-1">
                    <span className="text-slate-500">{c.label}:</span> {c.value}
                  </span>
                ))}
              </div>
            )}

            <div className="mt-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <p className="text-sm text-slate-600">
                <span className="text-lg font-semibold text-slate-900">{data.total.toLocaleString()}</span>{' '}
                matching candidate{data.total === 1 ? '' : 's'}
              </p>
              {data.total > 0 && (
                <label className="text-sm text-slate-600 flex items-center gap-2">
                  Sort by
                  <select value={sort} onChange={(e) => changeSort(e.target.value)}
                          className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
                    {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </label>
              )}
            </div>
          </>
        )}

        {loading && (
          <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-busy="true">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="h-48 rounded-xl border border-slate-200 bg-white p-5 animate-pulse">
                <div className="flex gap-3"><div className="h-11 w-11 rounded-full bg-slate-100" /><div className="flex-1 space-y-2"><div className="h-4 bg-slate-100 rounded w-2/3" /><div className="h-3 bg-slate-100 rounded" /></div></div>
                <div className="mt-6 h-3 bg-slate-100 rounded w-1/2" />
                <div className="mt-4 flex gap-2">{[...Array(4)].map((_, j) => <div key={j} className="h-5 w-14 bg-slate-100 rounded" />)}</div>
              </div>
            ))}
          </div>
        )}

        {data && !loading && data.total === 0 && (
          <div className="mt-8 rounded-2xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
            <p className="text-base font-medium text-slate-800">No matching candidates</p>
            <p className="mt-1 text-sm text-slate-500">
              {data.message || 'Try a broader role, fewer skills, or remove the location or experience requirement.'}
            </p>
          </div>
        )}

        {data && !loading && data.results.length > 0 && (
          <>
            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {data.results.map((c) => <CandidateCard key={c.id} c={c} onOpen={setOpenId} />)}
            </div>
            <Pagination page={page} totalPages={data.total_pages} onChange={goTo} />
          </>
        )}

        {!data && !loading && !error && (
          <p className="mt-12 text-center text-sm text-slate-400">
            Type a requirement in plain English, or open Filters, then press Search.
          </p>
        )}
      </main>

      {openId && <ProfilePanel key={openId} id={openId} onClose={() => setOpenId(null)} />}
    </div>
  )
}

function DataBadge({ health }) {
  if (!health) return null
  if (health.status === 'offline') return <span className="text-xs text-rose-600">Backend offline</span>
  if (health.status === 'error') return <span className="text-xs text-rose-600" title={health.warning}>Candidate data unavailable</span>
  if (health.status !== 'ready' && health.status !== 'refreshing') {
    return <span className="text-xs text-amber-600">Loading candidate data…</span>
  }
  const src = health.mode === 'real' ? 'Azure dataset' : 'Fictional demo data'
  return (
    <span className={`text-xs whitespace-nowrap ${health.warning ? 'text-amber-600' : 'text-slate-500'}`} title={health.warning || undefined}>
      {health.records?.toLocaleString()} profiles · {src}
      {health.status === 'refreshing' && ' · refreshing…'}
      {health.warning && ' · using cached copy'}
    </span>
  )
}

function Pagination({ page, totalPages, onChange }) {
  if (totalPages <= 1) return null
  const pages = []
  const start = Math.max(1, Math.min(page - 2, totalPages - 4))
  for (let p = start; p <= Math.min(totalPages, start + 4); p++) pages.push(p)
  const btn = 'min-w-9 h-9 px-3 rounded-lg text-sm border focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500'
  return (
    <nav className="mt-8 flex flex-wrap items-center justify-center gap-1.5" aria-label="Pagination">
      <button className={`${btn} border-slate-300 bg-white disabled:opacity-40`} disabled={page <= 1} onClick={() => onChange(page - 1)}>Previous</button>
      {pages.map((p) => (
        <button key={p} onClick={() => onChange(p)} aria-current={p === page ? 'page' : undefined}
                className={`${btn} ${p === page ? 'bg-indigo-600 border-indigo-600 text-white' : 'bg-white border-slate-300 text-slate-700 hover:border-indigo-300'}`}>
          {p}
        </button>
      ))}
      <button className={`${btn} border-slate-300 bg-white disabled:opacity-40`} disabled={page >= totalPages} onClick={() => onChange(page + 1)}>Next</button>
      <span className="w-full text-center text-xs text-slate-400 mt-1">Page {page} of {totalPages}</span>
    </nav>
  )
}
