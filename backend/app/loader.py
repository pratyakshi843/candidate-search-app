"""Builds the local DuckDB candidate table from the Azure JSONL blob (real mode)
or from generated fictional profiles (demo mode).

The blob is streamed chunk by chunk and parsed line by line; only a compact
projection of each record is written to a temporary JSONL file which DuckDB
then ingests. The source blob is only ever read.
"""
import argparse
import json
import logging
import os
import random
import tempfile
import time
from datetime import date

import duckdb

from . import config
from .experience import total_years

log = logging.getLogger("loader")

COLUMNS = {
    "id": "VARCHAR",
    "name": "VARCHAR",
    "headline": "VARCHAR",
    "current_title": "VARCHAR",
    "current_company": "VARCHAR",
    "location": "VARCHAR",
    "country": "VARCHAR",
    "industry": "VARCHAR",
    "summary": "VARCHAR",
    "profile_url": "VARCHAR",
    "years_experience": "DOUBLE",
    "skills": "VARCHAR[]",
    "experience_json": "VARCHAR",
    "education_json": "VARCHAR",
    "updated_at": "VARCHAR",
    # lower-cased search columns
    "current_text": "VARCHAR",
    "title_text": "VARCHAR",
    "skills_text": "VARCHAR",
    "company_text": "VARCHAR",
    "body_text": "VARCHAR",
    "loc_text": "VARCHAR",
}


# ---------------------------------------------------------------- helpers
def _s(v, limit=None):
    if v is None:
        return None
    if not isinstance(v, str):
        v = str(v)
    v = v.strip()
    if not v:
        return None
    return v[:limit] if limit else v


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _list(v):
    return v if isinstance(v, list) else []


def _month_index(year, month, default_month):
    year = _int(year)
    if not year or year < 1950 or year > date.today().year + 1:
        return None
    month = _int(month) or default_month
    return year * 12 + max(1, min(month, 12)) - 1


def transform(rec: dict) -> dict | None:
    """Project a raw CoreSignal record onto the columns used by the app."""
    if not isinstance(rec, dict):
        return None
    rid = _s(rec.get("id"))
    if not rid or _int(rec.get("deleted")) == 1:
        return None

    all_exp = [e for e in _list(rec.get("experience")) if isinstance(e, dict)]
    exp = [e for e in all_exp if _int(e.get("deleted")) != 1] or all_exp

    def is_current(e):
        # Trust the source flag; only when it is absent, an open-ended dated role counts as current.
        flag = _int(e.get("is_current"))
        return flag == 1 or (flag is None and bool(e.get("date_from_year")) and not e.get("date_to_year"))

    def sort_key(e):
        start = _month_index(e.get("date_from_year"), e.get("date_from_month"), 1) or 0
        return (is_current(e), start)

    exp.sort(key=sort_key, reverse=True)

    experience = []
    for e in exp:
        ongoing = is_current(e)
        experience.append({
            "title": _s(e.get("title"), 200),
            "company": _s(e.get("company_name"), 200),
            "from": _s(e.get("date_from")),
            "to": _s(e.get("date_to")) or ("Present" if ongoing else None),
            "is_current": ongoing,
            "location": _s(e.get("location"), 200),
            "description": _s(e.get("description"), 600),
        })

    current = next((e for e in experience if e["is_current"] and e["title"]), experience[0] if experience else None)

    skills = []
    seen = set()
    for sk in _list(rec.get("inferred_skills")):
        sk = _s(sk, 80)
        if sk and sk.lower() not in seen:
            seen.add(sk.lower())
            skills.append(sk)

    education = []
    for ed in _list(rec.get("education")):
        if isinstance(ed, dict) and _int(ed.get("deleted")) != 1:
            education.append({
                "institution": _s(ed.get("institution"), 200),
                "program": _s(ed.get("program"), 200),
                "from": _int(ed.get("date_from_year")),
                "to": _int(ed.get("date_to_year")),
            })

    headline = _s(rec.get("headline"), 300)
    summary = _s(rec.get("summary"), 3000)
    industry = _s(rec.get("industry"), 200)
    titles = [e["title"] for e in experience if e["title"]]
    companies = [e["company"] for e in experience if e["company"]]
    location = _s(rec.get("location"), 200)
    country = _s(rec.get("country"), 100)

    def low(*parts):
        return " | ".join(p for p in parts if p).lower()

    return {
        "id": rid,
        "name": _s(rec.get("full_name"), 200),
        "headline": headline,
        "current_title": current["title"] if current else None,
        "current_company": current["company"] if current else None,
        "location": location,
        "country": country,
        "industry": industry,
        "summary": summary,
        "profile_url": _s(rec.get("profile_url"), 300),
        "years_experience": total_years(experience),
        "skills": skills,
        "experience_json": json.dumps(experience, ensure_ascii=False),
        "education_json": json.dumps(education, ensure_ascii=False),
        "updated_at": _s(rec.get("updated_at")),
        "current_text": low(current["title"] if current else None, headline),
        "title_text": low(headline, *titles),
        "skills_text": "|" + "|".join(s.lower() for s in skills) + "|",
        "company_text": low(*companies),
        "body_text": low(headline, industry, summary, *companies,
                         *[e["description"] for e in experience if e["description"]]),
        "loc_text": low(location, _s(rec.get("city")), _s(rec.get("state")), country),
    }


# ---------------------------------------------------------------- azure
def blob_client():
    from azure.storage.blob import BlobClient, BlobServiceClient

    if not (config.AZURE_CONTAINER and config.AZURE_BLOB):
        raise RuntimeError("AZURE_CONTAINER / AZURE_RAW_BLOB not configured")
    if config.AZURE_SAS and config.AZURE_ACCOUNT:
        return BlobClient(f"https://{config.AZURE_ACCOUNT}.blob.core.windows.net",
                          config.AZURE_CONTAINER, config.AZURE_BLOB, credential=config.AZURE_SAS)
    if config.AZURE_CONN_STR:
        return BlobServiceClient.from_connection_string(config.AZURE_CONN_STR).get_blob_client(
            config.AZURE_CONTAINER, config.AZURE_BLOB)
    raise RuntimeError("No Azure credentials configured (AZURE_STORAGE_SAS_TOKEN or AZURE_STORAGE_CONNECTION_STRING)")


def source_signature() -> dict:
    props = blob_client().get_blob_properties()
    return {"etag": props.etag, "size": props.size, "last_modified": props.last_modified.isoformat(),
            "source_blob": f"{config.AZURE_ACCOUNT}/{config.AZURE_CONTAINER}/{props.name}"}


def iter_azure_records(stats: dict):
    """Stream the blob and yield parsed JSON objects one line at a time."""
    downloader = blob_client().download_blob(max_concurrency=4)
    buf = b""
    for chunk in downloader.chunks():
        buf += chunk
        *lines, buf = buf.split(b"\n")
        for line in lines:
            yield from _parse_line(line, stats)
    if buf:
        yield from _parse_line(buf, stats)


def _parse_line(line: bytes, stats: dict):
    line = line.strip()
    if not line:
        return
    stats["lines"] += 1
    try:
        yield json.loads(line.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, ValueError):
        stats["malformed"] += 1


# ---------------------------------------------------------------- demo data
DEMO_ROLES = {
    "Software Engineer": ["Python", "Java", "JavaScript", "SQL", "Git", "AWS", "Docker"],
    "Backend Developer": ["Python", "Django", "Node.js", "Express", "PostgreSQL", "MongoDB", "REST APIs", "Microservices"],
    "Frontend Developer": ["React", "JavaScript", "TypeScript", "HTML", "CSS", "Redux", "Tailwind CSS"],
    "Full Stack Developer": ["React", "Node.js", "Express", "MongoDB", "JavaScript", "TypeScript", "AWS"],
    "Data Scientist": ["Python", "Machine Learning", "Pandas", "SQL", "TensorFlow", "Statistics"],
    "DevOps Engineer": ["AWS", "Kubernetes", "Docker", "Terraform", "Linux", "Jenkins"],
    "QA Engineer": ["Selenium", "Python", "Test Automation", "Jira"],
    "Product Manager": ["Product Strategy", "Agile", "Roadmapping", "Stakeholder Management"],
}
DEMO_COMPANIES = ["Northwind Labs", "Bluefin Payments", "Acorn Health", "Lumen Retail", "Quartz Fintech",
                  "Harbor Logistics", "Pixel Forge Games", "Cedar Insurance", "Orbit SaaS", "Maple EdTech"]
DEMO_LOCATIONS = [("Bengaluru, Karnataka, India", "India"), ("Pune, Maharashtra, India", "India"),
                  ("London, England, United Kingdom", "United Kingdom"), ("Manchester, England, United Kingdom", "United Kingdom"),
                  ("New York, New York, United States", "United States"), ("Austin, Texas, United States", "United States"),
                  ("Berlin, Germany", "Germany"), ("Toronto, Ontario, Canada", "Canada"), ("Singapore", "Singapore")]


def iter_demo_records(n=1500, seed=42):
    """Fictional profiles. No names or other personal fields are generated."""
    rng = random.Random(seed)
    this_year = date.today().year
    for i in range(1, n + 1):
        role = rng.choice(list(DEMO_ROLES))
        years = rng.randint(0, 18)
        level = "Senior " if years >= 6 and rng.random() < 0.6 else ("Junior " if years <= 2 else "")
        loc, country = rng.choice(DEMO_LOCATIONS)
        exp, start = [], this_year - years
        companies = rng.sample(DEMO_COMPANIES, k=min(3, max(1, years // 4 + 1)))
        span = max(1, years // len(companies)) if years else 1
        for j, comp in enumerate(companies):
            is_cur = j == len(companies) - 1
            y_from = start + j * span
            exp.append({"title": (level if is_cur else "") + role, "company_name": comp, "date_from": str(y_from),
                        "date_from_year": y_from, "date_to": None if is_cur else str(y_from + span),
                        "date_to_year": None if is_cur else y_from + span, "is_current": int(is_cur),
                        "description": f"{role} work at {comp}."})
        yield {"id": f"DEMO-{i:05d}", "headline": f"{level}{role} at {companies[-1]}", "location": loc,
               "country": country, "experience": exp,
               "inferred_skills": rng.sample(DEMO_ROLES[role], k=min(len(DEMO_ROLES[role]), rng.randint(3, 6)))}


# ---------------------------------------------------------------- build
def build(force=False, swap=None) -> dict:
    """Create/refresh the DuckDB file. Returns metadata about the loaded data.

    `swap` lets a running server close its connection around the file replace.
    """
    db_path = config.DB_PATH
    signature = {"etag": "demo-v1", "size": 0, "last_modified": None}
    if config.DATA_MODE == "real":
        signature = source_signature()

    if db_path.exists() and not force:
        meta = read_meta(db_path)
        if meta and meta.get("etag") == signature["etag"]:
            log.info("Reusing local database (%s records, source unchanged)", meta.get("records"))
            return meta

    started = time.time()
    stats = {"lines": 0, "malformed": 0, "skipped": 0}
    records = iter_azure_records(stats) if config.DATA_MODE == "real" else iter_demo_records()

    fd, tmp_jsonl = tempfile.mkstemp(suffix=".jsonl", dir=config.DATA_DIR)
    tmp_db = db_path.with_suffix(".building.duckdb")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            for rec in records:
                if config.DATA_MODE == "demo":
                    stats["lines"] += 1
                try:
                    row = transform(rec)
                except Exception:  # never let one odd record stop the load
                    row = None
                if row is None:
                    stats["skipped"] += 1
                    continue
                out.write(json.dumps(row, ensure_ascii=False) + "\n")

        if tmp_db.exists():
            tmp_db.unlink()
        con = duckdb.connect(str(tmp_db))
        cols = ", ".join(f"'{k}': '{v}'" for k, v in COLUMNS.items())
        con.execute(f"""
            CREATE TABLE candidates AS
            SELECT * FROM read_json(?, format='newline_delimited', columns={{{cols}}})
            QUALIFY row_number() OVER (PARTITION BY id ORDER BY updated_at DESC NULLS LAST) = 1
        """, [tmp_jsonl])
        count = con.execute("SELECT count(*) FROM candidates").fetchone()[0]
        meta = {**signature, "mode": config.DATA_MODE, "records": count, "source_lines": stats["lines"],
                "malformed_lines": stats["malformed"], "skipped_records": stats["skipped"],
                "loaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "seconds": round(time.time() - started, 1)}
        con.execute("CREATE TABLE meta (k VARCHAR, v VARCHAR)")
        con.executemany("INSERT INTO meta VALUES (?, ?)", [(k, json.dumps(v)) for k, v in meta.items()])
        con.close()
        do_replace = lambda: os.replace(tmp_db, db_path)
        swap(do_replace) if swap else do_replace()
        log.info("Loaded %s records in %ss", count, meta["seconds"])
        return meta
    finally:
        if os.path.exists(tmp_jsonl):
            os.remove(tmp_jsonl)
        if tmp_db.exists():
            tmp_db.unlink()


def read_meta(path=None) -> dict | None:
    try:
        con = duckdb.connect(str(path or config.DB_PATH), read_only=True)
        try:
            return {k: json.loads(v) for k, v in con.execute("SELECT k, v FROM meta").fetchall()}
        finally:
            con.close()
    except Exception:
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("azure").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser(description="Load candidate data into DuckDB")
    ap.add_argument("--refresh", action="store_true", help="rebuild even if the source is unchanged")
    print(json.dumps(build(force=ap.parse_args().refresh), indent=2))
