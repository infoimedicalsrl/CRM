from decimal import Decimal

from app.api.sales_invoice_routes import parse_fatturapa


def test_parse_fatturapa_sales_invoice():
    xml = b'''<?xml version="1.0" encoding="UTF-8"?>
    <p:FatturaElettronica xmlns:p="urn:fatturapa">
      <p:FatturaElettronicaHeader>
        <p:CessionarioCommittente><p:DatiAnagrafici>
          <p:IdFiscaleIVA><p:IdPaese>IT</p:IdPaese><p:IdCodice>01234567890</p:IdCodice></p:IdFiscaleIVA>
          <p:Anagrafica><p:Denominazione>Cliente Demo SRL</p:Denominazione></p:Anagrafica>
        </p:DatiAnagrafici></p:CessionarioCommittente>
      </p:FatturaElettronicaHeader>
      <p:FatturaElettronicaBody><p:DatiGenerali><p:DatiGeneraliDocumento>
        <p:Divisa>EUR</p:Divisa><p:Data>2026-06-30</p:Data><p:Numero>FT-2026-001</p:Numero>
        <p:ImportoTotaleDocumento>122.00</p:ImportoTotaleDocumento>
      </p:DatiGeneraliDocumento></p:DatiGenerali>
      <p:DatiBeniServizi><p:DatiRiepilogo><p:ImponibileImporto>100.00</p:ImponibileImporto><p:Imposta>22.00</p:Imposta></p:DatiRiepilogo></p:DatiBeniServizi>
      </p:FatturaElettronicaBody>
    </p:FatturaElettronica>'''
    result = parse_fatturapa(xml)
    assert result["invoice_number"] == "FT-2026-001"
    assert result["customer_name"] == "Cliente Demo SRL"
    assert result["customer_vat"] == "01234567890"
    assert result["issue_date"].isoformat() == "2026-06-30"
    assert result["net_amount"] == Decimal("100.00")
    assert result["vat_amount"] == Decimal("22.00")
    assert result["gross_amount"] == Decimal("122.00")
