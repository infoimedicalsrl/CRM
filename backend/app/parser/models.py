from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field


class ParsedCustomer(BaseModel):
    name: str
    vat_number: str
    peppol_endpoint: Optional[str] = None


class ParsedOrderLine(BaseModel):
    line_number: str
    supplier_product_code: str
    description: Optional[str] = None
    quantity: Decimal = Field(ge=0)
    unit_code: Optional[str] = None
    unit_price: Decimal = Field(ge=0)
    line_net: Decimal = Field(ge=0)
    vat_category: Optional[str] = None
    vat_rate: Decimal = Field(ge=0)
    line_vat: Decimal = Field(ge=0)
    line_gross: Decimal = Field(ge=0)


class ParsedOrder(BaseModel):
    order_number: str
    order_date: date
    customer: ParsedCustomer
    currency: str
    total_net: Decimal = Field(ge=0)
    total_vat: Decimal = Field(ge=0)
    total_gross: Decimal = Field(ge=0)
    lines: list[ParsedOrderLine]
