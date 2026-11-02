export default function Initials({ name, id, size = 'h-11 w-11 text-sm' }) {
  const text = name
    ? name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase()
    : '#'
  return (
    <div className={`${size} shrink-0 rounded-full bg-indigo-100 text-indigo-700 font-semibold flex items-center justify-center`}
         aria-hidden="true" title={name || id}>
      {text}
    </div>
  )
}
