import hmac
import logging
import re
import threading
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator

from . import config, loader
from .filters import Filters
from .search import SORTS, store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")
logging.getLogger("azure").setLevel(logging.WARNING)
_refresh_lock = threading.Lock()


def _load(force: bool):
    """Build (or reuse) the local database, then open it for querying."""
    if not _refresh_lock.acquire(blocking=False):
        return
    try:
        store.status = "refreshing" if store.ready() else "loading"
        warning = None
        try:
            loader.build(force=force, swap=store.swap if store.con is not None else None)
        except Exception as exc:
            # Keep serving the existing local copy if the source can't be reached.
            log.error("Data load failed: %s", type(exc).__name__)
            warning = f"Data source unavailable ({type(exc).__name__}); serving the last local copy"
            if store.con is None and not config.DB_PATH.exists():
                store.status, store.error = "error", f"Data source unavailable ({type(exc).__name__})"
                return
        if store.con is None:
            store.open()
        store.status, store.error = "ready", warning
    finally:
        _refresh_lock.release()


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=_load, args=(False,), daemon=True).start()
    yield
    store.close()


app = FastAPI(title="Candidate Search", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["Content-Type", "X-Refresh-Token"])


EMPTY_SEARCH = "Type what you're looking for or choose at least one filter."


class ResolveRequest(BaseModel):
    """Natural-language query + manually chosen filters + keys of chips the recruiter removed."""
    query: str = Field("", max_length=500)
    filters: Filters = Field(default_factory=Filters)
    dismissed: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("query")
    @classmethod
    def strip(cls, v):
        return v.strip()

    @field_validator("dismissed")
    @classmethod
    def short_keys(cls, v):
        if any(len(k) > 120 for k in v):
            raise ValueError("Invalid filter key")
        return v


class SearchRequest(ResolveRequest):
    page: int = Field(1, ge=1, le=10_000)
    page_size: int = Field(12, ge=1, le=50)
    sort: Literal[tuple(SORTS)] = "relevance"

    @model_validator(mode="after")
    def not_empty(self):
        if not self.query and self.filters.is_empty():
            raise ValueError(EMPTY_SEARCH)
        return self


def _require_ready():
    if not store.ready():
        raise HTTPException(503, "Candidate data is still loading. Please try again shortly."
                            if store.status in ("starting", "loading") else (store.error or "Data unavailable"))


@app.get("/api/health")
def health():
    meta = store.meta or {}
    return {
        "status": store.status,
        "mode": config.DATA_MODE,
        "source": "azure-blob" if config.DATA_MODE == "real" else "fictional-demo",
        "records": meta.get("records"),
        "loaded_at": meta.get("loaded_at"),
        "warning": store.error,
    }


@app.post("/api/resolve")
def resolve(req: ResolveRequest):
    """Filters that a search with this query + manual filters would apply (drives the chips)."""
    _require_ready()
    merged, pq, chip_list, notes, auto = store.resolve(req.query, req.filters, req.dismissed)
    return {"filters": merged.model_dump(), "auto": auto.model_dump(), "chips": chip_list, "notes": notes,
            "parsed": pq.summary()}


@app.post("/api/search")
def search(req: SearchRequest):
    _require_ready()
    merged, pq, chip_list, notes, _ = store.resolve(req.query, req.filters, req.dismissed)
    total, results = store.search(pq, req.page, req.page_size, req.sort)
    resp = {
        "query": req.query,
        "parsed": pq.summary(),
        "filters": merged.model_dump(),
        "chips": chip_list,
        "notes": notes,
        "total": total,
        "page": req.page,
        "page_size": req.page_size,
        "total_pages": max(1, -(-total // req.page_size)),
        "sort": req.sort,
        "results": results,
    }
    if pq.is_empty():
        resp["message"] = ("Couldn't identify a role, skill, location or other criteria in that query."
                           if req.query else EMPTY_SEARCH)
    return resp


@app.get("/api/suggest")
def suggest(field: Literal["role", "skill", "country", "city", "company", "industry"],
            q: str = Query("", max_length=100), limit: int = Query(10, ge=1, le=25)):
    """Dropdown values for the Filters panel, taken from the loaded candidates."""
    _require_ready()
    return {"field": field, "values": store.suggest(field, q, limit)}


@app.get("/api/candidate/{cid}")
def candidate(cid: str):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", cid):
        raise HTTPException(400, "Invalid candidate id")
    _require_ready()
    prof = store.candidate(cid)
    if not prof:
        raise HTTPException(404, "Candidate not found")
    return prof


@app.post("/api/refresh", status_code=202)
def refresh(x_refresh_token: str = Header(default="")):
    if not config.REFRESH_TOKEN:
        raise HTTPException(403, "Refresh is disabled (REFRESH_TOKEN not configured)")
    if not hmac.compare_digest(x_refresh_token.encode(), config.REFRESH_TOKEN.encode()):
        raise HTTPException(401, "Not authorized")
    if _refresh_lock.locked():
        raise HTTPException(409, "A refresh is already running")
    threading.Thread(target=_load, args=(True,), daemon=True).start()
    return {"status": "refresh started"}
