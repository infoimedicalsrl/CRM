"""Autenticazione: ogni rotta /api (tranne /api/health) richiede un token Supabase valido.

Il token viene verificato interrogando Supabase Auth (/auth/v1/user), così funziona con
qualsiasi algoritmo di firma delle chiavi del progetto. Il risultato è tenuto in cache
pochi secondi per non fare una chiamata di rete per ogni richiesta.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx
from fastapi import Header, HTTPException

from app import config

_CACHE_TTL = 60.0
_cache: dict[str, tuple[float, dict]] = {}


def _unauthorized(detail: str = "Accesso non autorizzato. Effettua il login.") -> HTTPException:
    return HTTPException(status_code=401, detail=detail, headers={"WWW-Authenticate": "Bearer"})


def _verify_token(token: str) -> dict:
    now = time.monotonic()
    hit = _cache.get(token)
    if hit and hit[0] > now:
        return hit[1]
    if not config.SUPABASE_URL or not config.SUPABASE_ANON_KEY:
        raise HTTPException(503, "Autenticazione non configurata sul server.")
    try:
        resp = httpx.get(
            f"{config.SUPABASE_URL}/auth/v1/user",
            headers={"apikey": config.SUPABASE_ANON_KEY, "Authorization": f"Bearer {token}"},
            timeout=8.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Servizio di autenticazione non raggiungibile.") from exc
    if resp.status_code != 200:
        raise _unauthorized("Sessione scaduta o non valida. Effettua di nuovo il login.")
    user = resp.json()
    if not user.get("id"):
        raise _unauthorized()
    if len(_cache) > 256:
        _cache.clear()
    _cache[token] = (now + _CACHE_TTL, user)
    return user


def require_user(authorization: Optional[str] = Header(default=None)) -> dict:
    if config.AUTH_DISABLED:
        return {"id": "local-dev", "email": "local@dev"}
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized()
    token = authorization[7:].strip()
    if not token:
        raise _unauthorized()
    user = _verify_token(token)
    email = (user.get("email") or "").lower()
    if config.ALLOWED_EMAILS and email not in config.ALLOWED_EMAILS:
        raise HTTPException(403, "Utente non autorizzato ad usare questa applicazione.")
    return user
