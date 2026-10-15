from pathlib import Path
import sys

from app.database.database import SessionLocal, init_db
from app.importer.importer import import_xml


def main():
    if len(sys.argv) != 2:
        print("Uso: python import_file.py /percorso/ordine.xml")
        raise SystemExit(2)
    path = Path(sys.argv[1])
    init_db()
    with SessionLocal() as db:
        order, warnings = import_xml(path, db)
    print(f"Importato ordine {order.order_number} (id={order.id})")
    for warning in warnings:
        print(f"ATTENZIONE: {warning}")


if __name__ == "__main__":
    main()
