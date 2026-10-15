from __future__ import annotations

import hashlib
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from pypdf import PdfReader
from openpyxl import load_workbook
import unicodedata

from app.storage import StorageError, save_document
from app.database.database import SessionLocal
from app.database.models import PurchaseInvoice, BankMovement

router = APIRouter(prefix="/purchase-invoices", tags=["Fatture di acquisto"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def first_text(root: ET.Element, name: str) -> Optional[str]:
    for element in root.iter():
        if local_name(element.tag) == name and element.text and element.text.strip():
            return element.text.strip()
    return None


def decimal_value(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(value.strip().replace(" ", "").replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def parse_fatturapa(data: bytes) -> dict:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise HTTPException(422, f"XML non valido: {exc}")

    # CedentePrestatore è il fornitore nella fattura ricevuta (non CessionarioCommittente).
    supplier = next((element for element in root.iter() if local_name(element.tag) == "CedentePrestatore"), None)
    supplier_name = None
    supplier_vat = None
    supplier_cf = None
    if supplier is not None:
        for element in supplier.iter():
            tag = local_name(element.tag)
            value = (element.text or "").strip()
            if tag == "Denominazione" and value:
                supplier_name = value
                break
        if not supplier_name:
            name = next(((e.text or "").strip() for e in supplier.iter() if local_name(e.tag) == "Nome" and (e.text or "").strip()), "")
            surname = next(((e.text or "").strip() for e in supplier.iter() if local_name(e.tag) == "Cognome" and (e.text or "").strip()), "")
            supplier_name = " ".join(part for part in (name, surname) if part) or None
        supplier_vat = next(((e.text or "").strip() for e in supplier.iter() if local_name(e.tag) == "IdCodice" and (e.text or "").strip()), None)
        supplier_cf = next(((e.text or "").strip() for e in supplier.iter() if local_name(e.tag) == "CodiceFiscale" and (e.text or "").strip()), None)

    number = first_text(root, "Numero")
    date_text = first_text(root, "Data")
    try:
        issue_date = date.fromisoformat(date_text) if date_text else None
    except ValueError:
        issue_date = None
    gross = decimal_value(first_text(root, "ImportoTotaleDocumento"))
    due_date_text = first_text(root, "DataScadenzaPagamento")
    try:
        due_date = date.fromisoformat(due_date_text) if due_date_text else None
    except ValueError:
        due_date = None
    supplier_address = supplier_city = supplier_province = supplier_postal_code = supplier_country = None
    if supplier is not None:
        sede = next((element for element in supplier.iter() if local_name(element.tag) == "Sede"), None)
        if sede is not None:
            def sede_text(tag):
                return next(((e.text or "").strip() for e in sede.iter() if local_name(e.tag) == tag and (e.text or "").strip()), None)
            supplier_address = sede_text("Indirizzo")
            supplier_city = sede_text("Comune")
            supplier_province = sede_text("Provincia")
            supplier_postal_code = sede_text("CAP")
            supplier_country = sede_text("Nazione")
    description = next(((e.text or "").strip() for e in root.iter() if local_name(e.tag) == "Descrizione" and (e.text or "").strip()), None)
    net_values = [decimal_value(e.text) for e in root.iter() if local_name(e.tag) == "ImponibileImporto" and e.text]
    vat_values = [decimal_value(e.text) for e in root.iter() if local_name(e.tag) == "Imposta" and e.text]
    net = sum((v for v in net_values if v is not None), Decimal("0.00"))
    vat = sum((v for v in vat_values if v is not None), Decimal("0.00"))
    if gross is None and (net or vat):
        gross = net + vat
    missing = [label for label, value in (("numero fattura", number), ("data fattura", issue_date), ("fornitore", supplier_name), ("totale documento", gross)) if value is None]
    if missing:
        raise HTTPException(422, "XML letto, ma mancano campi obbligatori: " + ", ".join(missing) + ".")
    currency = first_text(root, "Divisa") or "EUR"
    return {"invoice_number": number, "issue_date": issue_date, "supplier_name": supplier_name, "supplier_vat": supplier_vat, "supplier_cf": supplier_cf, "currency": currency, "original_currency": currency, "due_date": due_date, "supplier_address": supplier_address, "supplier_city": supplier_city, "supplier_province": supplier_province, "supplier_postal_code": supplier_postal_code, "supplier_country": supplier_country, "description": description, "net_amount": net, "vat_amount": vat, "gross_amount": gross}


def parse_pdf(data: bytes) -> dict:
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(data)
            tmp.flush()
            reader = PdfReader(tmp.name)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise HTTPException(422, f"PDF non leggibile: {exc}")
    if len(text.strip()) < 30:
        raise HTTPException(422, "Il PDF non contiene testo estraibile. Per le scansioni usa un XML FatturaPA o inserisci prima una versione testuale del documento.")
    flat = re.sub(r"[ \t]+", " ", text)
    number_match = re.search(r"(?i)(?:numero\s+fattura|fattura\s*(?:n(?:\.|°|º)?|numero)|n(?:\.|°|º)\s*fattura)\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{0,39})", flat)
    date_match = re.search(r"(?i)(?:data\s+(?:fattura|documento)|data|\bdel)\s*[:#\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{4}-\d{2}-\d{2})", flat)
    total_match = re.search(r"(?i)(?:totale\s+(?:documento|fattura|da\s+pagare)|importo\s+totale)\s*[:€ ]*([0-9][0-9. ]*,[0-9]{2}|[0-9]+\.[0-9]{2})", flat)
    supplier_match = re.search(r"(?im)(?:fornitore|cedente(?:\s+prestatore)?|dati\s+fornitore)\s*[:\-]?\s*([^\n]{2,160})", text)
    vat_match = re.search(r"(?i)(?:P\.?\s*IVA|Partita\s+IVA)\s*[:#]?\s*(IT\s*)?([0-9]{11})", flat)
    issue_date = None
    if date_match:
        raw = date_match.group(1)
        try:
            issue_date = date.fromisoformat(raw) if raw.startswith("20") else date(*(int(x) for x in raw.replace("/", ".").replace("-", ".").split(".")[::-1]))
        except ValueError:
            pass
    gross = None
    if total_match:
        raw = total_match.group(1).strip().replace(" ", "")
        if "," in raw:
            raw = raw.replace(".", "").replace(",", ".")
        gross = decimal_value(raw)
    if not number_match or not issue_date or not supplier_match or gross is None:
        raise HTTPException(422, "Non riesco a identificare con sicurezza numero, data, fornitore e totale nel PDF. Nessun dato è stato salvato; per un'importazione affidabile usa l'XML FatturaPA.")
    supplier_vat = ((vat_match.group(1) or "") + vat_match.group(2)) if vat_match else None
    return {"invoice_number": number_match.group(1).strip(".,;"), "issue_date": issue_date, "supplier_name": supplier_match.group(1).strip()[:255], "supplier_vat": supplier_vat, "supplier_cf": None, "currency": "EUR", "net_amount": Decimal("0.00"), "vat_amount": Decimal("0.00"), "gross_amount": gross}


def _header_key(value: object) -> str:
    raw = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]", "", raw)


def _excel_date(value: object) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        try:
            import xlrd
            return xlrd.xldate_as_datetime(value, 0).date()
        except Exception:
            return None
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _excel_decimal(value: object) -> Optional[Decimal]:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except InvalidOperation:
            return None
    raw = str(value).strip().replace("€", "").replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    return decimal_value(raw)


def parse_excel(data: bytes, suffix: str) -> dict:
    try:
        if suffix in {".xlsx", ".xlsm"}:
            from io import BytesIO
            workbook = load_workbook(BytesIO(data), read_only=True, data_only=True)
            sheet = workbook.active
            values = list(sheet.iter_rows(values_only=True))
            workbook.close()
        else:
            from io import BytesIO
            import xlrd
            workbook = xlrd.open_workbook(file_contents=data)
            sheet = workbook.sheet_by_index(0)
            values = []
            for row_idx in range(sheet.nrows):
                converted = []
                for col_idx in range(sheet.ncols):
                    cell = sheet.cell(row_idx, col_idx)
                    value = cell.value
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        try:
                            value = xlrd.xldate.xldate_as_datetime(value, workbook.datemode)
                        except (ValueError, OverflowError):
                            value = None
                    elif cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK):
                        value = None
                    converted.append(value)
                values.append(tuple(converted))
            workbook.release_resources()
    except Exception as exc:
        raise HTTPException(422, f"File Excel non leggibile: {exc}")
    if not values:
        raise HTTPException(422, "Il file Excel non contiene righe.")
    # Cerca l'intestazione nelle prime 15 righe per tollerare titoli introduttivi.
    aliases = {
        "invoice_number": {"fatturaricevuta", "numerofattura", "numerodocumento", "fatturanumero", "numero", "nrfattura", "nacquisto", "numeroacquisto", "nracquisto"},
        "issue_date": {"data", "datafattura", "datadocumento"},
        "due_date": {"proxscadenza", "prossimascadenza", "scadenza", "datascadenza"},
        "supplier_name": {"fornitore", "ragionesociale", "denominazione"},
        "supplier_vat": {"piva", "partitaiva", "partitaivafornitore", "vat"},
        "supplier_cf": {"cf", "codicefiscale", "codicefiscalefornitore"},
        "supplier_address": {"indirizzo"},
        "supplier_city": {"comune", "citta"},
        "supplier_province": {"provincia", "prov"},
        "supplier_postal_code": {"cap", "codicepostale"},
        "supplier_country": {"paese", "nazione"},
        "description": {"descrizione"},
        "original_currency": {"valutaorig", "valutaoriginale", "valuta"},
        "net_amount": {"imponibile", "imponibiletotale", "totaleimponibile"},
        "vat_amount": {"iva", "importoiva", "totaleiva"},
    }
    header_index = None
    mapping = {}
    for idx, row in enumerate(values[:15]):
        keys = [_header_key(cell) for cell in row]
        found = {}
        for field, options in aliases.items():
            for col, key in enumerate(keys):
                if key in options:
                    found[field] = col
                    break
        if {"invoice_number", "issue_date", "supplier_name", "net_amount", "vat_amount"}.issubset(found):
            header_index, mapping = idx, found
            break
    if header_index is None:
        raise HTTPException(422, "Non trovo le colonne necessarie nel file Excel. Servono almeno # Fattura ricevuta, Data, Fornitore, Imponibile e IVA.")
    def cell(row, key):
        col = mapping.get(key)
        return row[col] if col is not None and col < len(row) else None
    imported = []
    for row in values[header_index + 1:]:
        if not any(str(v or "").strip() for v in row):
            continue
        number = str(cell(row, "invoice_number") or "").strip()
        supplier_name = str(cell(row, "supplier_name") or "").strip()
        issue_date = _excel_date(cell(row, "issue_date"))
        net = _excel_decimal(cell(row, "net_amount"))
        vat = _excel_decimal(cell(row, "vat_amount"))
        if not number and not supplier_name:
            continue
        missing = [label for label, value in (("numero fattura", number), ("data", issue_date), ("fornitore", supplier_name), ("imponibile", net), ("IVA", vat)) if value is None or value == ""]
        if missing:
            raise HTTPException(422, f"Riga Excel {len(imported) + header_index + 2}: campi mancanti o non validi: {', '.join(missing)}.")
        net = net or Decimal("0.00")
        vat = vat or Decimal("0.00")
        currency = str(cell(row, "original_currency") or "EUR").strip().upper()[:8] or "EUR"
        imported.append({"invoice_number": number, "issue_date": issue_date, "supplier_name": supplier_name[:255], "supplier_vat": str(cell(row, "supplier_vat") or "").strip() or None, "supplier_cf": str(cell(row, "supplier_cf") or "").strip() or None, "currency": currency, "original_currency": currency, "due_date": _excel_date(cell(row, "due_date")), "supplier_address": str(cell(row, "supplier_address") or "").strip() or None, "supplier_city": str(cell(row, "supplier_city") or "").strip() or None, "supplier_province": str(cell(row, "supplier_province") or "").strip() or None, "supplier_postal_code": str(cell(row, "supplier_postal_code") or "").strip() or None, "supplier_country": str(cell(row, "supplier_country") or "").strip() or None, "description": str(cell(row, "description") or "").strip() or None, "net_amount": net, "vat_amount": vat, "gross_amount": net + vat})
    if not imported:
        raise HTTPException(422, "Il file Excel non contiene fatture valide sotto l'intestazione.")
    return {"invoices": imported} if len(imported) > 1 else imported[0]


def _normalize_party(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii").lower())


def matching_bank_movements(row: PurchaseInvoice, db: Session) -> list[BankMovement]:
    """Suggerisce pagamenti solo con importo coincidente e controparte/casuale compatibile."""
    supplier = _normalize_party(row.supplier_name)
    supplier_ascii = unicodedata.normalize("NFKD", row.supplier_name or "").encode("ascii", "ignore").decode("ascii").lower()
    legal_suffixes = {"srl", "srls", "spa", "sapa", "snc", "sas", "societa", "soc", "co", "ltd", "limited", "inc"}
    tokens = [_normalize_party(token) for token in re.findall(r"[a-z0-9]+", supplier_ascii) if len(token) >= 5 and token not in legal_suffixes]
    candidates = list(db.scalars(select(BankMovement).where(BankMovement.direction == "uscita").order_by(BankMovement.booking_date.desc())).all())
    amount_party_matches = []
    invoice_ref_matches = []
    invoice_number = _normalize_party(str(row.invoice_number or ""))
    # Un riferimento è considerato valido anche se nella causale compaiono slash,
    # trattini o spazi diversi rispetto al numero registrato nella fattura.
    invoice_compact = re.sub(r"[^a-z0-9]", "", invoice_number)
    for movement in candidates:
        if abs(abs(Decimal(movement.amount)) - abs(Decimal(row.gross_amount))) > Decimal("0.02"):
            continue
        raw_text = f"{movement.counterparty or ''} {movement.description or ''}"
        text = _normalize_party(raw_text)
        party_match = bool(supplier and (supplier in text or any(token in text for token in tokens)))
        if not party_match:
            continue
        amount_party_matches.append(movement)
        compact_text = re.sub(r"[^a-z0-9]", "", text)
        if invoice_compact and invoice_compact in compact_text:
            invoice_ref_matches.append(movement)
    # Se più fatture dello stesso fornitore hanno lo stesso importo, si conferma
    # il collegamento solo se la causale identifica il numero fattura.
    if invoice_ref_matches:
        return invoice_ref_matches
    if len(amount_party_matches) == 1:
        return amount_party_matches
    return []


def serialize(row: PurchaseInvoice, db: Session | None = None) -> dict:
    matches = matching_bank_movements(row, db) if db is not None else []
    return {"id": row.id, "invoice_number": row.invoice_number, "issue_date": row.issue_date.isoformat(), "supplier_name": row.supplier_name, "supplier_vat": row.supplier_vat, "supplier_cf": row.supplier_cf, "currency": row.currency, "original_currency": row.original_currency or row.currency, "due_date": row.due_date.isoformat() if row.due_date else None, "supplier_address": row.supplier_address, "supplier_city": row.supplier_city, "supplier_province": row.supplier_province, "supplier_postal_code": row.supplier_postal_code, "supplier_country": row.supplier_country, "description": row.description, "net_amount": float(row.net_amount), "vat_amount": float(row.vat_amount), "gross_amount": float(row.gross_amount), "source_filename": row.source_filename, "source_format": row.source_format, "status": "PAGATA" if matches else "NON PAGATA", "reconciliation_status": "RICONCILIATA" if matches else "DA RICONCILIARE", "linked_movements": [{"id": m.id, "booking_date": m.booking_date.isoformat(), "amount": float(m.amount), "counterparty": m.counterparty, "description": m.description} for m in matches]}


@router.get("")
def list_purchase_invoices(search: Optional[str] = None, supplier: Optional[str] = None, db: Session = Depends(get_db)):
    filters = []
    if search and search.strip():
        term = f"%{search.strip()}%"
        filters.append(or_(PurchaseInvoice.invoice_number.ilike(term), PurchaseInvoice.supplier_name.ilike(term), PurchaseInvoice.supplier_vat.ilike(term), PurchaseInvoice.supplier_cf.ilike(term)))
    if supplier and supplier.strip():
        filters.append(PurchaseInvoice.supplier_name == supplier.strip())
    query = select(PurchaseInvoice).where(*filters).order_by(PurchaseInvoice.issue_date.desc(), PurchaseInvoice.id.desc())
    rows = list(db.scalars(query).all())
    total = db.scalar(select(func.coalesce(func.sum(PurchaseInvoice.gross_amount), 0)).where(*filters)) or Decimal("0.00")
    suppliers = list(db.scalars(select(PurchaseInvoice.supplier_name).distinct().order_by(PurchaseInvoice.supplier_name)).all())
    return {"rows": [serialize(row, db) for row in rows], "total_purchases": float(total), "suppliers": suppliers, "count": len(rows)}


@router.get("/{invoice_id}")
def get_purchase_invoice(invoice_id: int, db: Session = Depends(get_db)):
    row = db.get(PurchaseInvoice, invoice_id)
    if not row:
        raise HTTPException(404, "Fattura di acquisto non trovata.")
    return serialize(row, db)


@router.patch("/{invoice_id}")
def update_purchase_invoice(invoice_id: int, payload: dict, db: Session = Depends(get_db)):
    row = db.get(PurchaseInvoice, invoice_id)
    if not row:
        raise HTTPException(404, "Fattura di acquisto non trovata.")
    allowed = {"invoice_number", "issue_date", "supplier_name", "supplier_vat", "supplier_cf", "currency", "original_currency", "due_date", "supplier_address", "supplier_city", "supplier_province", "supplier_postal_code", "supplier_country", "description", "net_amount", "vat_amount", "gross_amount"}
    changes = {key: value for key, value in payload.items() if key in allowed}
    for key, value in changes.items():
        if key in {"issue_date", "due_date"}:
            if value in (None, ""):
                value = None
            elif isinstance(value, str):
                try:
                    value = date.fromisoformat(value[:10])
                except ValueError:
                    raise HTTPException(422, f"Data non valida per il campo {key}.")
        if key in {"net_amount", "vat_amount", "gross_amount"}:
            try:
                value = Decimal(str(value or 0)).quantize(Decimal("0.01"))
            except InvalidOperation:
                raise HTTPException(422, f"Importo non valido per il campo {key}.")
        setattr(row, key, value)
    row.gross_amount = Decimal(row.net_amount or 0) + Decimal(row.vat_amount or 0)
    db.commit()
    db.refresh(row)
    return serialize(row, db)


@router.post("/import")
async def import_purchase_invoice(file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename = Path(file.filename or "fattura-acquisto").name
    suffix = Path(filename).suffix.lower()
    if suffix not in {".xml", ".xls", ".xlsx"}:
        raise HTTPException(415, "Formato non supportato. Carica un file Excel (.xls/.xlsx) oppure un XML FatturaPA.")
    data = await file.read()
    if not data:
        raise HTTPException(422, "Il file è vuoto.")
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(PurchaseInvoice).where(PurchaseInvoice.source_hash == digest))
    if existing:
        raise HTTPException(409, f"Questo documento è già stato importato come fattura {existing.invoice_number}.")
    parsed_result = parse_fatturapa(data) if suffix == ".xml" else parse_excel(data, suffix)
    parsed_rows = parsed_result.get("invoices", [parsed_result]) if isinstance(parsed_result, dict) else [parsed_result]
    existing_rows = []
    for parsed in parsed_rows:
        duplicate = db.scalar(select(PurchaseInvoice.id).where(PurchaseInvoice.invoice_number == parsed["invoice_number"], PurchaseInvoice.issue_date == parsed["issue_date"], PurchaseInvoice.supplier_name == parsed["supplier_name"]))
        if duplicate:
            existing_rows.append(parsed["invoice_number"])
    if existing_rows:
        raise HTTPException(409, "Fatture già presenti (nessun dato importato): " + ", ".join(existing_rows[:10]))
    try:
        save_document("purchase-invoices", data, suffix, "application/octet-stream")
    except StorageError as exc:
        raise HTTPException(502, str(exc)) from exc
    rows = [PurchaseInvoice(**parsed, source_filename=filename, source_hash=digest if len(parsed_rows) == 1 else hashlib.sha256(f"{digest}:{idx}".encode()).hexdigest(), source_format=suffix[1:].upper()) for idx, parsed in enumerate(parsed_rows)]
    db.add_all(rows)
    try:
        db.commit()
        for row in rows:
            db.refresh(row)
    except Exception:
        db.rollback()
        raise
    return serialize(rows[0], db) if len(rows) == 1 else {"imported_count": len(rows), "invoices": [serialize(row, db) for row in rows]}
