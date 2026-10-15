from decimal import Decimal
from pathlib import Path
import os

import pytest

from app.parser.peppol_parser import parse_peppol_order
from app.parser.validator import validate_order


@pytest.mark.skipif(not os.environ.get("PEPPOL_SIMPLE_XML"), reason="XML di esempio non incluso (dati reali)")
def test_simple_order():
    path = Path(os.environ["PEPPOL_SIMPLE_XML"])
    order = parse_peppol_order(path)
    assert order.order_number == "202600017169"
    assert order.total_net == Decimal("890.00")
    assert len(order.lines) == 1
    assert order.lines[0].supplier_product_code == "BE-PAS 1915"
    assert order.lines[0].quantity == Decimal("1")
    assert order.lines[0].vat_rate == Decimal("22")
    assert validate_order(order) == []


@pytest.mark.skipif(not os.environ.get("PEPPOL_MULTI_XML"), reason="XML di esempio non incluso (dati reali)")
def test_multi_line_order():
    path = Path(os.environ["PEPPOL_MULTI_XML"])
    order = parse_peppol_order(path)
    assert order.order_number == "2026/8039V0"
    assert order.total_net == Decimal("163200")
    assert order.total_vat == Decimal("35904")
    assert len(order.lines) == 5
    assert [x.supplier_product_code for x in order.lines] == [
        "IM-CEC", "CP37V-V0", "AG5305", "AG70214", "AT-KIT"
    ]
    assert order.lines[2].unit_price == 0
    assert order.lines[3].vat_rate == 0
    assert order.lines[4].unit_code == "KT"
    assert validate_order(order) == []
