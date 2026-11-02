export default function SearchBar({
  query, onQueryChange, chips, notes, loading, panelOpen, onTogglePanel, onRemoveChip, onClearAll, onSubmit,
  examples, onExample, children,
}) {
  const count = chips.length
  return (
    <form onSubmit={onSubmit} className="bg-white rounded-2xl border border-slate-200 shadow-sm p-3 sm:p-4">
      <div className="flex flex-col sm:flex-row gap-2">
        <div className="flex flex-1 min-w-0 items-center rounded-xl border border-slate-300 bg-white focus-within:ring-2 focus-within:ring-indigo-500 focus-within:border-indigo-500">
          <svg className="ml-3 h-5 w-5 shrink-0 text-slate-400" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
            <path fillRule="evenodd" d="M9 3.5a5.5 5.5 0 1 0 0 11 5.5 5.5 0 0 0 0-11ZM2 9a7 7 0 1 1 12.45 4.39l3.08 3.08a.75.75 0 1 1-1.06 1.06l-3.08-3.08A7 7 0 0 1 2 9Z" clipRule="evenodd" />
          </svg>
          <label htmlFor="q" className="sr-only">Search query</label>
          <input
            id="q"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            maxLength={500}
            autoFocus
            placeholder="Describe the candidate, e.g. Python developers in India with 5+ years"
            className="min-w-0 flex-1 bg-transparent px-3 py-3 text-base placeholder:text-slate-400 focus:outline-none"
          />
          <button
            type="button"
            onClick={onTogglePanel}
            aria-expanded={panelOpen}
            aria-controls="filter-panel"
            className={`m-1.5 inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${panelOpen ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600 hover:bg-slate-100'}`}
          >
            <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M3 4.75A.75.75 0 0 1 3.75 4h12.5a.75.75 0 0 1 .53 1.28L12 10.06v4.19a.75.75 0 0 1-.33.62l-2.5 1.67A.75.75 0 0 1 8 15.92v-5.86L3.22 5.28A.75.75 0 0 1 3 4.75Z" />
            </svg>
            Filters
            {count > 0 && (
              <span className="min-w-5 rounded-full bg-indigo-600 px-1.5 text-xs leading-5 text-white" aria-label={`${count} active`}>{count}</span>
            )}
          </button>
        </div>
        <button
          type="submit"
          disabled={loading}
          className="rounded-xl bg-indigo-600 px-7 py-3 text-base font-medium text-white hover:bg-indigo-700 disabled:opacity-60 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 focus-visible:ring-offset-2"
        >
          {loading ? 'Searching…' : 'Search'}
        </button>
      </div>

      {(count > 0 || query) && (
        <div className="mt-3 flex flex-wrap items-center gap-1.5" aria-label="Applied filters">
          {chips.map((c) => (
            <span key={c.key} className="inline-flex max-w-full items-center gap-1 rounded-full bg-indigo-50 py-1 pl-3 pr-1 text-xs text-indigo-800">
              <span className="truncate"><span className="text-indigo-500">{c.label}:</span> {c.value}</span>
              <button type="button" onClick={() => onRemoveChip(c)} aria-label={`Remove ${c.label}: ${c.value}`}
                      className="grid h-5 w-5 shrink-0 place-items-center rounded-full text-indigo-400 hover:bg-indigo-100 hover:text-indigo-700">
                ×
              </button>
            </span>
          ))}
          <button type="button" onClick={onClearAll} className="ml-1 text-xs text-slate-500 underline-offset-2 hover:text-slate-800 hover:underline">
            Clear all
          </button>
        </div>
      )}
      {notes.length > 0 && <p className="mt-2 text-xs text-amber-700">{notes.join(' · ')}</p>}

      {children}

      {!panelOpen && count === 0 && !query && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <span className="text-slate-400">Try:</span>
          {examples.map((ex) => (
            <button key={ex} type="button" onClick={() => onExample(ex)}
                    className="rounded-full border border-slate-200 px-3 py-1 text-slate-600 hover:border-indigo-300 hover:text-indigo-700">
              {ex}
            </button>
          ))}
        </div>
      )}
    </form>
  )
}
