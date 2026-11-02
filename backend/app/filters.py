"""Structured filter model shared by natural-language and manual search.

A query is parsed into the same `Filters` shape the Filters panel edits. The two are
merged (manual values win per category, skills are combined, chips the recruiter removed
stay removed) and the result is turned back into a ParsedQuery for search.build_sql.
"""
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

from .parser import (CITY_ALIASES, COUNTRY_ALIASES, DOMAINS, GENERIC_DEV_TERMS, ROLES, SENIORITY, SKILLS, STACKS,
                     ParsedQuery, Vocab, _set_company, _title, apply_experience)

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
ExpOp = Literal["exact", "min", "gt", "max", "lt", "range", "approx"]
GENERIC_ROLE = "Developer / Engineer"
SINGLE_KEYS = ["name", "role", "seniority", "stack", "experience", "country", "city", "industry"]


class Experience(BaseModel):
    op: ExpOp
    value: float | None = Field(None, ge=0, le=60)
    min: float | None = Field(None, ge=0, le=60)
    max: float | None = Field(None, ge=0, le=60)

    @model_validator(mode="after")
    def check(self):
        if self.op == "range":
            if self.min is None or self.max is None or self.min > self.max:
                raise ValueError("Experience range needs a minimum that is not above the maximum.")
            self.value = None
        elif self.value is None:
            raise ValueError("Enter the number of years of experience.")
        else:
            self.min = self.max = None
        return self


class Filters(BaseModel):
    name: Text | None = None
    role: Text | None = None
    seniority: Literal[tuple(sorted(set(SENIORITY.values())))] | None = None
    skills: list[Text] = Field(default_factory=list, max_length=20)
    skills_mode: Literal["any", "all"] = "any"
    stack: Literal[tuple(STACKS)] | None = None
    experience: Experience | None = None
    country: Text | None = None
    city: Text | None = None
    company: Text | None = None
    company_status: Literal["any", "current", "former"] = "any"
    industry: Literal[tuple(DOMAINS)] | None = None
    keywords: list[Text] = Field(default_factory=list, max_length=20)

    @field_validator("name", "role", "country", "city", "company", "industry", "seniority", "stack", mode="before")
    @classmethod
    def blank_to_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("skills", "keywords")
    @classmethod
    def drop_blank(cls, v):
        return [x for x in v if x]

    def is_empty(self):
        return not any(getattr(self, k) for k in SINGLE_KEYS + ["company", "skills", "keywords"])


# ---------------------------------------------------------------- canonical names
_SKILL_INDEX = {a: name for name, aliases in SKILLS.items() for a in [name.lower(), *aliases]}
_ROLE_INDEX = {p: name for name, (phrases, _) in ROLES.items() for p in [name.lower(), *phrases]}


def canonical_skill(s):
    return _SKILL_INDEX.get(s.strip().lower(), s.strip())


def skill_key(s):
    return "skill:" + canonical_skill(s).lower()


def canonical_role(r):
    low = r.strip().lower()
    if low in ("developer", "developers", "engineer", "engineers", GENERIC_ROLE.lower()):
        return GENERIC_ROLE
    return _ROLE_INDEX.get(low) or _ROLE_INDEX.get(low.rstrip("s")) or r.strip()


# ---------------------------------------------------------------- conversions
def to_filters(pq: ParsedQuery) -> Filters:
    """Filters extracted from a natural-language query."""
    return Filters(
        name=pq.name, role=pq.role, seniority=pq.seniority, skills=[s["name"] for s in pq.skills],
        skills_mode=pq.skills_mode, stack=pq.stack, experience=pq.experience, country=pq.country,
        city=pq.location, company=pq.company, company_status=pq.company_status, industry=pq.domain,
        keywords=pq.keywords)


def from_filters(f: Filters, vocab: Vocab):
    """ParsedQuery for search.build_sql, plus notes such as spelling corrections."""
    pq, notes = ParsedQuery(), []
    if f.name:
        pq.name, pq.name_tokens = _title(f.name), f.name.lower().split()
    if f.role:
        role = canonical_role(f.role)
        if role == GENERIC_ROLE:
            terms = list(GENERIC_DEV_TERMS)
        elif role in ROLES:
            terms = list(ROLES[role][1])
            if f.stack and role == "Full Stack Developer":
                terms += GENERIC_DEV_TERMS  # stack developers are often titled plain "Software Engineer"
        else:
            terms = [role.lower()]
        pq.role, pq.role_terms = role, terms
    pq.seniority = f.seniority
    pq.skills_mode = f.skills_mode
    for s in f.skills:
        name = canonical_skill(s)
        pq.skills.append({"name": name, "aliases": SKILLS.get(name, [name.lower()])})
    if f.stack:
        pq.stack = f.stack
        pq.stack_skills = [{"name": n, "aliases": SKILLS[n]} for n in STACKS[f.stack]]
    if f.experience:
        apply_experience(pq, f.experience.model_dump(exclude_none=True))
    if f.country:
        pq.country = _title(COUNTRY_ALIASES.get(f.country.lower(), f.country.lower()))
    if f.city:
        pq.location = _title(CITY_ALIASES.get(f.city.lower(), f.city.lower()))
    if f.company:
        _set_company(pq, vocab, f.company.lower(), f.company_status, strong=True)
        if pq.company_typed:
            notes.append(f"Spelling corrected: {pq.company_typed} → {pq.company}")
    if f.industry:
        pq.domain, pq.domain_terms = f.industry, DOMAINS[f.industry]
    pq.keywords = [k.lower() for k in f.keywords]
    return pq, notes


def merge(auto: Filters, manual: Filters, dismissed: set) -> Filters:
    """Manual values win per category; skills are combined; removed chips stay removed."""
    out = {}
    for k in SINGLE_KEYS:
        mv, av = getattr(manual, k), getattr(auto, k)
        out[k] = mv if mv else (av if av and k not in dismissed else None)
    if manual.company:
        out["company"], out["company_status"] = manual.company, manual.company_status
    elif auto.company and "company" not in dismissed:
        out["company"], out["company_status"] = auto.company, auto.company_status
    skills, seen = [], set()
    for s in manual.skills + [s for s in auto.skills if skill_key(s) not in dismissed]:
        if skill_key(s) not in seen:
            seen.add(skill_key(s))
            skills.append(canonical_skill(s))
    out["skills"], out["skills_mode"] = skills, manual.skills_mode
    out["keywords"] = [k for k in auto.keywords if f"keyword:{k.lower()}" not in dismissed]
    return Filters(**out)


def chips(merged: Filters, pq: ParsedQuery, auto: Filters, manual: Filters):
    """One removable chip per applied condition. `manual` lists the panel values behind it, `auto` says
    whether the query text also produced it, so the UI knows what removing it must undo."""
    out = []

    def add(key, label, value, manual_values, from_auto):
        out.append({"key": key, "label": label, "value": value, "manual": manual_values, "auto": from_auto})

    simple = {"name": ("Name", pq.name), "role": ("Role", pq.role), "seniority": ("Seniority", pq.seniority),
              "experience": ("Experience", pq.experience_label),
              "country": ("Country", pq.country), "city": ("City", pq.location), "industry": ("Industry", pq.domain)}
    for key, (label, value) in simple.items():
        if getattr(merged, key):
            add(key, label, value, [key] if getattr(manual, key) else [], bool(getattr(auto, key)))
    for s in merged.skills:
        k = skill_key(s)
        add(k, "Skill", s, [m for m in manual.skills if skill_key(m) == k], any(skill_key(a) == k for a in auto.skills))
    if merged.stack:
        add("stack", "Stack", f"{merged.stack.upper()} ({', '.join(STACKS[merged.stack])})", [], True)
    if merged.company:
        status = {"current": " (current)", "former": " (former)", "any": ""}[merged.company_status]
        add("company", "Company", f"{pq.company}{status}", ["company"] if manual.company else [], bool(auto.company))
    for kw in merged.keywords:
        add(f"keyword:{kw.lower()}", "Keyword", kw, [], True)
    return out
