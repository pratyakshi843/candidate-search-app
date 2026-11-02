"""Total professional experience from employment date ranges.

Works on the stored experience entries ({"from": "June 2015" | "2015" | None,
"to": "March 2019" | "2019" | "Present" | None, "is_current": bool}).

Rules:
- Overlapping or back-to-back roles are merged, so parallel jobs are not double-counted.
- A role counts only if it has a valid start and either a valid end or "Present" on a
  current role. A missing end on a non-current role means the duration is unknown, so
  that role is skipped instead of being stretched to today.
- Year-only dates ("2015") use mid-year (July) for both start and end: the unbiased
  estimate when the month is unknown, rather than Jan/Dec which always over-counts.
- Starts before 1950 or in the future, and ranges that end before they start, are invalid.
- A total above MAX_PLAUSIBLE_YEARS signals bad source dates (e.g. a degree recorded as
  an ongoing job since 1963); such totals are reported as unknown (None), not capped.
"""
import re
from datetime import date

MIN_YEAR = 1950
MAX_PLAUSIBLE_YEARS = 50
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], 1)}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
_DATE_RE = re.compile(r"^(?:([a-z]+)\.?\s+)?(\d{4})$")


def _now_index(today=None):
    today = today or date.today()
    return today.year * 12 + today.month - 1


def parse_month(value, today=None):
    """'June 2015' / '2015' -> month index (year*12 + month-1); None if missing/invalid."""
    if not value:
        return None
    m = _DATE_RE.match(str(value).strip().lower())
    if not m:
        return None
    year = int(m.group(2))
    if m.group(1):
        month = MONTHS.get(m.group(1))
        if month is None:
            return None
    else:
        month = 7  # year only: mid-year estimate
    if year < MIN_YEAR or year > (today or date.today()).year:
        return None
    return year * 12 + month - 1


def total_years(experience, today=None):
    """Years of experience (2 decimals), or None when it can't be calculated reliably."""
    now = _now_index(today)
    intervals = []
    for e in experience or []:
        start = parse_month(e.get("from"), today)
        if start is None or start > now:
            continue
        to = (e.get("to") or "").strip().lower()
        if to == "present":
            if not e.get("is_current"):
                continue
            end = now
        else:
            end = parse_month(to, today)
            if end is None:
                continue  # end unknown: don't assume the role is still ongoing
            end = min(end, now)
        if end < start:
            continue
        intervals.append((start, end))
    if not intervals:
        return None

    intervals.sort()
    months, cur_s, cur_e = 0, *intervals[0]
    for s, e in intervals[1:]:
        if s <= cur_e + 1:
            cur_e = max(cur_e, e)
        else:
            months += cur_e - cur_s + 1
            cur_s, cur_e = s, e
    months += cur_e - cur_s + 1
    years = months / 12
    if years > MAX_PLAUSIBLE_YEARS:
        return None
    return round(years, 2)
