from __future__ import annotations

import hashlib
import json
import re
import tempfile
import io
import xml.etree.ElementTree as ET
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from pypdf import PdfReader
from openpyxl import load_workbook

from app.database.database import SessionLocal
from app.storage import StorageError, save_document
from app.database.models import BankMovement, SalesInvoice, CustomerStatementRow, Customer, DeliveryNote, Order

router = APIRouter(prefix="/sales-invoices", tags=["Fatture di vendita"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def first_text(root: ET.Element, name: str) -> Optional[str]:
    for el in root.iter():
        if local_name(el.tag) == name and el.text and el.text.strip():
            return el.text.strip()
    return None


def decimal_value(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(value.replace(" ", "").replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def parse_fatturapa(data: bytes) -> dict:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise HTTPException(422, f"XML non valido: {exc}")
    number = first_text(root, "Numero")
    date_text = first_text(root, "Data")
    gross = decimal_value(first_text(root, "ImportoTotaleDocumento"))
    customer_name = None
    customer_vat = None
    for el in root.iter():
        if local_name(el.tag) == "CessionarioCommittente":
            for child in el.iter():
                tag = local_name(child.tag)
                if tag in ("Denominazione", "Nome", "Cognome") and child.text and child.text.strip():
                    if tag == "Denominazione":
                        customer_name = child.text.strip()
                        break
                    customer_name = " ".join(x for x in [customer_name, child.text.strip()] if x)
            for child in el.iter():
                if local_name(child.tag) == "IdCodice" and child.text and child.text.strip():
                    customer_vat = child.text.strip()
                    break
            break
    net_values = [decimal_value(x.text) for x in root.iter() if local_name(x.tag) == "ImponibileImporto" and x.text]
    vat_values = [decimal_value(x.text) for x in root.iter() if local_name(x.tag) == "Imposta" and x.text]
    net = sum((x for x in net_values if x is not None), Decimal("0.00"))
    vat = sum((x for x in vat_values if x is not None), Decimal("0.00"))
    if not gross and net + vat > 0:
        gross = net + vat
    try:
        issue_date = date.fromisoformat(date_text) if date_text else None
    except ValueError:
        issue_date = None
    missing = []
    if not number: missing.append("numero fattura")
    if not issue_date: missing.append("data fattura")
    if not customer_name: missing.append("cliente/cessionario")
    if gross is None: missing.append("totale documento")
    if missing:
        raise HTTPException(422, "XML letto, ma mancano campi obbligatori: " + ", ".join(missing) + ".")
    return {"invoice_number": number, "issue_date": issue_date, "customer_name": customer_name, "customer_vat": customer_vat, "net_amount": net, "vat_amount": vat, "gross_amount": gross, "currency": first_text(root, "Divisa") or "EUR", "warnings": []}


def parse_pdf(data: bytes) -> dict:
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(data); tmp.flush()
            reader = PdfReader(tmp.name)
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc:
        raise HTTPException(422, f"PDF non leggibile: {exc}")
    if len(text.strip()) < 30:
        raise HTTPException(422, "Il PDF non contiene testo estraibile (probabile scansione). Usa un PDF testuale oppure inserisci i dati manualmente nella sezione Fatture di vendita.")
    flat = re.sub(r"[ \t]+", " ", text)
    number_patterns = [r"(?i)(?:numero\s+fattura|fattura\s*(?:n(?:\.|°|º)?|numero))\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{0,39})", r"(?i)\bN(?:\.|°|º)\s*Fattura\s*[:#\-]?\s*([A-Z0-9][A-Z0-9./_-]{0,39})"]
    number = next((m.group(1).strip(".,;") for pat in number_patterns if (m := re.search(pat, flat))), None)
    date_match = re.search(r"(?i)(?:data\s+(?:fattura|documento)|data|\bdel)\s*[:#\-]?\s*(\d{1,2}[./-]\d{1,2}[./-]\d{4}|\d{4}-\d{2}-\d{2})", flat)
    issue_date = None
    if date_match:
        raw = date_match.group(1)
        try:
            issue_date = date.fromisoformat(raw) if re.match(r"^\d{4}-", raw) else date(*(int(x) for x in raw.replace("/", ".").replace("-", ".").split(".")[::-1]))
        except ValueError:
            pass
    def amount_for(patterns):
        for pat in patterns:
            m = re.search(pat, flat, re.I)
            if m:
                raw = m.group(1).replace(".", "").replace(",", ".") if "," in m.group(1) else m.group(1)
                val = decimal_value(raw)
                if val is not None: return val
        return None
    gross = amount_for([r"(?:totale\s+(?:documento|fattura|da\s+pagare)|importo\s+totale)\s*[:€ ]*([0-9][0-9. ]*,[0-9]{2})", r"(?:totale\s+(?:documento|fattura|da\s+pagare)|importo\s+totale)\s*[:€ ]*([0-9]+\.[0-9]{2})"])
    net = amount_for([r"imponibile\s*(?:totale)?\s*[:€ ]*([0-9][0-9. ]*,[0-9]{2})"])
    vat = amount_for([r"(?:totale\s+)?IVA\s*[:€ ]*([0-9][0-9. ]*,[0-9]{2})"])
    customer_name = None
    customer_vat = None
    vat_match = re.search(r"(?i)(?:P\.?\s*IVA|Partita\s+IVA)\s*[:#]?\s*(IT\s*)?([0-9]{11})", flat)
    if vat_match: customer_vat = (vat_match.group(1) or "") + vat_match.group(2)
    # Best-effort PDF extraction only: do not invent a customer name from arbitrary lines.
    customer_match = re.search(r"(?im)(?:cliente|cessionario(?:/committente)?|destinatario)\s*[:\-]?\s*([^\n]{2,120})", text)
    if customer_match: customer_name = customer_match.group(1).strip()
    missing = [label for label, value in [("numero fattura", number), ("data fattura", issue_date), ("cliente", customer_name), ("totale documento", gross)] if value is None]
    if missing:
        raise HTTPException(422, "Non riesco a identificare con sicurezza " + ", ".join(missing) + " nel PDF. Nessun dato è stato salvato: inserisci i dati manualmente nella sezione Fatture di vendita oppure usa l'XML FatturaPA.")
    warnings = ["Dati estratti automaticamente da PDF testuale: verifica i campi prima di usarli per la riconciliazione."]
    return {"invoice_number": number, "issue_date": issue_date, "customer_name": customer_name, "customer_vat": customer_vat, "net_amount": net or Decimal("0.00"), "vat_amount": vat or Decimal("0.00"), "gross_amount": gross, "currency": "EUR", "warnings": warnings}


def serialize(invoice: SalesInvoice, linked_movements: list[BankMovement] | None = None, statement_rows: list[CustomerStatementRow] | None = None):
    return {"statement_reconciliations": [{"date": r.row_date.isoformat() if r.row_date else r.liquidated, "order_number": r.order_number, "document_number": r.document_number, "paid": float(r.paid) if r.paid is not None else None, "status": r.status} for r in (statement_rows or [])], "id": invoice.id, "invoice_number": invoice.invoice_number, "issue_date": invoice.issue_date.isoformat(), "customer_name": invoice.customer_name, "customer_vat": invoice.customer_vat, "customer_cf": invoice.customer_cf, "currency": invoice.currency, "net_amount": float(invoice.net_amount), "vat_amount": float(invoice.vat_amount), "gross_amount": float(invoice.gross_amount), "status": invoice.status, "source_filename": invoice.source_filename, "source_format": invoice.source_format, "warnings": json.loads(invoice.extraction_warnings or "[]"), "linked_movements": [{"id": m.id, "booking_date": m.booking_date.isoformat(), "amount": float(m.amount), "counterparty": m.counterparty, "description": m.description} for m in (linked_movements or [])]}


@router.get("")
def list_sales_invoices(search: Optional[str] = None, status: Optional[str] = None, db: Session = Depends(get_db)):
    q = select(SalesInvoice)
    if search:
        term = f"%{search.strip()}%"
        q = q.where(or_(SalesInvoice.invoice_number.ilike(term), SalesInvoice.customer_name.ilike(term), SalesInvoice.customer_vat.ilike(term)))
    if status: q = q.where(SalesInvoice.status == status)
    rows = list(db.scalars(q.order_by(SalesInvoice.issue_date.desc(), SalesInvoice.id.desc())).all())
    return [serialize(x, list(db.scalars(select(BankMovement).where(BankMovement.linked_sales_invoice_id == x.id)).all()), list(db.scalars(select(CustomerStatementRow).where(CustomerStatementRow.invoice_id == x.id).order_by(CustomerStatementRow.row_date.desc())).all())) for x in rows]


class SalesInvoiceUpdate(BaseModel):
    invoice_number: Optional[str] = Field(None, min_length=1, max_length=128)
    issue_date: Optional[date] = None
    customer_name: Optional[str] = Field(None, min_length=1, max_length=255)
    customer_vat: Optional[str] = None
    customer_cf: Optional[str] = None
    currency: Optional[str] = Field(None, min_length=1, max_length=8)
    net_amount: Optional[Decimal] = Field(None, ge=0)
    vat_amount: Optional[Decimal] = Field(None, ge=0)
    gross_amount: Optional[Decimal] = Field(None, ge=0)


@router.get("/{invoice_id}")
def get_sales_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(SalesInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Fattura non trovata.")
    movements = list(db.scalars(select(BankMovement).where(BankMovement.linked_sales_invoice_id == invoice_id).order_by(BankMovement.booking_date.desc())).all())
    statement_rows = list(db.scalars(select(CustomerStatementRow).where(CustomerStatementRow.invoice_id == invoice_id).order_by(CustomerStatementRow.row_date.desc())).all())
    result = serialize(invoice, movements, statement_rows)
    customer = None
    if invoice.customer_vat:
        vat = invoice.customer_vat.replace("IT", "").replace(" ", "")
        customer = db.scalar(select(Customer).where(Customer.vat_number.ilike(f"%{vat}%"))) if vat else None
    if customer is None:
        customer = db.scalar(select(Customer).where(Customer.name.ilike(invoice.customer_name.strip())))
    ddt_rows = []
    if customer:
        ddt_rows = db.scalars(select(DeliveryNote).where(DeliveryNote.customer_id == customer.id).order_by(DeliveryNote.ddt_date.desc()).limit(100)).all()
    result["linked_ddts"] = [{"id": d.id, "ddt_number": d.ddt_number, "ddt_date": d.ddt_date.isoformat(), "source_filename": d.source_filename, "status": d.status, "order_reference": d.order_reference, "order_number": d.order.order_number if d.order else None} for d in ddt_rows]
    result["source_document_available"] = bool(invoice.source_filename and invoice.source_filename != "Inserimento manuale")
    return result


@router.patch("/{invoice_id}")
def update_sales_invoice(invoice_id: int, payload: SalesInvoiceUpdate, db: Session = Depends(get_db)):
    invoice = db.get(SalesInvoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Fattura non trovata.")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        if isinstance(value, str):
            value = value.strip()
        setattr(invoice, key, value)
    if not invoice.invoice_number or not invoice.customer_name:
        raise HTTPException(422, "Numero fattura e cliente sono obbligatori.")
    if invoice.gross_amount < 0 or invoice.net_amount < 0 or invoice.vat_amount < 0:
        raise HTTPException(422, "Gli importi non possono essere negativi.")
    movements = list(db.scalars(select(BankMovement).where(BankMovement.linked_sales_invoice_id == invoice_id)).all())
    paid_total = sum((abs(Decimal(m.amount)) for m in movements), Decimal("0.00"))
    invoice.status = "INCASSATA" if paid_total >= Decimal(invoice.gross_amount) - Decimal("0.01") else ("INCASSO_PARZIALE" if paid_total > 0 else "DA_INCASSARE")
    db.commit(); db.refresh(invoice)
    statement_rows = list(db.scalars(select(CustomerStatementRow).where(CustomerStatementRow.invoice_id == invoice_id)).all())
    return serialize(invoice, movements, statement_rows)


@router.post("/import")
async def import_sales_invoice(file: UploadFile = File(...), db: Session = Depends(get_db)):
    name = Path(file.filename or "fattura").name
    data = await file.read()
    if not data: raise HTTPException(400, "Il file è vuoto.")
    suffix = Path(name).suffix.lower()
    if suffix not in (".xml", ".pdf"): raise HTTPException(400, "Formato non supportato: carica una fattura in PDF o XML FatturaPA.")
    digest = hashlib.sha256(data).hexdigest()
    if db.scalar(select(SalesInvoice.id).where(SalesInvoice.source_hash == digest)):
        raise HTTPException(409, "Questa fattura è già stata importata.")
    parsed = parse_fatturapa(data) if suffix == ".xml" else parse_pdf(data)
    duplicate = db.scalar(select(SalesInvoice.id).where(SalesInvoice.invoice_number == parsed["invoice_number"], SalesInvoice.customer_name == parsed["customer_name"], SalesInvoice.issue_date == parsed["issue_date"]))
    if duplicate: raise HTTPException(409, "Esiste già una fattura con lo stesso numero, cliente e data.")
    invoice = SalesInvoice(invoice_number=parsed["invoice_number"], issue_date=parsed["issue_date"], customer_name=parsed["customer_name"], customer_vat=parsed.get("customer_vat"), customer_cf=parsed.get("customer_cf"), currency=parsed.get("currency") or "EUR", net_amount=parsed.get("net_amount") or Decimal("0.00"), vat_amount=parsed.get("vat_amount") or Decimal("0.00"), gross_amount=parsed["gross_amount"], status="DA_INCASSARE", source_filename=name, source_hash=digest, source_format=suffix[1:].upper(), extraction_warnings=json.dumps(parsed.get("warnings", []), ensure_ascii=False))
    try:
        save_document("sales-invoices", data, suffix, "application/xml" if suffix == ".xml" else "application/pdf")
    except StorageError as exc:
        raise HTTPException(502, str(exc)) from exc
    db.add(invoice); db.commit(); db.refresh(invoice)
    return serialize(invoice)


# Importazione massiva da Excel: le intestazioni sono riconosciute anche con
# piccole variazioni (accenti, spazi, asterischi e maiuscole).
def _header_key(value) -> str:
    import unicodedata
    text_value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "", text_value.lower())


def _excel_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    raw = str(value).strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def _excel_amount(value):
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(Decimal("0.01"))
    raw = str(value).replace("EUR", "").replace("€", "").replace("\u00a0", " ").strip()
    raw = raw.replace(" ", "")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


@router.post("/import-excel")
async def import_sales_invoices_excel(file: UploadFile = File(...), db: Session = Depends(get_db)):
    name = Path(file.filename or "fatture.xlsx").name
    suffix = Path(name).suffix.lower()
    if suffix not in (".xlsx", ".xlsm", ".xls"):
        raise HTTPException(400, "Formato non supportato: carica un file Excel .xls, .xlsx o .xlsm.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Il file Excel è vuoto.")
    digest = hashlib.sha256(data).hexdigest()
    try:
        workbook = None
        legacy_book = None
        if suffix == ".xls":
            # Il formato .xls è il vecchio formato binario Excel (BIFF): openpyxl non lo supporta.
            import xlrd
            legacy_book = xlrd.open_workbook(file_contents=data, on_demand=True)
            sheet = legacy_book.sheet_by_index(0)
            converted_rows = []
            for row_idx in range(sheet.nrows):
                converted = []
                for col_idx in range(sheet.ncols):
                    cell = sheet.cell(row_idx, col_idx)
                    value = cell.value
                    if cell.ctype == xlrd.XL_CELL_DATE:
                        try:
                            value = xlrd.xldate.xldate_as_datetime(value, legacy_book.datemode)
                        except (ValueError, OverflowError):
                            value = None
                    elif cell.ctype == xlrd.XL_CELL_EMPTY or cell.ctype == xlrd.XL_CELL_BLANK:
                        value = None
                    converted.append(value)
                converted_rows.append(tuple(converted))
            rows = iter(converted_rows[1:])
            header_row = converted_rows[0] if converted_rows else None
        else:
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            sheet = workbook.active
            rows = sheet.iter_rows(values_only=True)
            header_row = next(rows, None)
        if not header_row:
            raise HTTPException(422, "Il foglio Excel non contiene intestazioni.")
        headers = {_header_key(v): i for i, v in enumerate(header_row) if v is not None}
        aliases = {
            "number": ("fatturaemessa", "numerofattura", "fattura", "numero", "nfattura"),
            "date": ("data", "datafattura", "dataemissione"),
            "customer": ("cliente", "clientedestinatario", "denominazionecliente"),
            "vat": ("piva", "partitaiva", "vat", "vatnumber"),
            "cf": ("cf", "codicefiscale", "codicefiscalecliente"),
            "net": ("imponibile", "imponibiletotale", "importoimponibile"),
            "vat_amount": ("iva", "importoiva", "ivafattura", "imposta"),
        }
        columns = {}
        for field, candidates in aliases.items():
            columns[field] = next((headers[k] for k in candidates if k in headers), None)
        required = {"number": "# Fattura emessa", "date": "Data", "customer": "Cliente", "net": "Imponibile", "vat_amount": "IVA"}
        missing = [label for key, label in required.items() if columns[key] is None]
        if missing:
            raise HTTPException(422, "Intestazioni Excel mancanti o non riconosciute: " + ", ".join(missing) + ". Controlla la prima riga del foglio.")
        inserted = 0
        duplicates = 0
        rejected = []
        seen_keys = set()
        for excel_row, values in enumerate(rows, start=2):
            if not values or not any(v is not None and str(v).strip() for v in values):
                continue
            def val(field):
                idx = columns.get(field)
                return values[idx] if idx is not None and idx < len(values) else None
            number = str(val("number") or "").strip()
            customer_name = str(val("customer") or "").strip()
            issue_date = _excel_date(val("date"))
            net = _excel_amount(val("net"))
            vat_amount = _excel_amount(val("vat_amount"))
            customer_vat = str(val("vat") or "").strip() or None
            customer_cf = str(val("cf") or "").strip() or None
            problems = []
            if not number: problems.append("numero fattura mancante")
            if not issue_date: problems.append("data non valida")
            if not customer_name: problems.append("cliente mancante")
            if net is None: problems.append("imponibile non valido")
            if vat_amount is None: problems.append("IVA non valida")
            if problems:
                rejected.append({"row": excel_row, "invoice_number": number or "—", "reason": ", ".join(problems)})
                continue
            key = (number.casefold(), issue_date.isoformat(), customer_name.casefold())
            if key in seen_keys or db.scalar(select(SalesInvoice.id).where(SalesInvoice.invoice_number == number, SalesInvoice.issue_date == issue_date, SalesInvoice.customer_name == customer_name)):
                duplicates += 1
                seen_keys.add(key)
                continue
            seen_keys.add(key)
            gross = (net + vat_amount).quantize(Decimal("0.01"))
            row_hash = hashlib.sha256(f"excel|{digest}|{excel_row}|{number}|{issue_date}|{customer_name}|{net}|{vat_amount}".encode()).hexdigest()
            db.add(SalesInvoice(invoice_number=number, issue_date=issue_date, customer_name=customer_name[:255], customer_vat=customer_vat, customer_cf=customer_cf, currency="EUR", net_amount=net, vat_amount=vat_amount, gross_amount=gross, status="DA_INCASSARE", source_filename=name, source_hash=row_hash, source_format="EXCEL", extraction_warnings="[]"))
            inserted += 1
        db.commit()
        save_document("sales-invoices-excel", data, suffix, "application/octet-stream")
        if workbook is not None:
            workbook.close()
        if legacy_book is not None:
            legacy_book.release_resources()
        return {"filename": name, "inserted": inserted, "duplicates": duplicates, "rejected_count": len(rejected), "rejected": rejected[:100], "message": f"Importazione Excel completata: {inserted} fatture inserite, {duplicates} già presenti ignorate, {len(rejected)} righe da correggere."}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, f"Non riesco a leggere il file Excel: {exc}") from exc


class ManualInvoice(BaseModel):
    invoice_number: str = Field(min_length=1, max_length=128)
    issue_date: date
    customer_name: str = Field(min_length=1, max_length=255)
    customer_vat: Optional[str] = None
    customer_cf: Optional[str] = None
    net_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    vat_amount: Decimal = Field(default=Decimal("0.00"), ge=0)
    gross_amount: Decimal = Field(ge=0)
    currency: str = "EUR"


@router.post("/manual")
def create_manual_invoice(payload: ManualInvoice, db: Session = Depends(get_db)):
    digest = hashlib.sha256(f"manual|{payload.invoice_number}|{payload.issue_date}|{payload.customer_name}|{payload.gross_amount}".encode()).hexdigest()
    if db.scalar(select(SalesInvoice.id).where(SalesInvoice.source_hash == digest)) or db.scalar(select(SalesInvoice.id).where(SalesInvoice.invoice_number == payload.invoice_number.strip(), SalesInvoice.customer_name == payload.customer_name.strip(), SalesInvoice.issue_date == payload.issue_date)):
        raise HTTPException(409, "Questa fattura manuale è già stata inserita.")
    row = SalesInvoice(invoice_number=payload.invoice_number.strip(), issue_date=payload.issue_date, customer_name=payload.customer_name.strip(), customer_vat=payload.customer_vat, customer_cf=payload.customer_cf, currency=payload.currency, net_amount=payload.net_amount, vat_amount=payload.vat_amount, gross_amount=payload.gross_amount, status="DA_INCASSARE", source_filename="Inserimento manuale", source_hash=digest, source_format="MANUALE", extraction_warnings="[]")
    db.add(row); db.commit(); db.refresh(row)
    return serialize(row)


class LinkMovement(BaseModel):
    movement_id: int


@router.post("/{invoice_id}/link")
def link_movement(invoice_id: int, payload: LinkMovement, db: Session = Depends(get_db)):
    invoice = db.get(SalesInvoice, invoice_id)
    movement = db.get(BankMovement, payload.movement_id)
    if not invoice: raise HTTPException(404, "Fattura non trovata.")
    if not movement: raise HTTPException(404, "Movimento bancario non trovato.")
    if movement.direction != "entrata": raise HTTPException(422, "Puoi collegare una fattura di vendita solo a un movimento in entrata.")
    if movement.linked_sales_invoice_id not in (None, invoice_id): raise HTTPException(409, "Il movimento è già collegato a un'altra fattura.")
    movement.linked_sales_invoice_id = invoice_id
    db.flush()
    linked_rows = list(db.scalars(select(BankMovement).where(BankMovement.linked_sales_invoice_id == invoice_id)).all())
    paid_total = sum((abs(Decimal(x.amount)) for x in linked_rows), Decimal("0.00"))
    invoice.status = "INCASSATA" if paid_total >= Decimal(invoice.gross_amount) - Decimal("0.01") else "INCASSO_PARZIALE"
    db.commit()
    return {"linked": True, "invoice_id": invoice_id, "movement_id": movement.id, "status": invoice.status}


@router.delete("/{invoice_id}/link/{movement_id}")
def unlink_movement(invoice_id: int, movement_id: int, db: Session = Depends(get_db)):
    invoice = db.get(SalesInvoice, invoice_id); movement = db.get(BankMovement, movement_id)
    if not invoice or not movement: raise HTTPException(404, "Fattura o movimento non trovato.")
    if movement.linked_sales_invoice_id == invoice_id: movement.linked_sales_invoice_id = None
    remaining_rows = list(db.scalars(select(BankMovement).where(BankMovement.linked_sales_invoice_id == invoice_id)).all())
    paid_total = sum((abs(Decimal(x.amount)) for x in remaining_rows), Decimal("0.00"))
    invoice.status = "INCASSATA" if paid_total >= Decimal(invoice.gross_amount) - Decimal("0.01") else ("INCASSO_PARZIALE" if paid_total > 0 else "DA_INCASSARE")
    db.commit()
    return {"linked": False}


@router.get("/{invoice_id}/candidates")
def invoice_candidates(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(SalesInvoice, invoice_id)
    if not invoice: raise HTTPException(404, "Fattura non trovata.")
    rows = list(db.scalars(select(BankMovement).where(BankMovement.direction == "entrata", BankMovement.linked_sales_invoice_id.is_(None), BankMovement.booking_date >= invoice.issue_date).order_by(BankMovement.booking_date.desc())).all())
    customer = (invoice.customer_name or "").casefold()
    vat = (invoice.customer_vat or "").replace("IT", "").replace(" ", "")
    candidates = []
    for m in rows:
        amount_match = abs(abs(Decimal(m.amount)) - Decimal(invoice.gross_amount)) < Decimal("0.02")
        name = (m.counterparty or "").casefold()
        desc = (m.description or "").casefold()
        vat_match = bool(vat and vat in re.sub(r"\s", "", (m.counterparty or "") + " " + (m.description or "")))
        name_match = bool(customer and (customer in name or name in customer or customer in desc))
        if amount_match or vat_match or name_match:
            candidates.append({"id": m.id, "booking_date": m.booking_date.isoformat(), "amount": float(m.amount), "counterparty": m.counterparty, "description": m.description, "amount_match": amount_match, "counterparty_match": vat_match or name_match})
    return candidates[:30]
