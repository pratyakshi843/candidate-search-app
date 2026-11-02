import json
import re
import threading
from collections import Counter
from functools import lru_cache

import duckdb

from . import config
from .experience import total_years
from .filters import Filters, chips, from_filters, merge, to_filters
from .parser import DOMAINS, ROLES, SKILLS, ParsedQuery, Vocab, parse_query

SORTS = {
    "relevance": "score DESC, years_experience DESC NULLS LAST, id",
    "experience_desc": "years_experience DESC NULLS LAST, score DESC, id",
    "experience_asc": "years_experience ASC NULLS LAST, score DESC, id",
    "recent": "updated_at DESC NULLS LAST, score DESC, id",
}
ALL_TEXT = "(title_text || ' ' || skills_text || ' ' || body_text)"
_RE2_META = set(r"\.^$|?*+()[]{}")


def _esc(term: str) -> str:
    return "".join("\\" + c if c in _RE2_META else c for c in term.lower())


def term_re(terms) -> str:
    """Case-insensitive RE2 pattern matching any term as a whole token (c++, node.js safe)."""
    alts = "|".join(_esc(t) for t in sorted(set(terms), key=len, reverse=True))
    return f"(^|[^a-z0-9])({alts})($|[^a-z0-9+#])"


def py_re(terms):
    """Python-re version of term_re, for highlighting matches in results."""
    return re.compile(term_re(terms).replace("(^|", "(?:^|").replace("($|", "(?:$|"))


def _levenshtein(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _derived(experience_json):
    """Columns computed when the database is opened (the stored file is never modified)."""
    exp = json.loads(experience_json or "[]")
    cur = [e["company"] for e in exp if e.get("is_current") and e.get("company")]
    past = [e["company"] for e in exp if not e.get("is_current") and e.get("company")]
    titles = [e["title"] for e in exp if e.get("title")]
    return total_years(exp), " | ".join(cur).lower(), " | ".join(past).lower(), " | ".join(titles).lower()


class Store:
    """Holds the read-only DuckDB connection; swapped atomically on refresh."""

    def __init__(self):
        self.lock = threading.RLock()
        self.con = None
        self.vocab = Vocab()
        self.meta = None
        self.status = "starting"
        self.error = None

    # ------------------------------------------------------------ lifecycle
    def open(self):
        with self.lock:
            self.close()
            # Copy the on-disk table into memory and add derived columns there; the file stays read-only.
            con = duckdb.connect(":memory:")
            con.execute(f"ATTACH '{config.DB_PATH.as_posix()}' AS src (READ_ONLY)")
            con.execute("CREATE TABLE candidates AS SELECT * FROM src.candidates")
            self.meta = {k: json.loads(v) for k, v in con.execute("SELECT k, v FROM src.meta").fetchall()}
            con.execute("DETACH src")

            ids, years, cur, past, roles, changed = [], [], [], [], [], 0
            for rid, stored, ej in con.execute("SELECT id, years_experience, experience_json FROM candidates").fetchall():
                y, c, p, t = _derived(ej)
                ids.append(rid), years.append(y), cur.append(c), past.append(p), roles.append(t)
                changed += stored != y
            con.execute("""
                CREATE TABLE derived AS SELECT unnest($1) AS id, unnest($2)::DOUBLE AS years, unnest($3) AS cur,
                                               unnest($4) AS past, unnest($5) AS roles""", [ids, years, cur, past, roles])
            con.execute("""
                CREATE OR REPLACE TABLE candidates AS
                SELECT c.* REPLACE (d.years AS years_experience),
                       d.cur AS current_company_text, d.past AS past_company_text, d.roles AS role_text,
                       lower(coalesce(c.name, '')) AS name_text
                FROM candidates c JOIN derived d USING (id)""")
            con.execute("DROP TABLE derived")
            self.meta["experience_recalculated"] = changed
            self.con = con
            self._build_vocab()
            self.status, self.error = "ready", None

    def close(self):
        with self.lock:
            if self.con is not None:
                self.con.close()
                self.con = None

    def swap(self, replace_file):
        with self.lock:
            self.close()
            replace_file()
            self.open()

    def _build_vocab(self):
        con = self.con
        countries = {r[0] for r in con.execute(
            "SELECT DISTINCT lower(country) FROM candidates WHERE country IS NOT NULL").fetchall()}
        skills = {r[0] for r in con.execute("""
            SELECT s FROM (SELECT lower(unnest(skills)) AS s FROM candidates)
            WHERE length(s) BETWEEN 2 AND 40 GROUP BY s HAVING count(*) >= 3""").fetchall()}
        company_words = dict(con.execute("""
            SELECT t, count(*) FROM (SELECT unnest(regexp_split_to_array(company_text, '[^a-z0-9]+')) AS t
                                    FROM candidates) WHERE length(t) >= 2 GROUP BY t""").fetchall())
        columns = {"company": "company_text", "title": "role_text", "location": "loc_text"}

        @lru_cache(maxsize=4096)
        def count(kind, phrase):
            """Candidates whose name / companies / job titles / location contain the phrase."""
            words = phrase.strip().lower().split()
            if not words:
                return 0
            if kind == "name":  # every word of the name, in any order
                conds, params = " AND ".join(["regexp_matches(name_text, ?)"] * len(words)), [term_re([w]) for w in words]
            else:
                conds, params = f"regexp_matches({columns[kind]}, ?)", [term_re([" ".join(words)])]
            with self.lock:
                return self.con.execute(f"SELECT count(*) FROM candidates WHERE {conds}", params).fetchone()[0]

        @lru_cache(maxsize=1024)
        def correct_company(phrase):
            """Fix small typos word by word ('mahendra bank' -> 'mahindra bank') using words from company names."""
            out, changed = [], False
            for w in phrase.lower().split():
                if w in company_words or len(w) < 4:
                    out.append(w)
                    continue
                limit = 1 if len(w) < 8 else 2
                near = [(n, t) for t, n in company_words.items()
                        if t[0] == w[0] and abs(len(t) - len(w)) <= limit and _levenshtein(w, t) <= limit]
                if not near:
                    return None
                out.append(max(near)[1])  # most common spelling
                changed = True
            fixed = " ".join(out)
            return fixed if changed and count("company", fixed) > 0 else None

        self.vocab = Vocab(countries=countries, skills=skills, location_exists=lambda t: count("location", t) > 0,
                           count=count, correct_company=correct_company)
        self._build_options()

    def _build_options(self):
        """Values offered by the Filters panel dropdowns, most common first."""
        con = self.con

        def ranked(sql, extra=()):
            seen, out = set(), []
            for v in [*extra, *(r[0] for r in con.execute(sql).fetchall())]:
                if v and v.strip() and v.strip().lower() not in seen:
                    seen.add(v.strip().lower())
                    out.append(v.strip())
            return out

        companies = Counter()
        for (ej,) in con.execute("SELECT experience_json FROM candidates").fetchall():
            for e in json.loads(ej or "[]"):
                if e.get("company"):
                    companies[e["company"].strip()] += 1
        self.options = {
            "role": ranked("SELECT current_title FROM candidates WHERE current_title IS NOT NULL "
                           "GROUP BY 1 ORDER BY count(*) DESC, 1", extra=list(ROLES)),
            "skill": ranked("SELECT s FROM (SELECT unnest(skills) AS s FROM candidates) GROUP BY 1 "
                            "HAVING count(*) >= 2 ORDER BY count(*) DESC, 1", extra=list(SKILLS)),
            "country": ranked("SELECT country FROM candidates WHERE country IS NOT NULL GROUP BY 1 ORDER BY count(*) DESC"),
            "city": ranked("SELECT trim(split_part(location, ',', 1)) FROM candidates WHERE location LIKE '%,%' "
                           "GROUP BY 1 ORDER BY count(*) DESC"),
            "company": [c for c, _ in companies.most_common()],
            "industry": list(DOMAINS),
        }

    def suggest(self, field: str, q: str, limit: int):
        q = q.strip().lower()
        values = self.options.get(field, [])
        if not q:
            return values[:limit]
        prefix = [v for v in values if v.lower().startswith(q)]
        if len(prefix) >= limit:
            return prefix[:limit]
        words = [v for v in values if not v.lower().startswith(q) and q in v.lower()]
        return (prefix + words)[:limit]

    # ------------------------------------------------------------ queries
    def ready(self):
        return self.con is not None  # keeps serving the current copy while a refresh builds

    def resolve(self, query: str, manual: Filters | None = None, dismissed=()):
        """Merge the filters parsed from the query with the manually chosen ones.

        Returns (merged Filters, ParsedQuery for SQL, chips, notes, Filters parsed from the query alone)."""
        manual = manual or Filters()
        with self.lock:
            auto_pq = parse_query(query, self.vocab) if query.strip() else ParsedQuery()
            auto = to_filters(auto_pq)
            merged = merge(auto, manual, set(dismissed))
            pq, notes = from_filters(merged, self.vocab)
            if auto_pq.company_typed and not manual.company and merged.company == auto.company:
                notes.append(f"Spelling corrected: {auto_pq.company_typed} \u2192 {auto_pq.company}")
            return merged, pq, chips(merged, pq, auto, manual), notes, auto

    def search(self, pq: ParsedQuery, page: int, page_size: int, sort: str):
        with self.lock:
            if pq.is_empty():
                return 0, []
            score_sql, score_params, where_sql, where_params = build_sql(pq)
            total = self.con.execute(f"SELECT count(*) FROM candidates WHERE {where_sql}", where_params).fetchone()[0]
            rows = self.con.execute(f"""
                SELECT id, name, headline, current_title, current_company, location, country, years_experience,
                       skills, experience_json, {score_sql} AS score
                FROM candidates WHERE {where_sql}
                ORDER BY {SORTS[sort]} LIMIT ? OFFSET ?""",
                score_params + where_params + [page_size, (page - 1) * page_size]).fetchall()
            cols = ["id", "name", "headline", "current_title", "current_company", "location", "country",
                    "years_experience", "skills", "experience_json", "score"]
            return total, [card(dict(zip(cols, r)), pq) for r in rows]

    def candidate(self, cid: str):
        with self.lock:
            cur = self.con.execute("SELECT * EXCLUDE (current_company_text, past_company_text, role_text, name_text) "
                                   "FROM candidates WHERE id = ?", [cid])
            row = cur.fetchone()
            if not row:
                return None
            return profile(dict(zip([d[0] for d in cur.description], row)))


def build_sql(pq: ParsedQuery):
    score, sp, where, wp = [], [], [], []

    if pq.name_tokens:
        for tok in pq.name_tokens:
            where.append("regexp_matches(name_text, ?)")
            wp.append(term_re([tok]))
        score.append("(CASE WHEN name_text = ? THEN 100 WHEN starts_with(name_text, ?) THEN 70 ELSE 60 END)")
        sp += [" ".join(pq.name_tokens), pq.name_tokens[0] + " "]

    if pq.role_terms:
        pat = term_re(pq.role_terms)
        where.append("regexp_matches(title_text, ?)")
        wp.append(pat)
        score.append("(CASE WHEN regexp_matches(lower(coalesce(current_title, '')), ?) THEN 40 "
                     "WHEN regexp_matches(lower(coalesce(headline, '')), ?) THEN 28 ELSE 15 END)")
        sp += [pat, pat]

    if pq.seniority:
        sen_terms = {"Senior": ["senior", "sr", "sr."], "Junior": ["junior", "jr", "jr."]}.get(
            pq.seniority, [pq.seniority.lower()])
        score.append("(CASE WHEN regexp_matches(current_text, ?) THEN 8 ELSE 0 END)")
        sp.append(term_re(sen_terms))
        if pq.seniority in ("Senior", "Lead", "Principal", "Staff", "Head"):
            score.append("least(coalesce(years_experience, 0), 12) * 0.4")

    def skill_group(skills, need):
        hits = []
        for s in skills:
            pat = term_re(s["aliases"])
            hits.append(f"CAST(regexp_matches({ALL_TEXT}, ?) AS INTEGER)")
            wp.append(pat)
            score.append("(CASE WHEN regexp_matches(skills_text, ?) THEN 12 "
                         "WHEN regexp_matches(current_text, ?) THEN 10 "
                         f"WHEN regexp_matches({ALL_TEXT}, ?) THEN 5 ELSE 0 END)")
            sp.extend([pat, pat, pat])
        return f"({' + '.join(hits)}) >= {int(min(need, len(skills)))}"

    if pq.skills:
        where.append(skill_group(pq.skills, len(pq.skills) if pq.skills_mode == "all" else 1))
    if pq.stack_skills:
        cond = skill_group(pq.stack_skills, 2)
        where.append(f"({cond} OR regexp_matches({ALL_TEXT}, ?))")
        wp.append(term_re([pq.stack, pq.stack + " stack"]))

    eps = 1e-9  # float slack so 4.9 and 5.1 stay inside "exactly 5 (+/-0.1)"
    if pq.min_years is not None:
        where.append("years_experience > ?" if pq.min_exclusive else "years_experience >= ?")
        wp.append(pq.min_years if pq.min_exclusive else pq.min_years - eps)
    if pq.max_years is not None:
        where.append("years_experience < ?" if pq.max_exclusive else "years_experience <= ?")
        wp.append(pq.max_years if pq.max_exclusive else pq.max_years + eps)

    if pq.country:
        where.append("lower(country) = ?")
        wp.append(pq.country.lower())
    if pq.location:
        where.append("regexp_matches(loc_text, ?)")
        wp.append(term_re([pq.location]))

    if pq.company:
        pat = term_re([pq.company])
        if pq.company_status == "current":
            where.append("regexp_matches(current_company_text, ?)")
            wp.append(pat)
        elif pq.company_status == "former":
            where.append("regexp_matches(past_company_text, ?) AND NOT regexp_matches(current_company_text, ?)")
            wp += [pat, pat]
        else:
            where.append("regexp_matches(company_text, ?)")
            wp.append(pat)
        score.append("(CASE WHEN regexp_matches(current_company_text, ?) THEN 15 ELSE 5 END)")
        sp.append(pat)

    if pq.domain_terms:
        pat = term_re(pq.domain_terms)
        where.append("regexp_matches(body_text, ?)")
        wp.append(pat)
        score.append("(CASE WHEN regexp_matches(lower(coalesce(current_company, '') || ' ' || current_text), ?) "
                     "THEN 15 WHEN regexp_matches(company_text, ?) THEN 10 ELSE 3 END)")
        sp += [pat, pat]

    for kw in pq.keywords:
        pat = term_re([kw])
        where.append(f"regexp_matches({ALL_TEXT}, ?)")
        wp.append(pat)
        score.append("(CASE WHEN regexp_matches(current_text, ?) THEN 8 ELSE 3 END)")
        sp.append(pat)

    score.append("least(coalesce(years_experience, 0), 20) * 0.1")  # mild tie-break
    return " + ".join(score), sp, " AND ".join(where) or "TRUE", wp


# ---------------------------------------------------------------- serialisers
def _matched_skills(skills, pq):
    matched = []
    for s in pq.skills + pq.stack_skills:
        rx = py_re(s["aliases"])
        for sk in skills or []:
            if rx.search(sk.lower()) and sk not in matched:
                matched.append(sk)
    return matched


def _display_name(row):
    # Fictional demo mode never exposes names; the anonymised ID is shown instead.
    return row.get("name") if config.DATA_MODE == "real" else None


def _company_match(exp, pq):
    """The role at the searched company: the current one first, else the most recent former one."""
    if not pq.company:
        return None
    rx = py_re([pq.company.lower()])
    hits = [e for e in exp if e.get("company") and rx.search(e["company"].lower())]
    hit = next((e for e in hits if e.get("is_current")), hits[0] if hits else None)
    if not hit:
        return None
    return {"status": "current" if hit.get("is_current") else "former", "title": hit.get("title"),
            "company": hit["company"], "from": hit.get("from"), "to": hit.get("to")}


def card(row, pq):
    exp = json.loads(row["experience_json"] or "[]")
    skills = row["skills"] or []
    matched = _matched_skills(skills, pq)
    ordered = matched + [s for s in skills if s not in matched]
    previous = [{"title": e["title"], "company": e["company"]} for e in exp
                if not e.get("is_current") and e.get("company")][:2]
    return {
        "id": row["id"],
        "name": _display_name(row),
        "headline": row["headline"],
        "current_title": row["current_title"],
        "current_company": row["current_company"],
        "location": row["location"] or row["country"],
        "years_experience": row["years_experience"],
        "skills": ordered[:10],
        "skills_total": len(skills),
        "matched_skills": matched,
        "previous": previous,
        "company_match": _company_match(exp, pq),
        "score": round(row["score"] or 0, 1),
    }


def profile(row):
    out = {
        "id": row["id"],
        "name": _display_name(row),
        "headline": row["headline"],
        "current_title": row["current_title"],
        "current_company": row["current_company"],
        "location": row["location"],
        "country": row["country"],
        "industry": row["industry"],
        "summary": row["summary"],
        "years_experience": row["years_experience"],
        "skills": row["skills"] or [],
        "experience": json.loads(row["experience_json"] or "[]"),
        "education": json.loads(row["education_json"] or "[]"),
    }
    if config.DATA_MODE == "real" and config.SHOW_PROFILE_URL:
        out["profile_url"] = row["profile_url"]
    return out


store = Store()
