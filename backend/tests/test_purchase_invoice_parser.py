from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.purchase_invoice_routes import parse_fatturapa


def test_parse_purchase_invoice_uses_supplier_not_customer():
    xml = b'''<?xml version="1.0" encoding="UTF-8"?>
    <p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
      <FatturaElettronicaHeader>
        <CedentePrestatore><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>01234567890</IdCodice></IdFiscaleIVA><Anagrafica><Denominazione>Fornitore Esempio Srl</Denominazione></Anagrafica></DatiAnagrafici></CedentePrestatore>
        <CessionarioCommittente><DatiAnagrafici><Anagrafica><Denominazione>La Mia Azienda</Denominazione></Anagrafica></DatiAnagrafici></CessionarioCommittente>
      </FatturaElettronicaHeader>
      <FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><Divisa>EUR</Divisa><Data>2026-10-12</Data><Numero>ACQ-42</Numero><ImportoTotaleDocumento>122.00</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
      <DatiBeniServizi><DatiRiepilogo><ImponibileImporto>100.00</ImponibileImporto><Imposta>22.00</Imposta></DatiRiepilogo></DatiBeniServizi></FatturaElettronicaBody>
    </p:FatturaElettronica>'''
    parsed = parse_fatturapa(xml)
    assert parsed["supplier_name"] == "Fornitore Esempio Srl"
    assert parsed["supplier_vat"] == "01234567890"
    assert parsed["invoice_number"] == "ACQ-42"
    assert parsed["issue_date"].isoformat() == "2026-10-12"
    assert parsed["net_amount"] == Decimal("100.00")
    assert parsed["vat_amount"] == Decimal("22.00")
    assert parsed["gross_amount"] == Decimal("122.00")


def test_parse_purchase_invoice_rejects_missing_supplier():
    xml = b'''<FatturaElettronica><FatturaElettronicaHeader/><FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><Data>2026-10-12</Data><Numero>1</Numero><ImportoTotaleDocumento>10.00</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali></FatturaElettronicaBody></FatturaElettronica>'''
    with pytest.raises(HTTPException) as exc:
        parse_fatturapa(xml)
    assert exc.value.status_code == 422
    assert "fornitore" in exc.value.detail


def test_total_purchases_changes_with_supplier_filter():
    from datetime import date
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.database.database import Base
    from app.database.models import PurchaseInvoice
    from app.api.purchase_invoice_routes import list_purchase_invoices

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add_all([
                PurchaseInvoice(invoice_number="A-1", issue_date=date(2026, 1, 1), supplier_name="Alfa Srl", supplier_vat=None, currency="EUR", net_amount=Decimal("100"), vat_amount=Decimal("22"), gross_amount=Decimal("122"), source_filename="a.xml", source_hash="a" * 64, source_format="XML"),
                PurchaseInvoice(invoice_number="A-2", issue_date=date(2026, 1, 2), supplier_name="Alfa Srl", supplier_vat=None, currency="EUR", net_amount=Decimal("50"), vat_amount=Decimal("11"), gross_amount=Decimal("61"), source_filename="b.xml", source_hash="b" * 64, source_format="XML"),
                PurchaseInvoice(invoice_number="B-1", issue_date=date(2026, 1, 3), supplier_name="Beta Spa", supplier_vat=None, currency="EUR", net_amount=Decimal("200"), vat_amount=Decimal("44"), gross_amount=Decimal("244"), source_filename="c.xml", source_hash="c" * 64, source_format="XML"),
            ])
            db.commit()
            all_invoices = list_purchase_invoices(db=db)
            alfa_invoices = list_purchase_invoices(supplier="Alfa Srl", db=db)
            alfa_search = list_purchase_invoices(search="A-2", db=db)
            assert all_invoices["total_purchases"] == 427.0
            assert alfa_invoices["total_purchases"] == 183.0
            assert alfa_invoices["count"] == 2
            assert alfa_search["total_purchases"] == 61.0
            assert alfa_search["count"] == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_parse_excel_purchase_invoice():
    from io import BytesIO
    from openpyxl import Workbook
    from app.api.purchase_invoice_routes import parse_excel

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["# Fattura ricevuta", "Data", "Fornitore", "P.IVA", "CF", "Imponibile", "IVA"])
    sheet.append(["FA-2026-01", "13/10/2026", "Fornitore Alfa Srl", "IT12345678901", "12345678901", 100, 22])
    buffer = BytesIO()
    workbook.save(buffer)
    result = parse_excel(buffer.getvalue(), ".xlsx")
    assert result["invoice_number"] == "FA-2026-01"
    assert result["supplier_name"] == "Fornitore Alfa Srl"
    assert result["supplier_vat"] == "IT12345678901"
    assert result["supplier_cf"] == "12345678901"
    assert result["net_amount"] == Decimal("100.00")
    assert result["vat_amount"] == Decimal("22.00")
    assert result["gross_amount"] == Decimal("122.00")


def test_parse_excel_purchase_invoice_extended_columns():
    from io import BytesIO
    from openpyxl import Workbook
    from app.api.purchase_invoice_routes import parse_excel

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Data", "Prox scadenza", "Nr. Fattura", "Fornitore", "Partita IVA", "Codice fiscale", "Indirizzo", "Comune", "Provincia", "CAP", "Paese", "Descrizione", "Valuta orig.", "Imponibile", "IVA"])
    sheet.append(["12/10/2026", "30/10/2026", "ACQ-99", "Eurosets Srl", "IT12345678901", "12345678901", "Via Roma 1", "Catania", "CT", "95100", "IT", "Materiale tecnico", "EUR", 100, 22])
    buffer = BytesIO()
    workbook.save(buffer)
    result = parse_excel(buffer.getvalue(), ".xlsx")
    assert result["invoice_number"] == "ACQ-99"
    assert result["supplier_name"] == "Eurosets Srl"
    assert result["due_date"].isoformat() == "2026-10-30"
    assert result["supplier_address"] == "Via Roma 1"
    assert result["supplier_city"] == "Catania"
    assert result["supplier_province"] == "CT"
    assert result["supplier_postal_code"] == "95100"
    assert result["supplier_country"] == "IT"
    assert result["description"] == "Materiale tecnico"
    assert result["original_currency"] == "EUR"


def test_purchase_invoice_matches_bank_movement_by_supplier_token_and_amount():
    from datetime import date
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.database.database import Base
    from app.database.models import BankMovement, PurchaseInvoice
    from app.api.purchase_invoice_routes import matching_bank_movements

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            invoice = PurchaseInvoice(invoice_number="ES-1", issue_date=date(2026, 10, 1), supplier_name="Eurosets Srl", supplier_vat=None, currency="EUR", net_amount=Decimal("100"), vat_amount=Decimal("22"), gross_amount=Decimal("122"), source_filename="eurosets.xlsx", source_hash="e" * 64, source_format="EXCEL")
            movement = BankMovement(booking_date=date(2026, 10, 5), amount=Decimal("-122.00"), direction="uscita", description="Pagamento fattura Eurosets", counterparty="EUROSETS", source_filename="estratto.csv", import_key="eurosets-movement")
            db.add_all([invoice, movement])
            db.commit()
            assert matching_bank_movements(invoice, db) == [movement]
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
