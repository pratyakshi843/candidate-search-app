import { useEffect, useId, useState } from 'react'
import { suggest } from '../api'

const AUTO = -2  // no option chosen with the keyboard yet

// Searchable dropdown backed by /api/suggest. Typing a value that is not in the list is allowed
// (press Enter or leave the field). With `multi`, each pick is passed to onSelect and the input clears.
export default function Combobox({ field, label, value = '', onSelect, placeholder, multi = false, exclude = [] }) {
  const [text, setText] = useState(multi ? '' : value || '')
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [active, setActive] = useState(AUTO)
  const id = useId()

  useEffect(() => {
    if (!open) return
    const ctrl = new AbortController()
    const t = setTimeout(() => {
      suggest(field, text.trim(), 8, ctrl.signal)
        .then((r) => { setItems(r.values); setActive(AUTO) })
        .catch(() => {})
    }, 150)
    return () => { clearTimeout(t); ctrl.abort() }
  }, [field, text, open])

  const excluded = new Set(exclude.map((x) => x.toLowerCase()))
  const shown = items.filter((v) => !excluded.has(v.toLowerCase()))
  const custom = text.trim() && !shown.some((v) => v.toLowerCase() === text.trim().toLowerCase()) ? text.trim() : null
  const options = custom ? [...shown, custom] : shown  // last option: use the typed text as-is
  const listOpen = open && options.length > 0
  // Until the arrow keys are used, highlight the best match so Enter picks it ("pyth" -> "Python"):
  // an exact match first, else a suggestion starting with the typed text. Nothing if it is already chosen.
  const typed = text.trim().toLowerCase()
  const exact = shown.findIndex((v) => v.toLowerCase() === typed)
  const best = !typed || excluded.has(typed) ? -1 : exact >= 0 ? exact : shown[0]?.toLowerCase().startsWith(typed) ? 0 : -1
  const current = active === AUTO ? best : active

  const commit = (v) => {
    const clean = (v ?? '').trim()
    setOpen(false)
    if (multi) {
      setText('')
      if (clean && !excluded.has(clean.toLowerCase())) onSelect(clean)
    } else {
      setText(clean)
      if (clean !== (value || '')) onSelect(clean || null)
    }
  }

  const onKeyDown = (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); setOpen(true); setActive(Math.min(current + 1, options.length - 1)) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(Math.max(current - 1, -1)) }
    else if (e.key === 'Enter') { e.preventDefault(); commit(current >= 0 && open ? options[current] : text) }
    else if (e.key === 'Escape') { setOpen(false) }
  }

  return (
    <div className="relative">
      <label htmlFor={id} className="sr-only">{label}</label>
      <div className="flex items-center rounded-lg border border-slate-300 bg-white focus-within:ring-2 focus-within:ring-indigo-500 focus-within:border-indigo-500">
        <input
          id={id}
          role="combobox"
          aria-expanded={listOpen}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          aria-activedescendant={listOpen && current >= 0 ? `${id}-${current}` : undefined}
          value={text}
          maxLength={100}
          placeholder={placeholder}
          onChange={(e) => { setText(e.target.value); setOpen(true); setActive(AUTO) }}
          onFocus={() => setOpen(true)}
          onBlur={() => commit(multi ? '' : text)}
          onKeyDown={onKeyDown}
          className="w-full min-w-0 rounded-lg bg-transparent px-3 py-2 text-sm placeholder:text-slate-400 focus:outline-none"
        />
        {!multi && text && (
          <button type="button" aria-label={`Clear ${label}`} onMouseDown={(e) => e.preventDefault()}
                  onClick={() => commit('')} className="px-2 text-slate-400 hover:text-slate-600">×</button>
        )}
      </div>
      {listOpen && (
        <ul id={`${id}-list`} role="listbox"
            className="absolute z-30 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg">
          {shown.map((v, i) => (
            <li key={v} id={`${id}-${i}`} role="option" aria-selected={i === current}
                onMouseDown={(e) => { e.preventDefault(); commit(v) }}
                className={`cursor-pointer px-3 py-1.5 ${i === current ? 'bg-indigo-50 text-indigo-700' : 'text-slate-700 hover:bg-slate-50'}`}>
              {v}
            </li>
          ))}
          {custom && (
            <li id={`${id}-${shown.length}`} role="option" aria-selected={current === shown.length}
                onMouseDown={(e) => { e.preventDefault(); commit(custom) }}
                className={`cursor-pointer border-t border-slate-100 px-3 py-1.5 ${current === shown.length ? 'bg-indigo-50 text-indigo-700' : 'text-slate-500 hover:bg-slate-50'}`}>
              Use “{custom}”
            </li>
          )}
        </ul>
      )}
    </div>
  )
}
