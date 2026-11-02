export function formatYears(y) {
  if (y === null || y === undefined) return null
  const r = Math.round(y * 10) / 10
  return `${Number.isInteger(r) ? r : r.toFixed(1)} yr${r === 1 ? '' : 's'}`
}
