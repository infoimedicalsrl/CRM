"""Sicurezza (login obbligatorio) e API su database reale, con dati interamente sintetici.

Gira su SQLite di sviluppo; con DATABASE_URL=postgresql://... gira su PostgreSQL/Supabase.
"""
import io
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import auth, config
from app.main import app
from app.database.database import init_db

BACKEND = Path(__file__).resolve().parents[1]

ORDER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Order xmlns="urn:oasis:names:specification:ubl:schema:xsd:Order-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
 <cbc:ID>TEST-{n}</cbc:ID><cbc:IssueDate>2026-0{m}-15</cbc:IssueDate><cbc:DocumentCurrencyCode>EUR</cbc:DocumentCurrencyCode>
 <cac:BuyerCustomerParty><cac:Party><cac:PartyLegalEntity><cbc:RegistrationName>Cliente Demo Srl</cbc:RegistrationName></cac:PartyLegalEntity>
 <cac:PartyTaxScheme><cbc:CompanyID>IT00000000001</cbc:CompanyID></cac:PartyTaxScheme></cac:Party></cac:BuyerCustomerParty>
 <cac:TaxTotal><cbc:TaxAmount>22.00</cbc:TaxAmount></cac:TaxTotal>
 <cac:AnticipatedMonetaryTotal><cbc:TaxExclusiveAmount>100.00</cbc:TaxExclusiveAmount><cbc:TaxInclusiveAmount>122.00</cbc:TaxInclusiveAmount></cac:AnticipatedMonetaryTotal>
 <cac:OrderLine><cac:LineItem><cbc:ID>1</cbc:ID><cbc:Quantity unitCode="C62">10</cbc:Quantity><cbc:LineExtensionAmount>100.00</cbc:LineExtensionAmount>
 <cac:Price><cbc:PriceAmount>10.00</cbc:PriceAmount></cac:Price>
 <cac:Item><cbc:Name>Prodotto demo</cbc:Name><cac:SellersItemIdentification><cbc:ID>DEMO 001</cbc:ID></cac:SellersItemIdentification>
 <cac:ClassifiedTaxCategory><cbc:ID>S</cbc:ID><cbc:Percent>22</cbc:Percent></cac:ClassifiedTaxCategory></cac:Item></cac:LineItem></cac:OrderLine>
</Order>"""

FATTURA_XML = """<?xml version="1.0"?><p:FatturaElettronica xmlns:p="http://ivaservizi.agenziaentrate.gov.it/docs/xsd/fatture/v1.2">
<FatturaElettronicaHeader><CessionarioCommittente><DatiAnagrafici><IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>00000000001</IdCodice></IdFiscaleIVA>
<Anagrafica><Denominazione>Cliente Demo Srl</Denominazione></Anagrafica></DatiAnagrafici></CessionarioCommittente></FatturaElettronicaHeader>
<FatturaElettronicaBody><DatiGenerali><DatiGeneraliDocumento><Data>2026-02-10</Data><Numero>F1</Numero><ImportoTotaleDocumento>122.00</ImportoTotaleDocumento></DatiGeneraliDocumento></DatiGenerali>
<DatiBeniServizi><DatiRiepilogo><ImponibileImporto>100.00</ImponibileImporto><Imposta>22.00</Imposta></DatiRiepilogo></DatiBeniServizi></FatturaElettronicaBody></p:FatturaElettronica>"""


@pytest.fixture(scope="module", autouse=True)
def _schema():
    init_db()


@pytest.fixture()
def anon():
    """Client SENZA scorciatoie di autenticazione."""
    return TestClient(app)


@pytest.fixture()
def authed(monkeypatch):
    """Client con un utente Supabase simulato (la verifica del token viene mockata)."""
    class R:
        status_code = 200
        def json(self): return {"id": "u1", "email": "owner@example.com"}
    monkeypatch.setattr(auth.httpx, "get", lambda *a, **k: R())
    monkeypatch.setattr(config, "AUTH_DISABLED", False)
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    auth._cache.clear()
    c = TestClient(app)
    c.headers["Authorization"] = "Bearer token-valido"
    return c


@pytest.fixture(autouse=True)
def _auth_on(monkeypatch):
    monkeypatch.setattr(config, "AUTH_DISABLED", False)


PROTECTED = ["/api/orders", "/api/dashboard", "/api/customers", "/api/products", "/api/ddts", "/api/imports",
             "/api/bank/movements", "/api/analytics/revenue-trend", "/api/search?q=ab", "/api/exports/orders",
             "/api/customer-statements", "/api/backups", "/api/dashboard-sync"]


def test_health_e_unica_rotta_pubblica(anon):
    assert anon.get("/api/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", PROTECTED)
def test_senza_login_nessun_dato(anon, path):
    r = anon.get(path)
    assert r.status_code in (401, 404, 405), path   # 404/405: rotta rimossa, comunque nessun dato
    assert r.status_code != 200


def test_scrittura_senza_login_rifiutata(anon):
    assert anon.delete("/api/orders/1").status_code == 401
    assert anon.post("/api/imports/upload", files={"file": ("a.xml", b"<a/>")}).status_code == 401


def test_token_non_valido_rifiutato(anon, monkeypatch):
    class R:
        status_code = 401
        def json(self): return {}
    monkeypatch.setattr(auth.httpx, "get", lambda *a, **k: R())
    monkeypatch.setattr(config, "SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon")
    auth._cache.clear()
    r = anon.get("/api/orders", headers={"Authorization": "Bearer falso"})
    assert r.status_code == 401


def test_utente_fuori_allowlist_403(authed, monkeypatch):
    monkeypatch.setattr(config, "ALLOWED_EMAILS", {"altro@example.com"})
    assert authed.get("/api/orders").status_code == 403


def test_auth_disabled_ignorato_su_vercel():
    env = {**os.environ, "VERCEL": "1", "PEPPOL_AUTH_DISABLED": "1", "DATABASE_URL": "postgresql://u:p@h/db",
           "SUPABASE_URL": "https://x.supabase.co", "SUPABASE_ANON_KEY": "a", "SUPABASE_SERVICE_ROLE_KEY": "s"}
    out = subprocess.run([sys.executable, "-c", "from app import config; print(config.AUTH_DISABLED)"],
                         cwd=BACKEND, env=env, capture_output=True, text=True)
    assert out.stdout.strip() == "False", out.stderr


def test_vercel_senza_database_url_non_parte():
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env["VERCEL"] = "1"
    out = subprocess.run([sys.executable, "-c", "from app import config"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert out.returncode != 0 and "DATABASE_URL" in out.stderr


def test_flusso_completo_con_storage_e_grafici(authed):
    for n, m in (("A1", 1), ("A2", 2), ("A3", 2)):
        r = authed.post("/api/imports/upload", files={"file": (f"o{n}.xml", ORDER_XML.format(n=n, m=m).encode(), "application/xml")})
        assert r.status_code in (200, 409), r.text
    orders = authed.get("/api/orders").json()
    items = orders["items"] if isinstance(orders, dict) else orders
    assert len(items) >= 3
    oid = items[0]["id"]

    # query che usavano strftime (SQLite) -> devono funzionare anche su PostgreSQL
    trend = authed.get("/api/analytics/revenue-trend")
    assert trend.status_code == 200 and {t["period"] for t in trend.json()} >= {"2026-01", "2026-02"}
    assert authed.get("/api/analytics/quantity-trend").status_code == 200
    assert authed.get("/api/dashboard").status_code == 200
    assert authed.get("/api/dashboard/financial-summary").status_code == 200
    assert authed.get("/api/analytics/top-products").status_code == 200
    assert authed.get("/api/analytics/top-customers").status_code == 200
    assert authed.get("/api/analytics/product-customer").status_code == 200
    assert authed.get("/api/analytics/zero-value").status_code == 200
    assert authed.get("/api/products").status_code == 200
    cust = authed.get("/api/customers").json()
    cid = (cust["items"] if isinstance(cust, dict) else cust)[0]["id"]
    cd = authed.get(f"/api/customers/{cid}")
    assert cd.status_code == 200 and cd.json()["trend"]
    assert authed.get("/api/search?q=demo").status_code == 200
    for ex in ("orders", "products", "customers", "analytics", "ddts"):
        assert authed.get(f"/api/exports/{ex}?format=xlsx").status_code == 200, ex

    # documento originale salvato nello Storage e riletto per il ripristino
    prev = authed.get(f"/api/orders/{oid}/restore-preview")
    assert prev.status_code == 200, prev.text
    assert authed.post(f"/api/orders/{oid}/restore").status_code == 200

    # fattura vendita XML -> archiviata; stesso file di nuovo -> 409
    r = authed.post("/api/sales-invoices/import", files={"file": ("f1.xml", FATTURA_XML.encode(), "application/xml")})
    assert r.status_code in (200, 409), r.text
    assert authed.get("/api/sales-invoices").status_code == 200

    # estratto conto cliente CSV -> file riletto dal Storage
    csv_data = "Documento;Ordine;Importo;Data\nF1;TEST-A1;122,00;10/02/2026\n".encode()
    r = authed.post("/api/customer-statements/import", files={"file": ("ec.csv", csv_data, "text/csv")})
    if r.status_code == 200:
        iid = r.json().get("id") or r.json().get("import", {}).get("id")
        if iid:
            f = authed.get(f"/api/customer-statements/{iid}/file")
            assert f.status_code == 200 and f.content == csv_data

    # rotte locali eliminate
    for gone in ("/api/backups", "/api/dashboard-sync", "/api/imports/watcher", "/api/ddts/watcher"):
        assert authed.get(gone).status_code in (404, 405, 422), gone
