import pytest
from pathlib import Path as _P
from decimal import Decimal
from datetime import date

from app.parser.ddt_parser import _parse_lines_from_text


def test_ddt_parser_keeps_every_product_and_fields():
    text = """
    CODICE DESCRIZIONE QUANTITA LOTTO SCADENZA
    BE-HQV25707
    Dispositivo chirurgico sterile
    8 PZ
    Lotto: 012144100
    Scadenza: 24/11/2028
    AG70214 Prodotto sterile 8 PZ Lotto: 012144105 Scadenza: 24/11/2028
    AG5300 Prodotto sterile 8 PZ Lotto: 012116307 Scadenza: 09/12/2028
    """
    rows = _parse_lines_from_text(text)
    assert len(rows) == 3
    assert rows[0].supplier_product_code == "BE-HQV25707"
    assert rows[0].description == "Dispositivo chirurgico sterile"
    assert rows[0].quantity == Decimal("8")
    assert rows[0].lot_number == "012144100"
    assert rows[0].expiry_date == date(2028, 11, 24)
    assert rows[1].supplier_product_code == "AG70214"
    assert rows[2].supplier_product_code == "AG5300"
    assert rows[2].lot_number == "012116307"
    assert rows[2].expiry_date == date(2028, 12, 9)


def test_ddt_parser_does_not_treat_lot_as_product_code():
    text = """
    BE-HQV25707 Dispositivo 8 PZ Lotto: ABC123 Scadenza: 24/11/2028
    AG70214 Prodotto 4 PZ Lotto: XYZ987 Scadenza: 01/01/2029
    """
    rows = _parse_lines_from_text(text)
    assert [row.supplier_product_code for row in rows] == ["BE-HQV25707", "AG70214"]


def test_ddt_parser_isolates_each_product_block_and_does_not_cross_assign_lot():
    text = """
    DESTINATARIO
    98158 Messina
    CODICE=DESCRIZIONE=QUANTITA
    123456=123456
    Prodotto numerico=2 PZ
    AG70214=AG70214
    Circuito Adulto=8 PZ
    Lotto: LOT-70214 Scadenza: 24/11/2028
    AG5300=AG5300
    Horizon AF Plus=3 PZ
    Lotto: LOT-5300 Scadenza: 09/12/2028
    """
    rows = _parse_lines_from_text(text)
    assert [r.supplier_product_code for r in rows] == ["123456", "AG70214", "AG5300"]
    assert rows[0].lot_number is None
    assert rows[0].expiry_date is None
    assert rows[1].lot_number == "LOT-70214"
    assert rows[1].expiry_date == date(2028, 11, 24)
    assert rows[2].lot_number == "LOT-5300"
    assert rows[2].expiry_date == date(2028, 12, 9)


def test_ddt_parser_handles_many_single_line_products_without_mixing_fields():
    text = """
    AA1001 Prodotto A 1 PZ Lotto: LOT-1001 Scadenza: 01/01/2029
    BB2002 Prodotto B 12 PZ Lotto: LOT-2002 Scadenza: 02/02/2029
    CC3003 Prodotto C 4 PZ
    DD4004 Prodotto D 7 PZ Lotto: L4004 Scadenza: 04/04/2029
    EE5005 Prodotto E 9 PZ Lotto: L5005 Scadenza: 05/05/2029
    """
    rows = _parse_lines_from_text(text)
    assert [r.supplier_product_code for r in rows] == ["AA1001", "BB2002", "CC3003", "DD4004", "EE5005"]
    assert [r.quantity for r in rows] == [Decimal("1"), Decimal("12"), Decimal("4"), Decimal("7"), Decimal("9")]
    assert rows[2].lot_number is None and rows[2].expiry_date is None
    assert rows[3].lot_number == "L4004"


def test_ddt_parser_accepts_codes_with_dots_slashes_and_visual_spaces():
    text = """
    DECOSL.05090 Specchio ovale 1 PZ Lotto: LOT-1 Scadenza: 01/01/2029
    ETLAB/950 Specchio laboratorio 2 PZ Lotto: LOT-2 Scadenza: 02/02/2029
    BE-HLS 7050 Dispositivo medicale 3 PZ Lotto: LOT-3 Scadenza: 03/03/2029
    """
    rows = _parse_lines_from_text(text)
    assert [r.supplier_product_code for r in rows] == ["DECOSL.05090", "ETLAB/950", "BE-HLS7050"]
    assert [r.quantity for r in rows] == [Decimal("1"), Decimal("2"), Decimal("3")]
    assert [r.lot_number for r in rows] == ["LOT-1", "LOT-2", "LOT-3"]


def test_ddt_parser_ignores_code_like_tokens_inside_notes():
    text = """
    AA1001 Prodotto A 1 PZ Lotto: LOT-A1001
    * Nota: utilizzare ricambio BB2002 se necessario
    * Confezione integra
    CC3003 Prodotto C 2 PZ Lotto: LOT-C3003
    """
    rows = _parse_lines_from_text(text)
    assert [r.supplier_product_code for r in rows] == ["AA1001", "CC3003"]
    assert rows[0].lot_number == "LOT-A1001"
    assert rows[1].lot_number == "LOT-C3003"


@pytest.mark.skipif(not (_P(__file__).parent / "fixtures" / "DDT_88-26-Recupero_sangue.pdf").exists(), reason="PDF reale non incluso nel repository (dati riservati)")
def test_real_ddt_88_2026_uses_physical_code_column_and_pairs_lots(tmp_path):
    from pathlib import Path
    from app.parser.ddt_parser import parse_ddt

    path = Path(__file__).parent / "fixtures" / "DDT_88-26-Recupero_sangue.pdf"
    ddt = parse_ddt(path)

    assert ddt.ddt_number == "88/2026"
    assert ddt.order_reference == "9562V1/26"
    assert [row.supplier_product_code for row in ddt.lines] == [
        "AT-KIT", "AT3", "ATR40", "ATS", "ATV-F140C"
    ]
    assert [row.quantity for row in ddt.lines] == [Decimal("24")] * 5
    assert [row.lot_number for row in ddt.lines] == [
        None, "TEA 214", "TEA 271", "TEA 296", "SLA 113"
    ]
    assert [row.expiry_date for row in ddt.lines] == [
        None, date(2029, 4, 21), date(2029, 4, 27), date(2029, 4, 29), date(2028, 10, 11)
    ]


@pytest.mark.skipif(not (_P(__file__).parent / "fixtures" / "DDT_15-26-CEC.pdf").exists(), reason="PDF reale non incluso nel repository (dati riservati)")
def test_real_ddt_15_2026_keeps_three_code_column_rows():
    from pathlib import Path
    from app.parser.ddt_parser import parse_ddt

    path = Path(__file__).parent / "fixtures" / "DDT_15-26-CEC.pdf"
    ddt = parse_ddt(path)

    assert [row.supplier_product_code for row in ddt.lines] == [
        "BE-HQV25707", "AG70214", "AG5300"
    ]
    assert [row.quantity for row in ddt.lines] == [Decimal("8")] * 3
    assert [row.lot_number for row in ddt.lines] == [
        None, "012144105", "012116307"
    ]
