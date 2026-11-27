from datetime import date
from decimal import Decimal

from app.parser.bper_bank_parser import _parse_lines, money, parse_date


def test_parse_date_italian_and_iso_formats():
    assert parse_date("09/10/2026") == date(2026, 10, 9)
    assert parse_date("09.10.26") == date(2026, 10, 9)
    assert parse_date("2026-10-09") == date(2026, 10, 9)


def test_money_italian_thousands_and_negative_formats():
    assert money("1.234,56") == Decimal("1234.56")
    assert money("- 12,30") == Decimal("-12.30")
    assert money("12,30-") == Decimal("-12.30")


def test_parse_bper_rows_with_outflow_inflow_columns():
    rows, opening, closing = _parse_lines([
        "Saldo iniziale 1.000,00",
        "01/10/2026 01/10/2026 Bonifico ricevuto 0,00 125,00",
        "02/10/2026 02/10/2026 Pagamento carta 45,90 0,00",
        "Saldo finale 1.079,10",
    ])
    assert opening == Decimal("1000.00")
    assert closing == Decimal("1079.10")
    assert len(rows) == 2
    assert rows[0]["amount"] == Decimal("125.00")
    assert rows[0]["direction"] == "entrata"
    assert rows[1]["amount"] == Decimal("-45.90")
    assert rows[1]["direction"] == "uscita"
    assert rows[0]["balance_after"] == Decimal("1125.00")
    assert rows[1]["balance_after"] == Decimal("1079.10")


def test_parse_two_digit_year_and_continuation_description():
    rows, _, _ = _parse_lines([
        "03/10/26 03/10/26 Bonifico in uscita 1.234,56 0,00",
        "Beneficiario: Mario Rossi",
    ])
    assert len(rows) == 1
    assert rows[0]["booking_date"] == date(2026, 10, 3)
    assert rows[0]["amount"] == Decimal("-1234.56")
    assert "Mario Rossi" in rows[0]["description"]
    assert rows[0]["counterparty"] == "Mario Rossi"


def test_unambiguous_single_amount_row():
    rows, _, _ = _parse_lines(["04/10/2026 04/10/2026 Accredito 75,00"])
    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("75.00")
    assert rows[0]["direction"] == "entrata"


def test_bper_columns_keep_bank_amount_separate_from_invoice_amount():
    from app.parser.bper_bank_parser import _find_columns
    header = f"{'DATA':<20}{'VALUTA':<20}{'USCITE':<20}{'INGRESSO':<20}{'DESCRIZIONE'}"
    row = f"{'25/05/2026':<20}{'21/05/2026':<20}{'1.428,37':>20}{'0,00':>20}{'01005-03298 a favore di BIOTECH SRL Num. Bon.Sepa 261461000090324 CIG: B5589E587C, CUP: , FATTURA N. 19 PA NO CIG: B55899781E, CUP: , FA 13.122,00 EUR Spese: 0,00 EUR'}"
    positions = _find_columns([header])
    rows, _, _ = _parse_lines([row], positions)
    assert len(rows) == 1
    assert rows[0]["amount"] == Decimal("-1428.37")
    assert rows[0]["direction"] == "uscita"
    assert rows[0]["counterparty"] == "BIOTECH SRL"
    assert "13.122,00 EUR" in rows[0]["description"]
    assert "B5589E587C" in rows[0]["description"]
    assert "B55899781E" in rows[0]["description"]


def test_invoice_details_are_extracted_without_changing_bank_amount():
    from app.parser.bper_bank_parser import extract_description_details
    details = extract_description_details(
        "01005-03298 a favore di BIOTECH SRL Num. Bon.Sepa 261461000090324 "
        "CIG: B5589E587C, CUP: , FATTURA N. 19 PA NO CIG: B55899781E, CUP: , "
        "FA 13.122,00 EUR Spese: 0,00 EUR - RIF. 26146/0145275"
    )
    assert details["counterparty"] == "BIOTECH SRL"
    assert details["invoice_amounts"] == [Decimal("13122.00")]
    assert details["fees"] == [Decimal("0.00")]
    assert {x["cig"] for x in details["invoice_details"] if x["cig"]} == {"B5589E587C", "B55899781E"}
    assert {x["number"]: x["cig"] for x in details["invoice_details"] if x["number"]} == {"19 PA": "B5589E587C"}
    assert details["cig_codes"] == ["B5589E587C", "B55899781E"]
