import { useEffect, useState } from 'react'
import { suggest } from '../api'
import Combobox from './Combobox'

const EXP_OPS = [
  ['', 'Any experience'],
  ['exact', 'Exactly'],
  ['min', 'At least (N+)'],
  ['gt', 'More than'],
  ['max', 'At most'],
  ['lt', 'Less than'],
  ['range', 'Between'],
  ['approx', 'About'],
]
const COMPANY_STATUS = [
  ['any', 'Current or former'],
  ['current', 'Current employees'],
  ['former', 'Former employees'],
]

// Panel values show what will be applied: the panel's own choice, else what the query produced.
// Controls are re-mounted (via `keyFor`) only when a value changes from outside the panel,
// e.g. a chip was removed or the query was edited, so typing in the panel never loses focus.
export default function FilterPanel({ value, auto, version, actions, onClose }) {
  const [industries, setIndustries] = useState([])
  useEffect(() => {
    suggest('industry', '', 25).then((r) => setIndustries(r.values)).catch(() => {})
  }, [])
  const keyFor = (k) => `${version}:${JSON.stringify(auto?.[k] ?? null)}`

  return (
    <div id="filter-panel" className="mt-3 border-t border-slate-100 pt-4">
      <div className="grid gap-x-5 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field label="Role">
          <Combobox key={keyFor('role')} field="role" label="Role" value={value.role || ''}
                    placeholder="e.g. Backend Developer" onSelect={(v) => actions.setSingle('role', v)} />
        </Field>

        <Field label="Skills">
          <Combobox field="skill" label="Add skill" multi placeholder="Search and add skills"
                    exclude={value.skills} onSelect={actions.addSkill} />
          {value.skills.length > 1 && (
            <div className="mt-2 flex gap-1 text-xs" role="radiogroup" aria-label="Skill matching">
              {[['any', 'Match any'], ['all', 'Match all']].map(([m, l]) => (
                <button key={m} type="button" role="radio" aria-checked={value.skills_mode === m}
                        onClick={() => actions.setSkillsMode(m)}
                        className={`rounded-md px-2 py-1 border ${value.skills_mode === m ? 'border-indigo-600 bg-indigo-600 text-white' : 'border-slate-300 text-slate-600 hover:border-indigo-300'}`}>
                  {l}
                </button>
              ))}
            </div>
          )}
        </Field>

        <Field label="Experience (years)">
          <ExperienceField key={keyFor('experience')} value={value.experience} onChange={actions.setExperience} />
        </Field>

        <Field label="Country">
          <Combobox key={keyFor('country')} field="country" label="Country" value={value.country || ''}
                    placeholder="e.g. India" onSelect={(v) => actions.setSingle('country', v)} />
        </Field>

        <Field label="City">
          <Combobox key={keyFor('city')} field="city" label="City" value={value.city || ''}
                    placeholder="e.g. Bengaluru" onSelect={(v) => actions.setSingle('city', v)} />
        </Field>

        <Field label="Industry">
          <select value={value.industry || ''} onChange={(e) => actions.setSingle('industry', e.target.value || null)}
                  aria-label="Industry"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
            <option value="">Any industry</option>
            {industries.map((i) => <option key={i} value={i}>{i}</option>)}
          </select>
        </Field>

        <Field label="Company" className="sm:col-span-2 lg:col-span-1">
          <Combobox key={keyFor('company')} field="company" label="Company" value={value.company || ''}
                    placeholder="e.g. Google" onSelect={(v) => actions.setCompany(v, value.company_status)} />
          <select value={value.company_status} aria-label="Employment at company"
                  onChange={(e) => actions.setCompany(value.company, e.target.value)}
                  className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
            {COMPANY_STATUS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
        </Field>
      </div>

      <div className="mt-4 flex justify-end">
        <button type="button" onClick={onClose}
                className="rounded-lg border border-slate-300 px-4 py-1.5 text-sm text-slate-700 hover:border-indigo-300 hover:text-indigo-700">
          Done
        </button>
      </div>
    </div>
  )
}

function Field({ label, className = '', children }) {
  return (
    <div className={className}>
      <p className="mb-1.5 text-xs font-medium text-slate-500">{label}</p>
      {children}
    </div>
  )
}

function ExperienceField({ value, onChange }) {
  const [op, setOp] = useState(value?.op || '')
  const [a, setA] = useState(String((value?.op === 'range' ? value?.min : value?.value) ?? ''))
  const [b, setB] = useState(String(value?.max ?? ''))
  const num = (s) => (s.trim() === '' || Number.isNaN(Number(s)) ? null : Number(s))

  const update = (nextOp, nextA, nextB) => {
    setOp(nextOp); setA(nextA); setB(nextB)
    const x = num(nextA)
    const y = num(nextB)
    if (!nextOp) onChange(null)
    else if (nextOp === 'range') { if (x !== null && y !== null && x >= 0 && x <= y && y <= 60) onChange({ op: 'range', min: x, max: y }) }
    else if (x !== null && x >= 0 && x <= 60) onChange({ op: nextOp, value: x })
  }

  const x = num(a)
  const y = num(b)
  const invalid = op && (x === null || x < 0 || x > 60 || (op === 'range' && (y === null || y < x || y > 60)))
  const input = 'w-full min-w-0 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500'

  return (
    <div>
      <div className="flex gap-2">
        <select value={op} aria-label="Experience condition" onChange={(e) => update(e.target.value, a, b)}
                className="rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500">
          {EXP_OPS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        {op && (
          <input type="number" min="0" max="60" step="0.5" inputMode="decimal" value={a} aria-label={op === 'range' ? 'Minimum years' : 'Years'}
                 placeholder={op === 'range' ? 'from' : 'years'} onChange={(e) => update(op, e.target.value, b)} className={input} />
        )}
        {op === 'range' && (
          <input type="number" min="0" max="60" step="0.5" inputMode="decimal" value={b} aria-label="Maximum years"
                 placeholder="to" onChange={(e) => update(op, a, e.target.value)} className={input} />
        )}
      </div>
      {invalid && (a !== '' || b !== '') && (
        <p className="mt-1 text-xs text-rose-600">
          {op === 'range' ? 'Enter a range between 0 and 60, from ≤ to.' : 'Enter a number of years between 0 and 60.'}
        </p>
      )}
      {op === 'exact' && !invalid && <p className="mt-1 text-xs text-slate-400">Matches {a} ± 0.1 years.</p>}
    </div>
  )
}
