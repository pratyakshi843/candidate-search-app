import { useEffect, useState } from 'react'
import { getCandidate } from '../api'
import { formatYears } from '../format'
import Initials from './Initials'

// Rendered with key={id}, so each candidate gets fresh loading state.
export default function ProfilePanel({ id, onClose }) {
  const [state, setState] = useState({ loading: true, data: null, error: null })

  useEffect(() => {
    let active = true
    getCandidate(id)
      .then((data) => active && setState({ loading: false, data, error: null }))
      .catch((e) => active && setState({ loading: false, data: null, error: e.message }))
    return () => { active = false }
  }, [id])

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const p = state.data
  return (
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label="Candidate profile">
      <div className="absolute inset-0 bg-slate-900/40" onClick={onClose} />
      <aside className="absolute right-0 top-0 h-full w-full sm:max-w-xl bg-white shadow-xl flex flex-col">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200">
          <h2 className="font-semibold text-slate-900">Candidate profile</h2>
          <button onClick={onClose} className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100" aria-label="Close">
            <svg className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path d="M6.28 5.22a.75.75 0 0 0-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 1 0 1.06 1.06L10 11.06l3.72 3.72a.75.75 0 1 0 1.06-1.06L11.06 10l3.72-3.72a.75.75 0 0 0-1.06-1.06L10 8.94 6.28 5.22Z" /></svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {state.loading && <div className="space-y-3 animate-pulse">{[...Array(6)].map((_, i) => <div key={i} className="h-4 bg-slate-100 rounded" />)}</div>}
          {state.error && <p className="text-sm text-rose-700 bg-rose-50 rounded-lg p-3">{state.error}</p>}
          {p && (
            <div className="space-y-6">
              <div className="flex items-start gap-4">
                <Initials name={p.name} id={p.id} size="h-14 w-14 text-lg" />
                <div className="min-w-0">
                  <h3 className="text-lg font-semibold text-slate-900">{p.name || `Candidate ${p.id}`}</h3>
                  <p className="text-sm text-slate-700">{[p.current_title, p.current_company].filter(Boolean).join(' · ')}</p>
                  {p.headline && p.headline !== p.current_title && <p className="text-sm text-slate-500 mt-1">{p.headline}</p>}
                  <div className="flex flex-wrap gap-x-4 text-xs text-slate-500 mt-2">
                    {p.location && <span>{p.location}</span>}
                    <span>{formatYears(p.years_experience) ? `${formatYears(p.years_experience)} experience` : 'Experience not available'}</span>
                    {p.industry && <span>{p.industry}</span>}
                  </div>
                  {p.profile_url && <a href={p.profile_url} target="_blank" rel="noreferrer" className="text-xs text-indigo-600 hover:underline mt-1 inline-block">View public profile</a>}
                </div>
              </div>

              {p.summary && <Section title="Summary"><p className="text-sm text-slate-600 whitespace-pre-line">{p.summary}</p></Section>}

              {p.skills.length > 0 && (
                <Section title={`Skills (${p.skills.length})`}>
                  <div className="flex flex-wrap gap-1.5">
                    {p.skills.map((s) => <span key={s} className="px-2 py-0.5 rounded-md text-xs bg-slate-100 text-slate-600">{s}</span>)}
                  </div>
                </Section>
              )}

              {p.experience.length > 0 && (
                <Section title="Experience">
                  <ol className="space-y-4 border-l border-slate-200 pl-4">
                    {p.experience.map((e, i) => (
                      <li key={i} className="relative">
                        <span className={`absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full ${e.is_current ? 'bg-indigo-500' : 'bg-slate-300'}`} />
                        <p className="text-sm font-medium text-slate-800">{e.title || 'Role not listed'}</p>
                        <p className="text-sm text-slate-600">{e.company}</p>
                        <p className="text-xs text-slate-400">{[e.from, e.to].filter(Boolean).join(' – ')}{e.location ? ` · ${e.location}` : ''}</p>
                        {e.description && <p className="text-xs text-slate-500 mt-1 line-clamp-4">{e.description}</p>}
                      </li>
                    ))}
                  </ol>
                </Section>
              )}

              {p.education.length > 0 && (
                <Section title="Education">
                  <ul className="space-y-2">
                    {p.education.map((ed, i) => (
                      <li key={i} className="text-sm">
                        <p className="font-medium text-slate-800">{ed.institution || 'Institution not listed'}</p>
                        {ed.program && <p className="text-slate-600">{ed.program}</p>}
                        {(ed.from || ed.to) && <p className="text-xs text-slate-400">{[ed.from, ed.to].filter(Boolean).join(' – ')}</p>}
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
            </div>
          )}
        </div>
      </aside>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <section>
      <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">{title}</h4>
      {children}
    </section>
  )
}
