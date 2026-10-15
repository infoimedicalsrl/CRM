"""Archivio dei documenti originali (XML, PDF, CSV, Excel) su Supabase Storage.

Il bucket è PRIVATO: i file sono accessibili solo tramite il backend, che usa la
service-role key (mai esposta al browser). In sviluppo locale, senza Supabase,
i file vanno in una cartella ignorata da git.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import httpx

from app import config


class StorageError(RuntimeError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name or "file").name).strip("._") or "file"
    return base[:120]


def build_key(prefix: str, digest: str, ext: str) -> str:
    """Chiave stabile e basata sul contenuto: lo stesso file ha sempre la stessa chiave."""
    ext = ext if ext.startswith(".") else f".{ext}"
    return f"{prefix}/{digest}{re.sub(r'[^A-Za-z0-9.]', '', ext.lower())}"


class _SupabaseStorage:
    def __init__(self) -> None:
        self.base = f"{config.SUPABASE_URL}/storage/v1/object/{config.STORAGE_BUCKET}"
        key = config.SUPABASE_SERVICE_ROLE_KEY
        self.headers = {"apikey": key}
        if key.startswith("eyJ"):  # le chiavi legacy sono JWT; le nuove sb_secret_* no
            self.headers["Authorization"] = f"Bearer {key}"

    def _url(self, key: str) -> str:
        return f"{self.base}/{quote(key, safe='/')}"

    def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            r = httpx.post(self._url(key), content=data, timeout=60.0,
                           headers={**self.headers, "Content-Type": content_type, "x-upsert": "true"})
        except httpx.HTTPError as exc:
            raise StorageError(f"Archivio documenti non raggiungibile: {exc}") from exc
        if r.status_code >= 300:
            raise StorageError(f"Salvataggio documento non riuscito (HTTP {r.status_code}).")

    def get(self, key: str) -> Optional[bytes]:
        try:
            r = httpx.get(self._url(key), headers=self.headers, timeout=60.0)
        except httpx.HTTPError as exc:
            raise StorageError(f"Archivio documenti non raggiungibile: {exc}") from exc
        if r.status_code in (400, 404):
            return None
        if r.status_code >= 300:
            raise StorageError(f"Lettura documento non riuscita (HTTP {r.status_code}).")
        return r.content


class _LocalStorage:
    """Solo sviluppo/test: nessun dato reale va mai in questa cartella."""
    def __init__(self) -> None:
        self.root = config.LOCAL_DEV_DIR / "documents"

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents:
            raise StorageError("Chiave documento non valida.")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key: str) -> Optional[bytes]:
        p = self._path(key)
        return p.read_bytes() if p.is_file() else None


_backend = None


def _get_backend():
    global _backend
    if _backend is None:
        if config.SUPABASE_URL and config.SUPABASE_SERVICE_ROLE_KEY:
            _backend = _SupabaseStorage()
        elif config.ON_VERCEL:
            raise StorageError("Supabase Storage non configurato.")
        else:
            _backend = _LocalStorage()
    return _backend


def save_document(prefix: str, data: bytes, ext: str, content_type: str = "application/octet-stream") -> str:
    """Salva il documento e restituisce la chiave. Idempotente (stesso contenuto = stessa chiave)."""
    key = build_key(prefix, sha256_bytes(data), ext)
    _get_backend().put(key, data, content_type)
    return key


def load_document(key: str) -> Optional[bytes]:
    return _get_backend().get(key)
