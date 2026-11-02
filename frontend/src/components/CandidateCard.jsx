import { formatYears } from '../format'
import Initials from './Initials'

export default function CandidateCard({ c, onOpen }) {
  const matched = new Set(c.matched_skills)
  const years = formatYears(c.years_experience)
  return (
    <button
      type="button"
      onClick={() => onOpen(c.id)}
      className="group text-left w-full bg-white rounded-xl border border-slate-200 p-5 shadow-sm hover:shadow-md hover:border-indigo-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition flex flex-col gap-3"
    >
      <div className="flex items-start gap-3">
        <Initials name={c.name} id={c.id} />
        <div className="min-w-0 flex-1">
          <h3 className="font-semibold text-slate-900 truncate group-hover:text-indigo-700">
            {c.name || `Candidate ${c.id}`}
          </h3>
          <p className="text-sm text-slate-700 line-clamp-2">
            {c.current_title || c.headline || 'Title not listed'}
            {c.current_company && <span className="text-slate-500"> · {c.current_company}</span>}
          </p>
        </div>
      </div>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
        {c.location && <span className="inline-flex items-center gap-1"><Pin />{c.location}</span>}
        <span className="inline-flex items-center gap-1"><Clock />{years ? `${years} experience` : 'Experience not available'}</span>
      </div>

      {c.company_match && (
        <p className="text-xs text-slate-600">
          <span className={`mr-1.5 rounded px-1.5 py-0.5 font-medium ${c.company_match.status === 'current' ? 'bg-indigo-50 text-indigo-700' : 'bg-slate-100 text-slate-600'}`}>
            {c.company_match.status === 'current' ? 'Current' : 'Former'}
          </span>
          {[c.company_match.title, c.company_match.company].filter(Boolean).join(' at ')}
          {c.company_match.from && <span className="text-slate-400"> · {c.company_match.from} – {c.company_match.to || 'end date not listed'}</span>}
        </p>
      )}

      {c.skills.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {c.skills.slice(0, 8).map((s) => (
            <span key={s}
                  className={`px-2 py-0.5 rounded-md text-xs ${matched.has(s) ? 'bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200' : 'bg-slate-100 text-slate-600'}`}>
              {s}
            </span>
          ))}
          {c.skills_total > 8 && <span className="px-2 py-0.5 text-xs text-slate-400">+{c.skills_total - 8} more</span>}
        </div>
      )}

      {c.previous.length > 0 && (
        <p className="text-xs text-slate-500 border-t border-slate-100 pt-3 line-clamp-2">
          <span className="font-medium text-slate-600">Previously: </span>
          {c.previous.map((p) => [p.title, p.company].filter(Boolean).join(' at ')).join(' · ')}
        </p>
      )}
    </button>
  )
}

const Pin = () => (
  <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
    <path fillRule="evenodd" d="M10 18s6-5.33 6-10A6 6 0 0 0 4 8c0 4.67 6 10 6 10Zm0-8a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z" clipRule="evenodd" />
  </svg>
)
const Clock = () => (
  <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
    <path fillRule="evenodd" d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm.75-12.5a.75.75 0 0 0-1.5 0V10c0 .2.08.39.22.53l2.5 2.5a.75.75 0 1 0 1.06-1.06L10.75 9.69V5.5Z" clipRule="evenodd" />
  </svg>
)
