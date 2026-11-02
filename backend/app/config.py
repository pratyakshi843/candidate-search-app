import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATA_MODE = os.getenv("DATA_MODE", "real").strip().lower()
if DATA_MODE not in ("real", "demo"):
    raise RuntimeError("DATA_MODE must be 'real' or 'demo'")

DATA_DIR = BACKEND_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)
# Real and fictional data never share a database file.
DB_PATH = DATA_DIR / f"{DATA_MODE}.duckdb"

AZURE_ACCOUNT = os.getenv("AZURE_STORAGE_ACCOUNT", "")
AZURE_CONTAINER = os.getenv("AZURE_CONTAINER", "")
AZURE_BLOB = os.getenv("AZURE_RAW_BLOB", "")
AZURE_SAS = os.getenv("AZURE_STORAGE_SAS_TOKEN", "").lstrip("?")
AZURE_CONN_STR = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")

REFRESH_TOKEN = os.getenv("REFRESH_TOKEN", "")
SHOW_PROFILE_URL = os.getenv("SHOW_PROFILE_URL", "false").lower() == "true"
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
