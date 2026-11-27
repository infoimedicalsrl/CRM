from __future__ import annotations
import csv, hashlib, io, json, tempfile, re
from datetime import date
from decimal import Decimal
from decimal import Decimal
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_, select, func
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.utils import get_column_letter
from app.database.database import SessionLocal
from app.database.models import BankMovement, BankStatement, CounterpartyRule
from app.parser.bper_bank_parser import parse_bper_pdf, money
from app.storage import StorageError, save_document

router = APIRouter(prefix="/bank", tags=["Banca"])

def get_db():
    db=SessionLocal()
    try: yield db
    finally: db.close()

class MovementUpdate(BaseModel):
    booking_date: Optional[date] = None
    amount: Optional[Decimal] = None
    category: Optional[str] = None
    counterparty: Optional[str] = None
    counterparty_iban: Optional[str] = None
    description: Optional[str] = None
    duplicate_reviewed: Optional[bool] = None
    possible_duplicate: Optional[bool] = None
    linked_order_id: Optional[int] = None
    linked_sales_invoice_id: Optional[int] = None


def _normalize_counterparty(value: Optional[str]) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())[:255]

@router.post('/import')
async def import_statement(file: UploadFile=File(...), db: Session=Depends(get_db)):
    name = Path(file.filename or 'estratto.pdf').name
    data = await file.read()
    if not data: raise HTTPException(400, 'Il file è vuoto.')
    suffix = Path(name).suffix.lower()
    if suffix not in ('.pdf','.csv'): raise HTTPException(400, 'Formato non supportato: carica un PDF o CSV.')
    parsed = None
    if suffix == '.pdf':
        try:
            with tempfile.NamedTemporaryFile(suffix='.pdf') as tmp:
                tmp.write(data); tmp.flush(); parsed = parse_bper_pdf(tmp.name)
        except Exception as exc:
            raise HTTPException(422, f'Impossibile leggere il PDF con testo selezionabile: {exc}')
    else:
        try:
            text=data.decode('utf-8-sig')
            reader=csv.DictReader(io.StringIO(text), delimiter=';' if text.count(';')>text.count(',') else ',')
            tx=[]
            for row in reader:
                row={str(k or '').strip().casefold(): (v or '').strip() for k,v in row.items()}
                dt=row.get('data contabile') or row.get('data') or row.get('booking_date')
                if not dt: continue
                try: booked=date.fromisoformat(dt) if '-' in dt else date(int(dt[6:10]),int(dt[3:5]),int(dt[:2]))
                except Exception: continue
                value=row.get('data valuta') or row.get('value_date') or dt
                try: valdate=date.fromisoformat(value) if '-' in value else date(int(value[6:10]),int(value[3:5]),int(value[:2]))
                except Exception: valdate=booked
                out_raw = row.get('uscite') or row.get('uscita') or ''
                in_raw = row.get('ingresso') or row.get('entrate') or row.get('entrata') or ''
                if out_raw or in_raw:
                    # In un CSV BPER le due colonne hanno priorità assoluta:
                    # USCITE -> importo negativo; INGRESSO/ENTRATE -> positivo.
                    out_value = abs(money(out_raw)) if out_raw else Decimal('0.00')
                    in_value = abs(money(in_raw)) if in_raw else Decimal('0.00')
                    if out_value and in_value:
                        # Riga ambigua: non scegliere arbitrariamente una colonna.
                        continue
                    if out_value:
                        amount, direction = -out_value, 'uscita'
                    elif in_value:
                        amount, direction = in_value, 'entrata'
                    else:
                        continue
                else:
                    raw=row.get('importo') or row.get('amount')
                    if not raw: continue
                    amount=money(raw)
                    direction='entrata' if amount>0 else 'uscita' if amount<0 else ''
                    if not direction: continue
                tx.append({'booking_date':booked,'value_date':valdate,'amount':amount,'direction':direction,'description':row.get('descrizione') or row.get('causale') or row.get('description') or '', 'counterparty':row.get('intestatario') or row.get('controparte'),'counterparty_iban':row.get('iban controparte') or row.get('iban'),'balance_after':None,'category':row.get('categoria')})
            parsed={'transactions':tx,'opening_balance':None,'closing_balance':None,'warnings':['CSV importato con mappatura delle intestazioni più comuni. Controllare i dati.']}
        except Exception as exc: raise HTTPException(422, f'CSV non leggibile: {exc}')
    txs=parsed['transactions']
    if not txs:
        if suffix == '.pdf':
            diagnostics = parsed.get('diagnostics') or {}
            chars = diagnostics.get('normal_text_chars', 0)
            if chars < 30:
                detail = ('Il PDF non contiene testo sufficiente da estrarre. Potrebbe essere una scansione o un PDF protetto. '
                          'Prova a esportare l’estratto da BPER in CSV oppure in PDF con testo selezionabile.')
            else:
                detail = ('Il PDF contiene testo, ma il formato delle righe non è stato riconosciuto dal parser. '
                          f"Pagine: {parsed.get('pages', 0)}; righe estratte: {diagnostics.get('normal_text_lines', 0)}; "
                          f"righe in layout: {diagnostics.get('layout_text_lines', 0)}. "
                          'Nessun movimento è stato salvato. Esporta da BPER un CSV dei movimenti: il layout specifico del PDF richiede una verifica.')
        else:
            detail = 'Il CSV è stato letto, ma non sono state riconosciute righe di movimento. Controlla intestazioni e colonna importo.'
        raise HTTPException(422, detail)
    # Calcolo del saldo in ordine cronologico; la visualizzazione frontend ordina per data,
    # senza dipendere dall'ordine fisico delle righe nel PDF.
    chronological=sorted(txs,key=lambda t:(t['booking_date'],t['value_date'] or t['booking_date']))
    running=parsed.get('opening_balance')
    balance_by_object={}
    for t in chronological:
        if running is not None:
            running += t['amount']
            balance_by_object[id(t)]=running
            t['balance_after']=running
    ordered=txs
    calculated=running
    difference=(calculated-parsed['closing_balance']) if calculated is not None and parsed.get('closing_balance') is not None else None
    if difference is not None and abs(difference) >= Decimal('0.01'):
        parsed.setdefault('warnings', []).append(
            f"RICONCILIAZIONE NON QUADRATA: saldo iniziale + movimenti = {calculated:.2f} EUR, "
            f"saldo finale PDF = {parsed['closing_balance']:.2f} EUR, differenza = {difference:.2f} EUR. "
            "Possibili movimenti mancanti o assegnazioni errate tra USCITE e INGRESSO."
        )
    elif calculated is None or parsed.get('closing_balance') is None:
        parsed.setdefault('warnings', []).append("Saldo iniziale o finale non individuato: impossibile verificare la completezza dei movimenti.")
    try:
        save_document("bank-statements", data, suffix, "application/pdf" if suffix == ".pdf" else "text/csv")
    except StorageError as exc:
        raise HTTPException(502, str(exc))
    statement=BankStatement(filename=name,opening_balance=parsed.get('opening_balance'),closing_balance=parsed.get('closing_balance'),calculated_closing_balance=calculated,reconciliation_difference=difference,transaction_count=len(txs),warnings=json.dumps(parsed.get('warnings',[]),ensure_ascii=False))
    db.add(statement); db.flush()
    inserted=0; flagged=0; seen_signatures=set(); key_occurrences={}
    for t in ordered:
        amount=Decimal(str(t['amount'])).quantize(Decimal('0.01'))
        direction=(t.get('direction') or '').casefold()
        if direction in ('uscita', 'uscite'):
            amount = -abs(amount)
            t['direction'] = 'uscita'
        elif direction in ('entrata', 'ingresso', 'entrate'):
            amount = abs(amount)
            t['direction'] = 'entrata'
        else:
            t['direction'] = 'entrata' if amount > 0 else 'uscita'
        key=hashlib.sha256(f"{t['booking_date']}|{t.get('value_date')}|{amount}|{t.get('description','').strip()}|{t.get('counterparty_iban') or ''}".encode()).hexdigest()
        existing=db.scalar(select(BankMovement).where(BankMovement.import_key==key))
        possible=existing is not None
        # La chiave logica identifica un possibile duplicato, ma non è la chiave
        # univoca del record: lo stesso movimento può comparire più volte nello
        # stesso estratto (es. due pagamenti uguali). Aggiungiamo statement e
        # occorrenza per rispettare il vincolo UNIQUE senza perdere righe.
        occurrence=key_occurrences.get(key, 0)
        key_occurrences[key]=occurrence+1
        unique_import_key=hashlib.sha256(f'{key}|statement:{statement.id}|occurrence:{occurrence}'.encode()).hexdigest()
        invoice_amounts = t.get('invoice_amounts') or []
        invoice_amount = invoice_amounts[0] if len(invoice_amounts) == 1 else None
        invoice_details = {"invoices": t.get('invoice_details') or [], "amounts": [str(x) for x in invoice_amounts], "fees": [str(x) for x in (t.get('fees') or [])]}
        normalized_counterparty = _normalize_counterparty(t.get('counterparty'))
        saved_rule = db.scalar(select(CounterpartyRule).where(CounterpartyRule.normalized_counterparty == normalized_counterparty)) if normalized_counterparty else None
        category = t.get('category') or (saved_rule.category if saved_rule else None)
        row=BankMovement(booking_date=t['booking_date'],value_date=t.get('value_date'),amount=amount,direction=t.get('direction') or ('entrata' if amount>0 else 'uscita'),description=t.get('description') or '',invoice_amount=invoice_amount,invoice_details=json.dumps(invoice_details,ensure_ascii=False),cig_codes=json.dumps(t.get('cig_codes') or [],ensure_ascii=False),counterparty=t.get('counterparty'),counterparty_iban=t.get('counterparty_iban'),balance_after=t.get('balance_after'),category=category,source_filename=name,import_key=unique_import_key,possible_duplicate=possible)
        # Cerca anche movimenti già presenti con stessa data/importo/causale normalizzata.
        signature=(row.booking_date,row.amount,row.description.strip().casefold())
        similar=db.scalar(select(BankMovement.id).where(BankMovement.booking_date==row.booking_date, BankMovement.amount==row.amount, BankMovement.description==row.description))
        row.possible_duplicate=bool(possible or similar or signature in seen_signatures)
        seen_signatures.add(signature)
        if row.possible_duplicate: flagged+=1
        db.add(row); inserted+=1
    db.commit()
    return {'statement_id':statement.id,'filename':name,'imported':inserted,'flagged_duplicates':flagged,'opening_balance':str(statement.opening_balance) if statement.opening_balance is not None else None,'closing_balance':str(statement.closing_balance) if statement.closing_balance is not None else None,'calculated_closing_balance':str(statement.calculated_closing_balance) if statement.calculated_closing_balance is not None else None,'reconciliation_difference':str(statement.reconciliation_difference) if statement.reconciliation_difference is not None else None,'warnings':parsed.get('warnings',[]),'pages':parsed.get('pages')}

@router.get('/movements')
def list_movements(search:Optional[str]=None, date_from:Optional[date]=None, date_to:Optional[date]=None, direction:Optional[str]=None, category:Optional[str]=None, duplicates_only:bool=False, db:Session=Depends(get_db)):
    q=select(BankMovement)
    if date_from:q=q.where(BankMovement.booking_date>=date_from)
    if date_to:q=q.where(BankMovement.booking_date<=date_to)
    if direction in ('entrata','uscita'):q=q.where(BankMovement.direction==direction)
    if category:q=q.where(BankMovement.category==category)
    if duplicates_only:q=q.where(BankMovement.possible_duplicate.is_(True),BankMovement.duplicate_reviewed.is_(False))
    if search:
        term=f'%{search}%'; q=q.where(or_(BankMovement.counterparty.ilike(term),BankMovement.counterparty_iban.ilike(term),BankMovement.description.ilike(term)))
    rows=list(db.scalars(q.order_by(BankMovement.id.asc())).all())
    return [{'id':r.id,'booking_date':r.booking_date.isoformat(),'value_date':r.value_date.isoformat() if r.value_date else None,'amount':float(r.amount),'direction':r.direction,'description':r.description,'invoice_amount':float(r.invoice_amount) if r.invoice_amount is not None else None,'invoice_details':json.loads(r.invoice_details or '{}'),'cig_codes':json.loads(r.cig_codes or '[]'),'counterparty':r.counterparty,'counterparty_iban':r.counterparty_iban,'balance_after':float(r.balance_after) if r.balance_after is not None else None,'category':r.category,'source_filename':r.source_filename,'possible_duplicate':r.possible_duplicate,'duplicate_reviewed':r.duplicate_reviewed,'linked_order_id':r.linked_order_id,'linked_sales_invoice_id':r.linked_sales_invoice_id} for r in rows]

@router.patch('/movements/{movement_id}')
def update_movement(movement_id:int, payload:MovementUpdate, db:Session=Depends(get_db)):
    row=db.get(BankMovement,movement_id)
    if not row: raise HTTPException(404,'Movimento non trovato.')
    updates = payload.model_dump(exclude_unset=True)
    for key,value in updates.items(): setattr(row,key,value)
    if "category" in updates and row.counterparty and row.category:
        normalized = _normalize_counterparty(row.counterparty)
        if normalized:
            rule = db.scalar(select(CounterpartyRule).where(CounterpartyRule.normalized_counterparty == normalized))
            if rule:
                rule.category = row.category
                rule.display_counterparty = row.counterparty
            else:
                db.add(CounterpartyRule(normalized_counterparty=normalized, display_counterparty=row.counterparty, category=row.category))
    db.commit(); db.refresh(row)
    return {'id':row.id,'updated':True}

@router.get('/summary')
def summary(date_from:Optional[date]=None,date_to:Optional[date]=None,db:Session=Depends(get_db)):
    q=select(BankMovement)
    if date_from:q=q.where(BankMovement.booking_date>=date_from)
    if date_to:q=q.where(BankMovement.booking_date<=date_to)
    rows=list(db.scalars(q).all())
    incoming=sum((r.amount for r in rows if r.amount>0),Decimal('0'))
    outgoing=-sum((r.amount for r in rows if r.amount<0),Decimal('0'))
    categories=sorted({r.category for r in rows if r.category})
    return {'count':len(rows),'income':float(incoming),'expenses':float(outgoing),'net':float(incoming-outgoing),'unreviewed_duplicates':sum(1 for r in rows if r.possible_duplicate and not r.duplicate_reviewed),'categories':categories,'monthly':_monthly(rows)}

def _monthly(rows):
    grouped={}
    for r in rows:
        key=r.booking_date.strftime('%Y-%m'); item=grouped.setdefault(key,{'month':key,'income':0.0,'expenses':0.0,'count':0}); item['count']+=1
        if r.amount>0:item['income']+=float(r.amount)
        else:item['expenses']+=float(-r.amount)
    return sorted(grouped.values(),key=lambda x:x['month'])

@router.get('/statements')
def statements(db:Session=Depends(get_db)):
    return [{'id':s.id,'filename':s.filename,'imported_at':s.imported_at.isoformat(),'opening_balance':float(s.opening_balance) if s.opening_balance is not None else None,'closing_balance':float(s.closing_balance) if s.closing_balance is not None else None,'calculated_closing_balance':float(s.calculated_closing_balance) if s.calculated_closing_balance is not None else None,'reconciliation_difference':float(s.reconciliation_difference) if s.reconciliation_difference is not None else None,'transaction_count':s.transaction_count,'warnings':json.loads(s.warnings or '[]')} for s in db.scalars(select(BankStatement).order_by(BankStatement.id.desc())).all()]

@router.get('/counterparty-rules')
def counterparty_rules(db: Session = Depends(get_db)):
    return [{'id': r.id, 'counterparty': r.display_counterparty, 'category': r.category} for r in db.scalars(select(CounterpartyRule).order_by(CounterpartyRule.display_counterparty)).all()]


@router.get('/export.xlsx')
def export_xlsx(db:Session=Depends(get_db)):
    rows=list(db.scalars(select(BankMovement).order_by(BankMovement.booking_date, BankMovement.id)).all())
    wb=Workbook(); ws=wb.active; ws.title='Movimenti bancari'
    ws.append(['Data contabile','Data valuta','Importo EUR','Direzione','Causale','Controparte','IBAN controparte','Saldo dopo movimento','Categoria','Possibile duplicato','Duplicato verificato','File origine','Ordine collegato'])
    for r in rows: ws.append([r.booking_date.isoformat(),r.value_date.isoformat() if r.value_date else '',float(r.amount),r.direction,r.description,r.counterparty or '',r.counterparty_iban or '',float(r.balance_after) if r.balance_after is not None else '',r.category or '', 'Sì' if r.possible_duplicate else 'No','Sì' if r.duplicate_reviewed else 'No',r.source_filename,r.linked_order_id or ''])
    ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
    for col in ws.columns:
        width=min(max(max(len(str(c.value or '')) for c in col)+2,12),55); ws.column_dimensions[get_column_letter(col[0].column)].width=width
    out=io.BytesIO(); wb.save(out); out.seek(0)
    return StreamingResponse(out,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="movimenti_bancari.xlsx"'})
