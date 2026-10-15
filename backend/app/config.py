"""Configurazione centralizzata (solo variabili d'ambiente, nessun segreto nel codice)."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

try:  # In locale legge il file .env nella radice del repository; su Vercel non serve.
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env", override=False)
except ImportError:  # pragma: no cover
    pass

ON_VERCEL = bool(os.getenv("VERCEL"))
LOCAL_DEV_DIR = PROJECT_ROOT / ".local"  # ignorata da git; solo sviluppo/test


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


# --- Database -------------------------------------------------------------
DATABASE_URL = _env("DATABASE_URL")
if not DATABASE_URL:
    if ON_VERCEL:
        raise RuntimeError("DATABASE_URL non configurata: imposta la connection string Supabase su Vercel.")
    LOCAL_DEV_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE_URL = f"sqlite:///{LOCAL_DEV_DIR / 'dev.sqlite'}"  # solo sviluppo locale
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgres://"):]
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL[len("postgresql://"):]
IS_REMOTE_DATABASE = not DATABASE_URL.startswith("sqlite:")

# --- Supabase (Auth + Storage) -------------------------------------------
SUPABASE_URL = _env("SUPABASE_URL").rstrip("/")
SUPABASE_ANON_KEY = _env("SUPABASE_ANON_KEY")                 # pubblica: serve a validare i token
SUPABASE_SERVICE_ROLE_KEY = _env("SUPABASE_SERVICE_ROLE_KEY")  # SEGRETA: solo backend (Storage)
STORAGE_BUCKET = _env("SUPABASE_STORAGE_BUCKET", "documents")

# Se vuoto, qualsiasi utente autenticato di QUESTO progetto Supabase può entrare.
ALLOWED_EMAILS = {e.strip().lower() for e in _env("PEPPOL_ALLOWED_EMAILS").split(",") if e.strip()}

# L'autenticazione è sempre obbligatoria su Vercel. Si può disattivare solo in locale
# (test/sviluppo) con PEPPOL_AUTH_DISABLED=1: il flag viene ignorato in produzione.
AUTH_DISABLED = (not ON_VERCEL) and _env("PEPPOL_AUTH_DISABLED") == "1"

CORS_ORIGINS = [o.strip() for o in _env("PEPPOL_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]

if ON_VERCEL:
    missing = [n for n, v in (("SUPABASE_URL", SUPABASE_URL), ("SUPABASE_ANON_KEY", SUPABASE_ANON_KEY),
                              ("SUPABASE_SERVICE_ROLE_KEY", SUPABASE_SERVICE_ROLE_KEY)) if not v]
    if missing:
        raise RuntimeError("Variabili mancanti su Vercel: " + ", ".join(missing))
