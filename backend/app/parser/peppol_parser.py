from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import Optional, Union

from .models import ParsedCustomer, ParsedOrder, ParsedOrderLine
from app.normalization import normalize_unit_code

UBL_ORDER = "urn:oasis:names:specification:ubl:schema:xsd:Order-2"
CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
NS = {"ord": UBL_ORDER, "cac": CAC, "cbc": CBC}
MONEY = Decimal("0.01")


class PeppolParseError(ValueError):
    pass


def _text(node: ET.Element, path: str, *, required: bool = False) -> Optional[str]:
    found = node.find(path, NS)
    value = found.text.strip() if found is not None and found.text else None
    if required and not value:
        raise PeppolParseError(f"Campo obbligatorio mancante: {path}")
    return value


def _decimal(node: ET.Element, path: str, *, required: bool = False) -> Decimal:
    value = _text(node, path, required=required)
    if value is None:
        return Decimal("0")
    try:
        return Decimal(value)
    except Exception as exc:
        raise PeppolParseError(f"Valore numerico non valido in {path}: {value}") from exc


def _q2(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def parse_peppol_order(file_path: Union[str, Path]) -> ParsedOrder:
    file_path = Path(file_path)
    try:
        root = ET.parse(file_path).getroot()
    except ET.ParseError as exc:
        raise PeppolParseError(f"XML non valido: {exc}") from exc

    order = root.find("ord:Order", NS)
    if order is None and root.tag == f"{{{UBL_ORDER}}}Order":
        order = root
    if order is None:
        raise PeppolParseError("Documento UBL Order non trovato")

    order_number = _text(order, "cbc:ID", required=True)
    order_date_raw = _text(order, "cbc:IssueDate", required=True)
    currency = _text(order, "cbc:DocumentCurrencyCode", required=True)
    try:
        order_date = date.fromisoformat(order_date_raw)
    except ValueError as exc:
        raise PeppolParseError(f"Data ordine non valida: {order_date_raw}") from exc

    buyer = order.find("cac:BuyerCustomerParty/cac:Party", NS)
    if buyer is None:
        raise PeppolParseError("BuyerCustomerParty mancante")
    customer_name = (
        _text(buyer, "cac:PartyLegalEntity/cbc:RegistrationName")
        or _text(buyer, "cac:PartyName/cbc:Name", required=True)
    )
    vat_number = _text(buyer, "cac:PartyTaxScheme/cbc:CompanyID", required=True)
    endpoint = _text(buyer, "cbc:EndpointID")

    total_net = _decimal(order, "cac:AnticipatedMonetaryTotal/cbc:TaxExclusiveAmount", required=True)
    total_vat = _decimal(order, "cac:TaxTotal/cbc:TaxAmount", required=True)
    total_gross = _decimal(order, "cac:AnticipatedMonetaryTotal/cbc:TaxInclusiveAmount", required=True)

    parsed_lines: list[ParsedOrderLine] = []
    for line in order.findall("cac:OrderLine", NS):
        item = line.find("cac:LineItem", NS)
        if item is None:
            raise PeppolParseError("OrderLine senza LineItem")

        line_number = _text(item, "cbc:ID", required=True)
        quantity_node = item.find("cbc:Quantity", NS)
        if quantity_node is None or quantity_node.text is None:
            raise PeppolParseError(f"Quantità mancante alla riga {line_number}")
        quantity = Decimal(quantity_node.text.strip())
        unit_code = normalize_unit_code(quantity_node.attrib.get("unitCode"))

        unit_price = _decimal(item, "cac:Price/cbc:PriceAmount", required=True)
        line_net = _decimal(item, "cbc:LineExtensionAmount", required=True)
        product_code = _text(
            item,
            "cac:Item/cac:SellersItemIdentification/cbc:ID",
            required=True,
        )
        description = _text(item, "cac:Item/cbc:Name")
        vat_category = _text(item, "cac:Item/cac:ClassifiedTaxCategory/cbc:ID")
        vat_rate = _decimal(item, "cac:Item/cac:ClassifiedTaxCategory/cbc:Percent", required=True)

        line_vat = _q2(line_net * vat_rate / Decimal("100"))
        line_gross = _q2(line_net + line_vat)

        parsed_lines.append(
            ParsedOrderLine(
                line_number=line_number,
                supplier_product_code=product_code,
                description=description,
                quantity=quantity,
                unit_code=unit_code,
                unit_price=unit_price,
                line_net=line_net,
                vat_category=vat_category,
                vat_rate=vat_rate,
                line_vat=line_vat,
                line_gross=line_gross,
            )
        )

    if not parsed_lines:
        raise PeppolParseError("Ordine senza righe prodotto")

    return ParsedOrder(
        order_number=order_number,
        order_date=order_date,
        customer=ParsedCustomer(
            name=customer_name,
            vat_number=vat_number,
            peppol_endpoint=endpoint,
        ),
        currency=currency,
        total_net=total_net,
        total_vat=total_vat,
        total_gross=total_gross,
        lines=parsed_lines,
    )
