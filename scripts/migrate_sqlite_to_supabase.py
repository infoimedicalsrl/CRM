#!/usr/bin/env python3
"""Copia i dati dal vecchio database SQLite locale a Supabase (PostgreSQL) e, facoltativamente,
carica i documenti originali (XML ordini, PDF DDT) su Supabase Storage.

Uso (dalla radice del repository, con .env configurato):
    python scripts/migrate_sqlite_to_supabase.py --sqlite /percorso/peppol.sqlite [--documents-dir /percorso/ordini --documents-dir /percorso/ddt]

Richiede che le migrazioni in supabase/migrations siano gia' state eseguite. Rifiuta di
procedere se il database di destinazione contiene gia' dati (usa --force per saltare il controllo).
"""
import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine, func, select, text  # noqa: E402

from app import config  # noqa: E402
from app.database import models  # noqa: E402,F401
from app.database.database import Base  # noqa: E402
from app.storage import build_key, save_document  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True, help="file SQLite di origine")
    ap.add_argument("--documents-dir", action="append", default=[], help="cartella con XML/PDF originali (ripetibile)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not config.IS_REMOTE_DATABASE:
        print("DATABASE_URL non punta a PostgreSQL/Supabase: configura il file .env.")
        return 2
    src_path = Path(args.sqlite).expanduser()
    if not src_path.is_file():
        print(f"File non trovato: {src_path}")
        return 2

    src = create_engine(f"sqlite:///{src_path}")
    dst = create_engine(config.DATABASE_URL)
    tables = list(Base.metadata.sorted_tables)

    with dst.begin() as d:
        if not args.force:
            for t in tables:
                if d.execute(select(func.count()).select_from(t)).scalar():
                    print(f"La tabella {t.name} di destinazione non e' vuota. Interrompo (usa --force per ignorare).")
                    return 3

    with src.connect() as s, dst.begin() as d:
        existing = set(__import__("sqlalchemy").inspect(src).get_table_names())
        for t in tables:
            if t.name not in existing:
                print(f"{t.name:32s} (assente nel SQLite, saltata)")
                continue
            cols = [c.name for c in t.columns if c.name in {x["name"] for x in __import__("sqlalchemy").inspect(src).get_columns(t.name)}]
            rows = [dict(r._mapping) for r in s.execute(select(*[t.c[c] for c in cols]))]
            if rows:
                for i in range(0, len(rows), 500):
                    d.execute(t.insert(), rows[i:i + 500])
            print(f"{t.name:32s} {len(rows):6d} righe")
        # riallinea le sequenze degli id
        for t in tables:
            if "id" in t.c:
                d.execute(text(f"select setval(pg_get_serial_sequence('{t.name}','id'), coalesce((select max(id) from {t.name}),0)+1, false)"))

    if args.documents_dir:
        wanted = {}
        with dst.connect() as d:
            for prefix, table, ext in (("orders", "orders", ".xml"), ("ddt", "delivery_notes", ".pdf")):
                for (h,) in d.execute(text(f"select source_hash from {table}")):
                    wanted[h] = (prefix, ext)
        sent = 0
        for folder in args.documents_dir:
            for f in Path(folder).expanduser().rglob("*"):
                if not f.is_file() or f.suffix.lower() not in (".xml", ".pdf"):
                    continue
                data = f.read_bytes()
                h = hashlib.sha256(data).hexdigest()
                if h in wanted:
                    prefix, ext = wanted.pop(h)
                    save_document(prefix, data, ext, "application/pdf" if ext == ".pdf" else "application/xml")
                    sent += 1
        print(f"Documenti caricati su Storage: {sent}; senza file originale trovato: {len(wanted)}")
    print("Migrazione completata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
