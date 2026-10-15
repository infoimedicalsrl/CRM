from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app import config
from app.auth import require_user
from app.api.routes import router
from app.api.bank_routes import router as bank_router
from app.api.sales_invoice_routes import router as sales_invoice_router
from app.api.purchase_invoice_routes import router as purchase_invoice_router
from app.api.customer_statement_routes import router as customer_statement_router
from app.database.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()  # no-op su Supabase: lo schema si crea con supabase/migrations
    yield


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Cache-Control", "no-store")
        return response


# In produzione la documentazione interattiva non viene esposta.
_docs = {} if not config.ON_VERCEL else {"docs_url": None, "redoc_url": None, "openapi_url": None}
app = FastAPI(title="Peppol Sales Analytics API", version="1.0.0", lifespan=lifespan, **_docs)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=False,  # autenticazione con header Bearer, nessun cookie
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/api/health")
def health():
    """Unica rotta pubblica: non espone dati."""
    return {"status": "ok"}


# Tutte le altre rotte richiedono un utente Supabase autenticato.
_protected = [Depends(require_user)]
app.include_router(router, prefix="/api", dependencies=_protected)
app.include_router(bank_router, prefix="/api", dependencies=_protected)
app.include_router(sales_invoice_router, prefix="/api", dependencies=_protected)
app.include_router(purchase_invoice_router, prefix="/api", dependencies=_protected)
app.include_router(customer_statement_router, prefix="/api", dependencies=_protected)
