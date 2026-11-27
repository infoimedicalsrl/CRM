from __future__ import annotations
import csv, hashlib, io, json, re, unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from pypdf import PdfReader
from app.storage import StorageError, load_document, save_document
from app.database.database import SessionLocal
from app.database.models import CustomerStatementImport, CustomerStatementRow, SalesInvoice

router = APIRouter(prefix="/customer-statements", tags=["Estratto conto cliente"])
CURRENT_YEAR = date.today().year

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", text)

def dec(value: object) -> Optional[Decimal]:
    if value is None: return None
    s = str(value).strip().replace("€", "").replace("EUR", "").replace(" ", "")
    if not s or s in {"-", "—", "n.d."}: return None
    if "," in s and "." in s: s = s.replace(".", "").replace(",", ".")
    elif "," in s: s = s.replace(",", ".")
    try: return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation: return None

def parse_date(value: object) -> Optional[date]:
    """Parse dates both as standalone values and embedded in document references."""
    s = str(value or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y", "%d-%b-%y", "%d-%b-%Y", "%d-%B-%y", "%d-%B-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    # Date embedded in document descriptions, e.g. "52/PA del 11-08-2025".
    m = re.search(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})(?!\d)", s)
    if m:
        try:
            year = int(m.group(3))
            if year < 100:
                year += 2000 if year < 70 else 1900
            return date(year, int(m.group(2)), int(m.group(1)))
        except ValueError:
            pass
    # Ordinativi often use English month abbreviations, e.g. "827 del 18-FEB-25".
    months = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "MAG": 5, "JUN": 6, "GIU": 6, "JUL": 7, "LUG": 7, "AUG": 8, "AGO": 8, "SEP": 9, "SET": 9, "OCT": 10, "OTT": 10, "NOV": 11, "DEC": 12, "DIC": 12}
    m = re.search(r"(?<!\d)(\d{1,2})[- /]([A-Za-zÀ-ÿ]{3,})[- /](\d{2,4})(?!\d)", s, re.I)
    if m:
        month = months.get(m.group(2)[:3].upper())
        year = int(m.group(3))
        if year < 100:
            year += 2000 if year < 70 else 1900
        if month:
            try:
                return date(year, month, int(m.group(1)))
            except ValueError:
                pass
    m = re.search(r"(?<!\d)(20\d{2})-(\d{2})-(\d{2})(?!\d)", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass
    return None

def matching_invoices(invoice_index: dict[str, list[SalesInvoice]], document_reference: object, statement_date: Optional[date]) -> list[SalesInvoice]:
    """Match document number only within the statement row's year; use the invoice date when present."""
    doc = str(document_reference or "").strip()
    if not doc or statement_date is None:
        return []
    number = re.split(r"\s+del\s+", doc, maxsplit=1, flags=re.I)[0].strip()
    candidates = invoice_index.get(norm(number), [])
    # Bank/customer-statement date and invoice issue date must belong to the same year.
    candidates = [candidate for candidate in candidates if candidate.issue_date and candidate.issue_date.year == statement_date.year]
    document_date = parse_date(doc)
    if document_date:
        if document_date.year != statement_date.year:
            return []
        # If the reference embeds the invoice date, require an exact date match.
        candidates = [candidate for candidate in candidates if candidate.issue_date == document_date]
    return candidates

ALIASES = {
 "office": ["ufficiotipodocumento", "ufficiotipo", "ufficio", "tipodocumento"],
 "doc": ["doc", "documento", "numerodocumento", "numerodoc", "documenton"],
 "order": ["ordinativo", "numeroordinativo", "ordinativon"],
 "amount": ["importo", "importodocumento"],
 "vat": ["ivaritenute", "ivaritenuta", "ritenute", "iva"],
 "paid": ["pagato", "importopagato"],
 "balance": ["saldo", "residuo"],
 "liquidated": ["liquidato", "data liquidazione", "dataliquidazione", "data", "datapagamento"],
 "status": ["stato", "statodocumento", "statopagamento"]
}
def canonical_row(raw: dict) -> dict:
    by_norm = {norm(k): str(v or "").strip() for k,v in raw.items()}
    out = {}
    for key, aliases in ALIASES.items():
        out[key] = next((by_norm[norm(a)] for a in aliases if norm(a) in by_norm and by_norm[norm(a)] != ""), None)
    # Support common multi-word variants in exported reports.
    if not out.get("doc"):
        out["doc"] = next((v for k,v in by_norm.items() if k.startswith("doc") and v), None)
    # In this export, "Liquidato" is an amount (e.g. 0 or 1464), not a date.
    # Use the payment order date when present; otherwise fall back to the date
    # embedded in the document reference. This prevents every row being dropped
    # merely because Liquidato contains a numeric amount.
    out["row_date"] = parse_date(out.get("order")) or parse_date(out.get("doc"))
    return out

def read_csv_rows(data: bytes) -> list[dict]:
    text = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try: text = data.decode(enc); break
        except UnicodeDecodeError: continue
    if text is None: raise HTTPException(422, "Non riesco a leggere la codifica del CSV.")
    sample = text[:8192]
    try: dialect = csv.Sniffer().sniff(sample, delimiters=";,\t|")
    except csv.Error: dialect = csv.excel; dialect.delimiter = ";" if sample.count(";") >= sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames: raise HTTPException(422, "Il CSV non contiene intestazioni di colonna.")
    return [canonical_row(row) for row in reader if any(str(v or "").strip() for v in row.values())]

def read_pdf_rows(data: bytes) -> list[dict]:
    try:
        reader = PdfReader(io.BytesIO(data))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception as exc: raise HTTPException(422, f"Impossibile leggere il PDF: {exc}")
    if not text.strip(): raise HTTPException(422, "Il PDF sembra una scansione o non contiene testo selezionabile. Per questo file serve OCR, non incluso in questa versione.")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    header_idx = next((i for i,line in enumerate(lines) if "doc" in norm(line) and ("ordinativo" in norm(line) or "pagato" in norm(line))), None)
    if header_idx is None: raise HTTPException(422, "Non trovo nel PDF l'intestazione della tabella. Esporta il documento in CSV per un'importazione affidabile.")
    header_line = lines[header_idx]
    if "\t" in header_line: headers = [x.strip() for x in header_line.split("\t")]
    elif re.search(r"\s{2,}", header_line): headers = [x.strip() for x in re.split(r"\s{2,}", header_line)]
    elif ";" in header_line: headers = [x.strip() for x in header_line.split(";")]
    else: raise HTTPException(422, "Le colonne del PDF non sono distinguibili con sicurezza. Usa il CSV esportato dallo stesso gestionale.")
    parsed=[]
    for line in lines[header_idx+1:]:
        parts = [x.strip() for x in (line.split("\t") if "\t" in line else re.split(r"\s{2,}", line) if re.search(r"\s{2,}", line) else line.split(";"))]
        if len(parts) != len(headers): continue
        parsed.append(canonical_row(dict(zip(headers, parts))))
    if not parsed: raise HTTPException(422, "Non sono riuscito a ricostruire le righe della tabella PDF. Usa il CSV per evitare abbinamenti errati.")
    return parsed

def serialize_import(imp: CustomerStatementImport, db: Session, include_rows: bool = False):
    result = {"id":imp.id,"filename":imp.filename,"file_format":imp.file_format,"imported_at":imp.imported_at.isoformat(),"source_year":imp.source_year,"rows_imported":imp.rows_imported,"rows_ignored_other_year":imp.rows_ignored_other_year,"rows_unmatched":imp.rows_unmatched,"rows_matched":imp.rows_matched}
    if include_rows:
        rows = db.scalars(select(CustomerStatementRow).where(CustomerStatementRow.import_id==imp.id).order_by(CustomerStatementRow.row_date, CustomerStatementRow.id)).all()
        result["rows"] = [{"id":r.id,"office_document_type":r.office_document_type,"document_number":r.document_number,"order_number":r.order_number,"amount":float(r.amount) if r.amount is not None else None,"vat_withholdings":float(r.vat_withholdings) if r.vat_withholdings is not None else None,"paid":float(r.paid) if r.paid is not None else None,"balance":float(r.balance) if r.balance is not None else None,"liquidated":r.liquidated,"row_date":r.row_date.isoformat() if r.row_date else None,"status":r.status,"match_status":r.match_status,"match_note":r.match_note,"invoice_id":r.invoice_id,"invoice_number":db.get(SalesInvoice,r.invoice_id).invoice_number if r.invoice_id and db.get(SalesInvoice,r.invoice_id) else None} for r in rows]
    return result

@router.get("")
def list_imports(db: Session = Depends(get_db)):
    return [serialize_import(x,db) for x in db.scalars(select(CustomerStatementImport).order_by(CustomerStatementImport.imported_at.desc())).all()]

@router.post("/import")
async def import_statement(file: UploadFile = File(...), db: Session = Depends(get_db)):
    name = Path(file.filename or "estratto-conto").name
    suffix = Path(name).suffix.lower()
    if suffix not in (".csv", ".pdf"): raise HTTPException(400,"Carica un file CSV o PDF.")
    data = await file.read()
    if not data: raise HTTPException(400,"Il file è vuoto.")
    digest = hashlib.sha256(data).hexdigest()
    if db.scalar(select(CustomerStatementImport.id).where(CustomerStatementImport.file_hash==digest)):
        raise HTTPException(409,"Questo estratto conto è già stato importato.")
    parsed = read_csv_rows(data) if suffix==".csv" else read_pdf_rows(data)
    try:
        stored_key = save_document("customer-statements", data, suffix, "application/pdf" if suffix==".pdf" else "text/csv")
    except StorageError as exc:
        raise HTTPException(502, str(exc)) from exc
    imp = CustomerStatementImport(filename=name,file_hash=digest,file_format=suffix[1:].upper(),stored_path=stored_key,source_year=CURRENT_YEAR)
    db.add(imp); db.flush()
    ignored=0; matched=0; unmatched=0; imported=0
    # Le fatture non sono limitate all'anno corrente: gli estratti possono
    # contenere ordinativi/liquidazioni di anni precedenti.
    invoices = db.scalars(select(SalesInvoice)).all()
    invoice_index={}
    for inv in invoices: invoice_index.setdefault(norm(inv.invoice_number), []).append(inv)
    for p in parsed:
        d=p.get("row_date")
        # Ignora solo le righe senza una data interpretabile; non scartare
        # automaticamente righe valide solo perché appartengono a un anno passato.
        if not d:
            ignored += 1; continue
        doc=(p.get("doc") or "").strip()
        if not doc: ignored += 1; continue
        # Numero + anno della riga estratto conto; se presente, anche la data esatta della fattura.
        matches = matching_invoices(invoice_index, doc, d)
        invoice=matches[0] if len(matches)==1 else None
        status=(p.get("status") or "").strip()
        paid=dec(p.get("paid")); gross=invoice.gross_amount if invoice else None
        status_norm=norm(status)
        negative_status=any(x in status_norm for x in ("daliquidare", "dapagare", "nonpagato", "annullato", "sospeso", "respinto"))
        status_ok=not negative_status and bool(re.search(r"pagat|incassat|liquidat|completat|quietanzat",status,re.I))
        amount_ok=invoice is not None and paid is not None and abs(Decimal(paid)-Decimal(gross)) <= Decimal("0.01")
        if invoice and amount_ok and status_ok:
            match_status="ABBINATA_INCASSATA"; note="Documento e importo pagato corrispondono; stato compatibile con pagamento completato."; invoice.status="INCASSATA"; matched += 1
        elif len(matches)>1:
            match_status="DA_VERIFICARE"; note="Più fatture dello stesso anno hanno questo numero; abbinamento automatico sospeso per evitare un collegamento errato."; unmatched += 1
        elif invoice:
            match_status="DA_VERIFICARE"; note="Numero documento trovato, ma stato o importo pagato non confermano un incasso completo."; unmatched += 1
        else:
            match_status="NON_ABBINATA"; note="Nessuna fattura con numero corrispondente e data nello stesso anno della riga dell'estratto conto."; unmatched += 1
        row=CustomerStatementRow(import_id=imp.id,invoice_id=invoice.id if invoice else None,office_document_type=p.get("office"),document_number=doc,order_number=p.get("order"),amount=dec(p.get("amount")),vat_withholdings=dec(p.get("vat")),paid=paid,balance=dec(p.get("balance")),liquidated=p.get("liquidated"),row_date=d,status=status,match_status=match_status,match_note=note,raw_data=json.dumps(p,ensure_ascii=False,default=str))
        db.add(row); imported += 1
    imp.rows_imported=imported; imp.rows_ignored_other_year=ignored; imp.rows_unmatched=unmatched; imp.rows_matched=matched
    db.commit(); db.refresh(imp)
    return serialize_import(imp,db,True)


@router.post("/rematch")
def rematch_existing_statements(db: Session = Depends(get_db)):
    """Re-run invoice matching for previously imported statement rows."""
    invoices = db.scalars(select(SalesInvoice)).all()
    invoice_index = {}
    for inv in invoices:
        invoice_index.setdefault(norm(inv.invoice_number), []).append(inv)
    imports = db.scalars(select(CustomerStatementImport)).all()
    rows = db.scalars(select(CustomerStatementRow)).all()
    matched = 0
    unmatched = 0
    for row in rows:
        doc = (row.document_number or "").strip()
        candidates = matching_invoices(invoice_index, doc, row.row_date)
        invoice = candidates[0] if len(candidates) == 1 else None
        row.invoice_id = invoice.id if invoice else None
        status_norm = norm(row.status or "")
        negative_status = any(x in status_norm for x in ("daliquidare", "dapagare", "nonpagato", "annullato", "sospeso", "respinto"))
        status_ok = not negative_status and bool(re.search(r"pagat|incassat|liquidat|completat|quietanzat", row.status or "", re.I))
        paid = Decimal(row.paid) if row.paid is not None else None
        gross = Decimal(invoice.gross_amount) if invoice else None
        amount_ok = invoice is not None and paid is not None and gross is not None and abs(paid-gross) <= Decimal("0.01")
        if invoice and amount_ok and status_ok:
            row.match_status = "ABBINATA_INCASSATA"
            row.match_note = "Documento e importo pagato corrispondono; stato compatibile con pagamento completato."
            invoice.status = "INCASSATA"
            matched += 1
        elif len(candidates) > 1:
            row.match_status = "DA_VERIFICARE"
            row.match_note = "Più fatture dello stesso anno hanno questo numero; abbinamento automatico sospeso per evitare un collegamento errato."
            unmatched += 1
        elif invoice:
            row.match_status = "DA_VERIFICARE"
            row.match_note = "Numero documento trovato, ma stato o importo pagato non confermano un incasso completo."
            unmatched += 1
        else:
            row.match_status = "NON_ABBINATA"
            row.match_note = "Nessuna fattura con numero corrispondente e data nello stesso anno della riga dell'estratto conto."
            unmatched += 1
    for imp in imports:
        own = [r for r in rows if r.import_id == imp.id]
        imp.rows_matched = sum(r.match_status == "ABBINATA_INCASSATA" for r in own)
        imp.rows_unmatched = sum(r.match_status != "ABBINATA_INCASSATA" for r in own)
    db.commit()
    return {"rows_processed": len(rows), "rows_matched": matched, "rows_unmatched": unmatched}

@router.get("/{import_id}")
def get_import(import_id:int, db:Session=Depends(get_db)):
    imp=db.get(CustomerStatementImport,import_id)
    if not imp: raise HTTPException(404,"Estratto conto non trovato.")
    return serialize_import(imp,db,True)

@router.get("/{import_id}/file")
def get_original_file(import_id:int, db:Session=Depends(get_db)):
    imp=db.get(CustomerStatementImport,import_id)
    if not imp: raise HTTPException(404,"Estratto conto non trovato.")
    try:
        data=load_document(imp.stored_path)
    except StorageError as exc:
        raise HTTPException(502,str(exc)) from exc
    if data is None: raise HTTPException(404,"File originale non trovato nell'archivio documenti.")
    media="application/pdf" if imp.file_format=="PDF" else "text/csv; charset=utf-8"
    filename=Path(imp.filename).name.replace('"',"")
    return Response(content=data,media_type=media,headers={"Content-Disposition":f'inline; filename="{filename}"'})
