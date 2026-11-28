from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import io
import tempfile
import zipfile
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.database.database import SessionLocal, month_expr
from app.database.models import Customer, ImportJob, Order, OrderLine, Product, ProductCodeVariant, DeliveryNote, DeliveryNoteLine, SalesInvoice, BankMovement
from app.importer.importer import DuplicateOrderError, import_xml
from app.importer.ddt_importer import DuplicateDDTError, import_ddt, relink_ddt, refresh_order_delivery, refresh_ddt_status, order_references_match, sha256_file
from app.parser.peppol_parser import parse_peppol_order
from app.storage import StorageError, build_key, load_document, save_document
from app.exporting import export_response
from app.normalization import normalize_product_code, normalize_unit_code, normalize_customer_name, normalize_vat_number

router = APIRouter()


def _archive(prefix: str, data: bytes, ext: str, content_type: str) -> str:
    """Salva il documento originale su Supabase Storage prima di importarlo."""
    try:
        return save_document(prefix, data, ext, content_type)
    except StorageError as exc:
        raise HTTPException(502, str(exc)) from exc


class CustomerNameUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class OrderLineUpdate(BaseModel):
    id: int
    line_number: Optional[str] = None
    supplier_product_code: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    quantity: Optional[Decimal] = Field(None, ge=0)
    unit_code: Optional[str] = None
    unit_price: Optional[Decimal] = Field(None, ge=0)
    vat_category: Optional[str] = None
    vat_rate: Optional[Decimal] = Field(None, ge=0)


class OrderUpdate(BaseModel):
    order_number: Optional[str] = Field(None, min_length=1, max_length=128)
    order_date: Optional[date] = None
    customer_id: Optional[int] = None
    lines: Optional[list[OrderLineUpdate]] = None


class OrderDeliveryLineUpdate(BaseModel):
    delivered_quantity: Optional[Decimal] = Field(None, ge=0)


def _normalized_product_expr():
    return func.upper(func.replace(Product.supplier_product_code, " ", ""))


def _get_order_status(db: Session, order_id: int) -> str:
    """
    Get order delivery status without the full summary.
    Returns: "EVASO", "PARZIALE", "DA_EVADERE"
    """
# Build subqueries for DDT delivered quantities
    ddt_line_sub = (
        select(
            OrderLine.id.label("line_id"),
            func.coalesce(
                func.sum(DeliveryNoteLine.quantity), 0
            ).label("ddt_delivered")
        )
        .join(
            DeliveryNoteLine,
            DeliveryNoteLine.order_line_id == OrderLine.id
        )
        .group_by(OrderLine.id)
        .subquery()
    )

    # Query order lines with DDT deliveries
    rows = db.execute(
        select(OrderLine.quantity, ddt_line_sub.c.ddt_delivered, OrderLine.manual_delivered_quantity)
        .outerjoin(ddt_line_sub, ddt_line_sub.c.line_id == OrderLine.id)
        .where(OrderLine.order_id == order_id)
    ).all()

    total_ordered = Decimal("0")
    total_delivered = Decimal("0")

    for row in rows:
        ordered = Decimal(row[0])
        ddt_delivered = Decimal(row[1]) if row[1] else Decimal("0")
        manual_delivered = Decimal(row[2]) if row[2] else Decimal("0")

        # Manual override takes priority if set
        delivered = manual_delivered if manual_delivered > 0 else ddt_delivered

        total_ordered += ordered
        total_delivered += delivered

    residual = max(Decimal("0"), total_ordered - total_delivered)

    # Determine overall status
    if residual > 0 and total_ordered > 0:
        return "DA_EVADERE"  # Red
    elif total_delivered >= total_ordered:
        return "EVASO"  # Green
    elif total_delivered > 0:
        return "PARZIALE"  # Yellow
    else:
        return "DA_EVADERE"  # Red (no orders)


def _product_code_filter(code: str):
    return _normalized_product_expr() == normalize_product_code(code)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _order_filters(
    date_from: Optional[date],
    date_to: Optional[date],
    customer_id: Optional[int],
):
    filters = []
    if date_from:
        filters.append(Order.order_date >= date_from)
    if date_to:
        filters.append(Order.order_date <= date_to)
    if customer_id:
        filters.append(Order.customer_id == customer_id)
    return filters


@router.get("/orders")
def list_orders(
    search: Optional[str] = None,
    customer_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
):
    stmt = select(Order, Customer).join(Customer, Order.customer_id == Customer.id)
    filters = _order_filters(date_from, date_to, customer_id)
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(Order.order_number.ilike(term), Customer.name.ilike(term), Customer.vat_number.ilike(term)))
    if filters:
        stmt = stmt.where(and_(*filters))
    rows = db.execute(stmt.order_by(Order.order_date.desc(), Order.id.desc())).all()
    return [
        {
            "id": o.id,
            "order_number": o.order_number,
            "order_date": o.order_date,
            "customer_id": c.id,
            "customer": c.name,
            "customer_vat": c.vat_number,
            "currency": o.currency,
            "total_net": o.total_net,
            "total_vat": o.total_vat,
            "total_gross": o.total_gross,
            "status": _get_order_status(db, o.id),
        }
        for o, c in rows
    ]



def _delivery_summary_for_order(db: Session, order_id: int):
    order = db.get(Order, order_id)
    if not order:
        return {"status": "NON_CONSEGNATO", "ordered_quantity": 0, "delivered_quantity": 0, "residual_quantity": 0, "lines": [], "ddts": []}
    lines = db.scalars(select(OrderLine).where(OrderLine.order_id == order_id).order_by(OrderLine.id)).all()
    result_lines = []
    total_ordered = Decimal("0")
    total_delivered = Decimal("0")
    ddts = db.scalars(select(DeliveryNote).where(DeliveryNote.order_id == order_id).order_by(DeliveryNote.ddt_date, DeliveryNote.id)).all()
    for ol in lines:
        ddt_delivered = db.scalar(
            select(func.coalesce(func.sum(DeliveryNoteLine.quantity), 0))
            .where(
                DeliveryNoteLine.order_line_id == ol.id,
                DeliveryNoteLine.is_gift.is_(False),
            )
        ) or Decimal("0")
        ordered = Decimal(ol.quantity)
        # A manual value is an explicit override. If it is not set, the
        # delivered quantity is derived exclusively from the real DDT links.
        delivered = (
            Decimal(ol.manual_delivered_quantity)
            if ol.manual_delivered_quantity is not None
            else Decimal(ddt_delivered)
        )
        residual = max(Decimal("0"), ordered - delivered)
        over = max(Decimal("0"), delivered - ordered)
        total_ordered += ordered
        total_delivered += delivered
        result_lines.append({
            "order_line_id": ol.id,
            "product_id": ol.product_id,
            "supplier_product_code": ol.product.supplier_product_code if ol.product else "",
            "description": ol.description_snapshot,
            "unit_code": ol.unit_code,
            "ordered_quantity": ordered,
            "delivered_quantity": delivered,
            "ddt_delivered_quantity": Decimal(ddt_delivered),
            "manual_delivered_quantity": Decimal(ol.manual_delivered_quantity) if ol.manual_delivered_quantity is not None else None,
            "residual_quantity": residual,
            "over_quantity": over,
            "status": "SOVRACONSEGNATO" if over > 0 else ("COMPLETAMENTE_CONSEGNATO" if delivered >= ordered else ("PARZIALMENTE_CONSEGNATO" if delivered > 0 else "NON_CONSEGNATO")),
        })
    if any(x["over_quantity"] > 0 for x in result_lines):
        status = "SOVRACONSEGNATO"
    elif total_delivered >= total_ordered and total_ordered > 0:
        status = "COMPLETAMENTE_CONSEGNATO"
    elif total_delivered > 0:
        status = "PARZIALMENTE_CONSEGNATO"
    else:
        status = "NON_CONSEGNATO"
    ddt_items = []
    for ddt in ddts:
        delivered = sum((x.quantity for x in ddt.lines if not x.is_gift and x.order_line_id is not None), Decimal("0"))
        ddt_items.append({"id": ddt.id, "number": ddt.ddt_number, "date": ddt.ddt_date, "quantity": delivered, "status": ddt.status})
    return {"status": status, "ordered_quantity": total_ordered, "delivered_quantity": total_delivered, "residual_quantity": max(Decimal("0"), total_ordered-total_delivered), "over_quantity": max(Decimal("0"), total_delivered-total_ordered), "lines": result_lines, "ddts": ddt_items}


@router.get("/orders/{order_id}")
def order_detail(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Ordine non trovato")
    customer = db.get(Customer, order.customer_id)
    lines = db.execute(
        select(OrderLine, Product)
        .join(Product, OrderLine.product_id == Product.id)
        .where(OrderLine.order_id == order_id)
        .order_by(OrderLine.id)
    ).all()
    return {
        "id": order.id,
        "order_number": order.order_number,
        "order_date": order.order_date,
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "vat_number": customer.vat_number,
            "peppol_endpoint": customer.peppol_endpoint,
        },
        "currency": order.currency,
        "total_net": order.total_net,
        "total_vat": order.total_vat,
        "total_gross": order.total_gross,
        "source_filename": order.source_filename,
        "delivery": _delivery_summary_for_order(db, order_id),
        "lines": [
            {
                "id": l.id,
                "product_id": p.id,
                "line_number": l.line_number,
                "supplier_product_code": p.supplier_product_code,
                "description": l.description_snapshot,
                "quantity": l.quantity,
                "unit_code": l.unit_code,
                "unit_price": l.unit_price,
                "line_net": l.line_net,
                "vat_category": l.vat_category,
                "vat_rate": l.vat_rate,
                "line_vat": l.line_vat,
                "line_gross": l.line_gross,
                "is_zero_value": l.line_net == 0,
            }
            for l, p in lines
        ],
    }


@router.patch("/orders/{order_id}")
def update_order(order_id: int, payload: OrderUpdate, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Ordine non trovato")

    if payload.order_number is not None:
        number = payload.order_number.strip()
        duplicate = db.scalar(
            select(Order).where(Order.order_number == number, Order.id != order_id)
        )
        if duplicate:
            raise HTTPException(409, f"Esiste già un ordine con numero {number}")
        order.order_number = number

    if payload.order_date is not None:
        order.order_date = payload.order_date

    if payload.customer_id is not None:
        customer = db.get(Customer, payload.customer_id)
        if not customer:
            raise HTTPException(422, "Cliente non valido")
        order.customer_id = customer.id

    if payload.lines is not None:
        existing_lines = {
            line.id: line
            for line in db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)).all()
        }
        for change in payload.lines:
            line = existing_lines.get(change.id)
            if line is None:
                raise HTTPException(422, f"Riga ordine {change.id} non valida")

            if change.line_number is not None:
                line.line_number = change.line_number.strip()
            if change.description is not None:
                line.description_snapshot = change.description.strip() or None
            if change.quantity is not None:
                line.quantity = change.quantity
            if change.unit_code is not None:
                line.unit_code = normalize_unit_code(change.unit_code)
            if change.unit_price is not None:
                line.unit_price = change.unit_price
            if change.vat_category is not None:
                line.vat_category = change.vat_category.strip() or None
            if change.vat_rate is not None:
                line.vat_rate = change.vat_rate

            if change.supplier_product_code is not None:
                display_code = change.supplier_product_code.strip()
                if not display_code:
                    raise HTTPException(422, "Il codice fornitore non può essere vuoto")
                target = db.scalar(select(Product).where(_product_code_filter(display_code)))
                if target is None:
                    target = Product(
                        supplier_product_code=display_code,
                        description=line.description_snapshot,
                    )
                    db.add(target)
                    db.flush()
                line.product_id = target.id
                if line.description_snapshot:
                    target.description = line.description_snapshot
            elif line.product_id and line.description_snapshot:
                product = db.get(Product, line.product_id)
                if product:
                    product.description = line.description_snapshot

            # Manual edits use quantity × unit price as the line's commercial value.
            line.line_net = (line.quantity * line.unit_price).quantize(Decimal("0.01"))
            line.line_vat = (line.line_net * line.vat_rate / Decimal("100")).quantize(Decimal("0.01"))
            line.line_gross = line.line_net + line.line_vat

        db.flush()
        all_lines = db.scalars(select(OrderLine).where(OrderLine.order_id == order_id)).all()
        order.total_net = sum((line.line_net for line in all_lines), Decimal("0"))
        order.total_vat = sum((line.line_vat for line in all_lines), Decimal("0"))
        order.total_gross = sum((line.line_gross for line in all_lines), Decimal("0"))

    db.commit()
    refresh_order_delivery(db, order_id)
    db.commit()
    return order_detail(order_id, db)


@router.patch("/orders/{order_id}/delivery-lines/{order_line_id}")
def update_order_delivery_line(
    order_id: int,
    order_line_id: int,
    payload: OrderDeliveryLineUpdate,
    db: Session = Depends(get_db),
):
    """Set or clear the delivered quantity for one order line.

    ``null`` clears the manual override and returns the line to automatic DDT
    calculation. A numeric value is an explicit manual delivered quantity.
    """
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Ordine non trovato")
    line = db.get(OrderLine, order_line_id)
    if not line or line.order_id != order_id:
        raise HTTPException(404, "Riga ordine non trovata")

    if payload.delivered_quantity is not None:
        line.manual_delivered_quantity = payload.delivered_quantity
    else:
        line.manual_delivered_quantity = None

    db.commit()
    return order_detail(order_id, db)


@router.delete("/orders/{order_id}")
def delete_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order:
        raise HTTPException(404, "Ordine non trovato")

    product_ids = [line.product_id for line in order.lines]
    db.delete(order)
    db.flush()

    # Products exist only as a catalog derived from imported orders. Remove
    # entries that became orphaned after deleting the order.
    for product_id in set(product_ids):
        still_used = db.scalar(select(OrderLine.id).where(OrderLine.product_id == product_id).limit(1))
        if still_used is None:
            product = db.get(Product, product_id)
            if product:
                db.delete(product)

    db.commit()
    return {"status": "deleted", "id": order_id}


@router.get("/products")
def products(search: Optional[str] = None, db: Session = Depends(get_db)):
    stmt = (
        select(
            Product.id,
            Product.supplier_product_code,
            Product.description,
            func.coalesce(func.sum(OrderLine.quantity), 0).label("quantity"),
            func.count(func.distinct(OrderLine.order_id)).label("orders"),
            func.count(func.distinct(Order.customer_id)).label("customers"),
            func.coalesce(func.sum(OrderLine.line_net), 0).label("net"),
            func.coalesce(func.sum(OrderLine.line_vat), 0).label("vat"),
            func.coalesce(func.sum(OrderLine.line_gross), 0).label("gross"),
            func.coalesce(func.sum(case((OrderLine.line_net == 0, OrderLine.quantity), else_=0)), 0).label("zero_value_quantity"),
        )
        .outerjoin(OrderLine, OrderLine.product_id == Product.id)
        .outerjoin(Order, Order.id == OrderLine.order_id)
        .group_by(Product.id)
    )
    if search:
        raw = search.strip()
        term = f"%{raw}%"
        normalized_term = f"%{normalize_product_code(raw)}%"
        stmt = stmt.where(
            or_(
                _normalized_product_expr().like(normalized_term),
                Product.description.ilike(term),
            )
        )
    stmt = stmt.order_by(Product.supplier_product_code)
    return [dict(r._mapping) for r in db.execute(stmt)]


@router.get("/products/code-variants")
def product_code_variants(db: Session = Depends(get_db)):
    rows = db.execute(
        select(
            Product.id,
            Product.supplier_product_code,
            Product.description,
            ProductCodeVariant.raw_code,
            ProductCodeVariant.occurrences,
            ProductCodeVariant.first_seen_at,
            ProductCodeVariant.last_seen_at,
        )
        .join(ProductCodeVariant, ProductCodeVariant.product_id == Product.id)
        .order_by(Product.supplier_product_code, ProductCodeVariant.first_seen_at)
    ).all()
    grouped = {}
    for row in rows:
        item = grouped.setdefault(row.id, {
            "product_id": row.id,
            "canonical_code": row.supplier_product_code,
            "description": row.description,
            "variants": [],
        })
        item["variants"].append({
            "code": row.raw_code,
            "occurrences": row.occurrences,
            "first_seen_at": row.first_seen_at,
            "last_seen_at": row.last_seen_at,
        })
    # Only show products for which more than one written form has actually been received.
    return [item for item in grouped.values() if len(item["variants"]) > 1]


@router.get("/products/{product_ref}")
def product_detail(product_ref: str, db: Session = Depends(get_db)):
    product = db.get(Product, int(product_ref)) if product_ref.isdigit() else db.scalar(
        select(Product).where(_product_code_filter(product_ref))
    )
    if not product:
        raise HTTPException(404, "Prodotto non trovato")
    product_id = product.id

    summary = db.execute(
        select(
            func.coalesce(func.sum(OrderLine.quantity), 0).label("quantity"),
            func.coalesce(func.sum(OrderLine.line_net), 0).label("net"),
            func.coalesce(func.sum(OrderLine.line_vat), 0).label("vat"),
            func.coalesce(func.sum(OrderLine.line_gross), 0).label("gross"),
            func.count(func.distinct(OrderLine.order_id)).label("orders"),
            func.count(func.distinct(Order.customer_id)).label("customers"),
            func.coalesce(func.sum(case((OrderLine.line_net == 0, OrderLine.quantity), else_=0)), 0).label("zero_value_quantity"),
        )
        .select_from(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .where(OrderLine.product_id == product_id)
    ).one()

    weighted_qty = db.scalar(
        select(func.coalesce(func.sum(OrderLine.quantity), 0)).where(
            OrderLine.product_id == product_id, OrderLine.line_net > 0
        )
    ) or Decimal("0")
    valued_net = db.scalar(
        select(func.coalesce(func.sum(OrderLine.line_net), 0)).where(
            OrderLine.product_id == product_id, OrderLine.line_net > 0
        )
    ) or Decimal("0")
    avg_price = (valued_net / weighted_qty) if weighted_qty else Decimal("0")

    by_customer = db.execute(
        select(
            Customer.id.label("customer_id"),
            Customer.name.label("customer"),
            Customer.vat_number,
            OrderLine.unit_code,
            func.coalesce(func.sum(OrderLine.quantity), 0).label("quantity"),
            func.count(func.distinct(OrderLine.order_id)).label("orders"),
            func.coalesce(func.sum(OrderLine.line_net), 0).label("net"),
        )
        .join(Order, Order.customer_id == Customer.id)
        .join(OrderLine, OrderLine.order_id == Order.id)
        .where(OrderLine.product_id == product_id)
        .group_by(Customer.id, OrderLine.unit_code)
        .order_by(func.sum(OrderLine.line_net).desc())
    ).all()

    trend = db.execute(
        select(
            Order.order_date,
            OrderLine.unit_code,
            func.sum(OrderLine.quantity).label("quantity"),
            func.sum(OrderLine.line_net).label("net"),
            func.avg(OrderLine.unit_price).label("average_price"),
        )
        .join(OrderLine, OrderLine.order_id == Order.id)
        .where(OrderLine.product_id == product_id)
        .group_by(Order.order_date, OrderLine.unit_code)
        .order_by(Order.order_date)
    ).all()

    return {
        "id": product.id,
        "supplier_product_code": product.supplier_product_code,
        "description": product.description,
        "summary": {
            **dict(summary._mapping),
            "average_price": avg_price,
        },
        "by_customer": [dict(r._mapping) for r in by_customer],
        "trend": [dict(r._mapping) for r in trend],
        "recent_orders": [dict(r._mapping) for r in db.execute(
            select(Order.id.label("order_id"), Order.order_number, Order.order_date, Customer.name.label("customer"), OrderLine.quantity, OrderLine.unit_code, OrderLine.unit_price, OrderLine.line_net)
            .join(OrderLine, OrderLine.order_id == Order.id)
            .join(Customer, Customer.id == Order.customer_id)
            .where(OrderLine.product_id == product_id)
            .order_by(Order.order_date.desc(), Order.id.desc()).limit(10)
        ).all()],
    }


@router.get("/customers")
def customers(search: Optional[str] = None, db: Session = Depends(get_db)):
    order_totals = (
        select(
            Order.customer_id.label("customer_id"),
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.total_net), 0).label("net"),
            func.coalesce(func.sum(Order.total_gross), 0).label("gross"),
        )
        .group_by(Order.customer_id)
        .subquery()
    )
    line_totals = (
        select(
            Order.customer_id.label("customer_id"),
            func.count(func.distinct(OrderLine.product_id)).label("products"),
            func.coalesce(func.sum(OrderLine.quantity), 0).label("quantity"),
        )
        .join(OrderLine, OrderLine.order_id == Order.id)
        .group_by(Order.customer_id)
        .subquery()
    )
    stmt = (
        select(
            Customer.id,
            Customer.name,
            Customer.vat_number,
            Customer.peppol_endpoint,
            func.coalesce(order_totals.c.orders, 0).label("orders"),
            func.coalesce(line_totals.c.products, 0).label("products"),
            func.coalesce(line_totals.c.quantity, 0).label("quantity"),
            func.coalesce(order_totals.c.net, 0).label("net"),
            func.coalesce(order_totals.c.gross, 0).label("gross"),
        )
        .outerjoin(order_totals, order_totals.c.customer_id == Customer.id)
        .outerjoin(line_totals, line_totals.c.customer_id == Customer.id)
    )
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(or_(Customer.name.ilike(term), Customer.vat_number.ilike(term)))
    return [dict(r._mapping) for r in db.execute(stmt.order_by(Customer.name))]


@router.patch("/customers/{customer_id}")
def update_customer_name(customer_id: int, payload: CustomerNameUpdate, db: Session = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(404, "Cliente non trovato")

    name = payload.name.strip()
    if not name:
        raise HTTPException(422, "Il nome cliente non può essere vuoto")

    customer.name = normalize_customer_name(name)
    db.commit()
    db.refresh(customer)
    return {
        "id": customer.id,
        "name": customer.name,
        "vat_number": customer.vat_number,
        "peppol_endpoint": customer.peppol_endpoint,
    }


@router.get("/customers/{customer_id}")
def customer_detail(customer_id: int, db: Session = Depends(get_db)):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(404, "Cliente non trovato")

    orders = db.scalars(
        select(Order).where(Order.customer_id == customer_id).order_by(Order.order_date.desc())
    ).all()
    total_net = sum((o.total_net for o in orders), Decimal("0"))
    total_vat = sum((o.total_vat for o in orders), Decimal("0"))
    total_gross = sum((o.total_gross for o in orders), Decimal("0"))
    average_order = (total_net / len(orders)) if orders else Decimal("0")

    products = db.execute(
        select(
            Product.id.label("product_id"),
            Product.supplier_product_code,
            Product.description,
            OrderLine.unit_code,
            func.sum(OrderLine.quantity).label("quantity"),
            func.count(func.distinct(OrderLine.order_id)).label("orders"),
            func.sum(OrderLine.line_net).label("net"),
        )
        .join(OrderLine, OrderLine.product_id == Product.id)
        .join(Order, Order.id == OrderLine.order_id)
        .where(Order.customer_id == customer_id)
        .group_by(Product.id, OrderLine.unit_code)
        .order_by(func.sum(OrderLine.line_net).desc())
    ).all()

    return {
        "id": customer.id,
        "name": customer.name,
        "vat_number": customer.vat_number,
        "peppol_endpoint": customer.peppol_endpoint,
        "summary": {
            "orders": len(orders),
            "products": len({r.product_id for r in products}),
            "net": total_net,
            "vat": total_vat,
            "gross": total_gross,
            "average_order": average_order,
        },
        "products": [dict(r._mapping) for r in products],
        "trend": [
            {"period": period, "net": net, "orders": count}
            for period, net, count in db.execute(
                select(month_expr(Order.order_date), func.sum(Order.total_net), func.count(Order.id))
                .where(Order.customer_id == customer_id)
                .group_by(month_expr(Order.order_date))
                .order_by(month_expr(Order.order_date))
            ).all()
        ],
        "last_order": ({"id": orders[0].id, "order_number": orders[0].order_number, "order_date": orders[0].order_date, "total_gross": orders[0].total_gross} if orders else None),
        "orders": [
            {
                "id": o.id,
                "order_number": o.order_number,
                "order_date": o.order_date,
                "total_net": o.total_net,
                "total_vat": o.total_vat,
                "total_gross": o.total_gross,
            }
            for o in orders
        ],
    }


@router.get("/dashboard/financial-summary")
def dashboard_financial_summary(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
):
    """Financial KPIs based on their own source records, not mixed order totals."""
    invoice_stmt = select(
        func.coalesce(func.sum(SalesInvoice.net_amount), 0).label("invoice_net"),
        func.coalesce(func.sum(SalesInvoice.vat_amount), 0).label("invoice_vat"),
        func.count(SalesInvoice.id).label("invoice_count"),
    )
    if date_from:
        invoice_stmt = invoice_stmt.where(SalesInvoice.issue_date >= date_from)
    if date_to:
        invoice_stmt = invoice_stmt.where(SalesInvoice.issue_date <= date_to)
    invoice_totals = db.execute(invoice_stmt).one()

    payment_stmt = select(func.coalesce(func.sum(func.abs(BankMovement.amount)), 0)).where(
        BankMovement.direction == "entrata",
        or_(BankMovement.possible_duplicate.is_(False), BankMovement.duplicate_reviewed.is_(True)),
    )
    if date_from:
        payment_stmt = payment_stmt.where(BankMovement.booking_date >= date_from)
    if date_to:
        payment_stmt = payment_stmt.where(BankMovement.booking_date <= date_to)
    received_total = db.scalar(payment_stmt) or Decimal("0.00")

    return {
        "invoice_net": invoice_totals.invoice_net,
        "invoice_vat": invoice_totals.invoice_vat,
        "invoice_count": invoice_totals.invoice_count,
        "received_total": received_total,
    }


@router.get("/dashboard")
def dashboard(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer_id: Optional[int] = None,
    supplier_product_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    filters = _order_filters(date_from, date_to, customer_id)

    if supplier_product_code:
        filters.append(_product_code_filter(supplier_product_code))
        stmt = (
            select(
                func.coalesce(func.sum(OrderLine.line_net), 0).label("net"),
                func.coalesce(func.sum(OrderLine.line_vat), 0).label("vat"),
                func.coalesce(func.sum(OrderLine.line_gross), 0).label("gross"),
                func.count(func.distinct(Order.id)).label("orders"),
                func.count(func.distinct(Order.customer_id)).label("customers"),
                func.count(func.distinct(Product.id)).label("products"),
                func.coalesce(func.sum(case((OrderLine.line_net == 0, OrderLine.quantity), else_=0)), 0).label("zero_qty"),
            )
            .select_from(OrderLine)
            .join(Order, Order.id == OrderLine.order_id)
            .join(Product, Product.id == OrderLine.product_id)
        )
        if filters:
            stmt = stmt.where(and_(*filters))
        row = db.execute(stmt).one()
        return {
            "total_net": row.net,
            "total_vat": row.vat,
            "total_gross": row.gross,
            "orders": row.orders,
            "customers": row.customers,
            "products": row.products,
            "zero_value_quantity": row.zero_qty,
        }

    stmt = select(
        func.coalesce(func.sum(Order.total_net), 0).label("net"),
        func.coalesce(func.sum(Order.total_vat), 0).label("vat"),
        func.coalesce(func.sum(Order.total_gross), 0).label("gross"),
        func.count(Order.id).label("orders"),
        func.count(func.distinct(Order.customer_id)).label("customers"),
    )
    if filters:
        stmt = stmt.where(and_(*filters))
    row = db.execute(stmt).one()

    line_stmt = (
        select(
            func.count(func.distinct(OrderLine.product_id)).label("products"),
            func.coalesce(func.sum(case((OrderLine.line_net == 0, OrderLine.quantity), else_=0)), 0).label("zero_qty"),
        )
        .select_from(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
    )
    if filters:
        line_stmt = line_stmt.where(and_(*filters))
    line_row = db.execute(line_stmt).one()
    return {
        "total_net": row.net,
        "total_vat": row.vat,
        "total_gross": row.gross,
        "orders": row.orders,
        "customers": row.customers,
        "products": line_row.products,
        "zero_value_quantity": line_row.zero_qty,
    }


@router.get("/analytics/revenue-trend")
def revenue_trend(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer_id: Optional[int] = None,
    supplier_product_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    month = month_expr(Order.order_date).label("period")
    filters = _order_filters(date_from, date_to, customer_id)
    if supplier_product_code:
        filters.append(_product_code_filter(supplier_product_code))
        stmt = (
            select(
                month,
                func.sum(OrderLine.line_net).label("net"),
                func.sum(OrderLine.line_vat).label("vat"),
                func.sum(OrderLine.line_gross).label("gross"),
                func.count(func.distinct(Order.id)).label("orders"),
            )
            .select_from(OrderLine)
            .join(Order, Order.id == OrderLine.order_id)
            .join(Product, Product.id == OrderLine.product_id)
        )
    else:
        stmt = select(
            month,
            func.sum(Order.total_net).label("net"),
            func.sum(Order.total_vat).label("vat"),
            func.sum(Order.total_gross).label("gross"),
            func.count(Order.id).label("orders"),
        )
    if filters:
        stmt = stmt.where(and_(*filters))
    rows = db.execute(stmt.group_by(month).order_by(month)).all()
    return [dict(r._mapping) for r in rows]


@router.get("/analytics/quantity-trend")
def quantity_trend(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer_id: Optional[int] = None,
    supplier_product_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    month = month_expr(Order.order_date).label("period")
    stmt = (
        select(month, OrderLine.unit_code, func.sum(OrderLine.quantity).label("quantity"))
        .join(OrderLine, OrderLine.order_id == Order.id)
        .join(Product, Product.id == OrderLine.product_id)
    )
    filters = _order_filters(date_from, date_to, customer_id)
    if supplier_product_code:
        filters.append(_product_code_filter(supplier_product_code))
    if filters:
        stmt = stmt.where(and_(*filters))
    rows = db.execute(stmt.group_by(month, OrderLine.unit_code).order_by(month)).all()
    by_period = {}
    for period, unit_code, quantity in rows:
        item = by_period.setdefault(period, {"period": period})
        item[unit_code or "N/D"] = quantity
    return list(by_period.values())


@router.get("/analytics/top-products")
def top_products(
    metric: str = Query("net", pattern="^(net|quantity)$"),
    limit: int = Query(10, ge=1, le=100),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer_id: Optional[int] = None,
    supplier_product_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    metric_expr = func.sum(OrderLine.line_net) if metric == "net" else func.sum(OrderLine.quantity)
    stmt = (
        select(
            Product.id,
            Product.supplier_product_code,
            Product.description,
            OrderLine.unit_code,
            func.sum(OrderLine.quantity).label("quantity"),
            func.sum(OrderLine.line_net).label("net"),
        )
        .join(OrderLine, OrderLine.product_id == Product.id)
        .join(Order, Order.id == OrderLine.order_id)
    )
    filters = _order_filters(date_from, date_to, customer_id)
    if supplier_product_code:
        filters.append(_product_code_filter(supplier_product_code))
    if filters:
        stmt = stmt.where(and_(*filters))
    rows = db.execute(
        stmt.group_by(Product.id, OrderLine.unit_code)
        .order_by(metric_expr.desc())
        .limit(limit)
    ).all()
    return [dict(r._mapping) for r in rows]


@router.get("/analytics/top-customers")
def top_customers(
    metric: str = Query("net", pattern="^(net|orders)$"),
    limit: int = Query(10, ge=1, le=100),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer_id: Optional[int] = None,
    supplier_product_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    filters = _order_filters(date_from, date_to, customer_id)
    if supplier_product_code:
        filters.append(_product_code_filter(supplier_product_code))
        stmt = (
            select(
                Customer.id,
                Customer.name,
                Customer.vat_number,
                func.count(func.distinct(Order.id)).label("orders"),
                func.sum(OrderLine.line_net).label("net"),
            )
            .select_from(OrderLine)
            .join(Order, Order.id == OrderLine.order_id)
            .join(Customer, Customer.id == Order.customer_id)
            .join(Product, Product.id == OrderLine.product_id)
        )
        metric_expr = func.sum(OrderLine.line_net) if metric == "net" else func.count(func.distinct(Order.id))
    else:
        stmt = (
            select(
                Customer.id,
                Customer.name,
                Customer.vat_number,
                func.count(Order.id).label("orders"),
                func.sum(Order.total_net).label("net"),
            )
            .join(Order, Order.customer_id == Customer.id)
        )
        metric_expr = func.sum(Order.total_net) if metric == "net" else func.count(Order.id)
    if filters:
        stmt = stmt.where(and_(*filters))
    rows = db.execute(stmt.group_by(Customer.id).order_by(metric_expr.desc()).limit(limit)).all()
    return [dict(r._mapping) for r in rows]


@router.get("/analytics/product-customer")
def product_customer(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer_id: Optional[int] = None,
    product_id: Optional[int] = None,
    supplier_product_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    stmt = (
        select(
            Customer.id.label("customer_id"),
            Customer.name.label("customer"),
            Product.id.label("product_id"),
            Product.supplier_product_code,
            Product.description,
            OrderLine.unit_code,
            func.sum(OrderLine.quantity).label("quantity"),
            func.sum(OrderLine.line_net).label("net"),
        )
        .join(Order, Order.customer_id == Customer.id)
        .join(OrderLine, OrderLine.order_id == Order.id)
        .join(Product, Product.id == OrderLine.product_id)
    )
    filters = _order_filters(date_from, date_to, customer_id)
    if product_id:
        filters.append(Product.id == product_id)
    if supplier_product_code:
        filters.append(_product_code_filter(supplier_product_code))
    if filters:
        stmt = stmt.where(and_(*filters))
    rows = db.execute(
        stmt.group_by(Customer.id, Product.id, OrderLine.unit_code)
        .order_by(Customer.name, Product.supplier_product_code)
    ).all()
    return [dict(r._mapping) for r in rows]


@router.get("/analytics/zero-value")
def zero_value(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    customer_id: Optional[int] = None,
    supplier_product_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    stmt = (
        select(
            OrderLine.id,
            Product.id.label("product_id"),
            Product.supplier_product_code,
            OrderLine.description_snapshot.label("description"),
            Customer.id.label("customer_id"),
            Customer.name.label("customer"),
            Order.id.label("order_id"),
            Order.order_number,
            Order.order_date,
            OrderLine.quantity,
            OrderLine.unit_code,
        )
        .join(Product, Product.id == OrderLine.product_id)
        .join(Order, Order.id == OrderLine.order_id)
        .join(Customer, Customer.id == Order.customer_id)
        .where(OrderLine.line_net == 0)
    )
    filters = _order_filters(date_from, date_to, customer_id)
    if supplier_product_code:
        filters.append(_product_code_filter(supplier_product_code))
    if filters:
        stmt = stmt.where(and_(*filters))
    rows = db.execute(stmt.order_by(Order.order_date.desc(), OrderLine.id)).all()
    return [dict(r._mapping) for r in rows]



@router.get("/ddts")
def list_ddts(
    search: Optional[str] = None,
    customer_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    stmt = select(DeliveryNote, Customer, Order).outerjoin(Customer, DeliveryNote.customer_id == Customer.id).outerjoin(Order, DeliveryNote.order_id == Order.id)
    filters = []
    if customer_id: filters.append(DeliveryNote.customer_id == customer_id)
    if date_from: filters.append(DeliveryNote.ddt_date >= date_from)
    if date_to: filters.append(DeliveryNote.ddt_date <= date_to)
    if status: filters.append(DeliveryNote.status == status)
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(DeliveryNote.ddt_number.ilike(term), DeliveryNote.order_reference.ilike(term), Customer.name.ilike(term), Order.order_number.ilike(term)))
    if filters: stmt = stmt.where(and_(*filters))
    rows = db.execute(stmt.order_by(DeliveryNote.ddt_date.desc(), DeliveryNote.id.desc())).all()
    result=[]
    for d,c,o in rows:
        qty=sum((x.quantity for x in d.lines), Decimal("0"))
        result.append({"id":d.id,"ddt_number":d.ddt_number,"ddt_date":d.ddt_date,"customer_id":c.id if c else None,"customer_name":c.name if c else None,
                       "order_id":o.id if o else None,"order_number":o.order_number if o else None,"order_reference":d.order_reference,
                       "status":d.status,"source_filename":d.source_filename,"line_count":len(d.lines),"quantity":qty})
    return result


@router.get("/ddts/{ddt_id}/pdf")
def ddt_pdf(ddt_id: int, db: Session = Depends(get_db)):
    ddt = db.get(DeliveryNote, ddt_id)
    if not ddt:
        raise HTTPException(404, "DDT non trovato")
    try:
        data = load_document(build_key("ddt", ddt.source_hash, ".pdf"))
    except StorageError as exc:
        raise HTTPException(502, str(exc)) from exc
    if data is None:
        raise HTTPException(404, "PDF originale del DDT non trovato nell'archivio documenti")
    filename = Path(ddt.source_filename).name.replace('"', "")
    return Response(content=data, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.get("/ddts/{ddt_id}")
def ddt_detail(ddt_id: int, db: Session = Depends(get_db)):
    d = db.get(DeliveryNote, ddt_id)
    if not d: raise HTTPException(404, "DDT non trovato")
    c = db.get(Customer, d.customer_id) if d.customer_id else None
    o = db.get(Order, d.order_id) if d.order_id else None
    lines=[]
    for l in d.lines:
        p=db.get(Product,l.product_id) if l.product_id else None
        ol=db.get(OrderLine,l.order_line_id) if l.order_line_id else None
        lines.append({"id":l.id,"supplier_product_code":p.supplier_product_code if p else l.supplier_product_code,"description":l.description,
                      "quantity":l.quantity,"unit_code":l.unit_code,"lot_number":l.lot_number,"expiry_date":l.expiry_date,
                      "is_gift":l.is_gift,"is_unordered":l.is_unordered,"product_id":l.product_id,"order_line_id":l.order_line_id,
                      "order_line_quantity":ol.quantity if ol else None})
    return {"id":d.id,"ddt_number":d.ddt_number,"ddt_date":d.ddt_date,"customer":{"id":c.id,"name":c.name,"vat_number":c.vat_number} if c else None,
            "order_id":o.id if o else None,"order_number":o.order_number if o else None,"order_reference":d.order_reference,
            "status":d.status,"source_filename":d.source_filename,"lines":lines}


class DDTLinkPayload(BaseModel):
    order_id: Optional[int] = None


class DDTLineGiftPayload(BaseModel):
    is_gift: bool


class DDTLineUpdate(BaseModel):
    id: int
    supplier_product_code: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    quantity: Optional[Decimal] = Field(None, ge=0)
    unit_code: Optional[str] = None
    lot_number: Optional[str] = None
    expiry_date: Optional[date] = None
    is_gift: Optional[bool] = None


class DDTUpdate(BaseModel):
    ddt_number: Optional[str] = Field(None, min_length=1, max_length=128)
    ddt_date: Optional[date] = None
    customer_id: Optional[int] = None
    order_id: Optional[int] = None
    lines: Optional[list[DDTLineUpdate]] = None



@router.get("/ddts/{ddt_id}/orders")
def ddt_manual_order_search(
    ddt_id: int,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """Search orders for a manual DDT link without relying on customer_id equality.

    This is intentionally broader than the automatic matcher: legacy databases can
    contain duplicate customer records or customer names coming from documents with
    different prefixes. Results are ranked so the same normalized customer and a
    format-compatible order reference appear first.
    """
    d = db.get(DeliveryNote, ddt_id)
    if not d:
        raise HTTPException(404, "DDT non trovato")

    d_customer = db.get(Customer, d.customer_id) if d.customer_id else None
    d_customer_name = normalize_customer_name(d_customer.name) if d_customer else ""
    d_customer_vat = (d_customer.vat_number or "").strip().upper() if d_customer else ""
    raw_search = (search or "").strip()
    search_upper = raw_search.upper()

    rows = db.execute(
        select(Order, Customer).join(Customer, Order.customer_id == Customer.id)
    ).all()

    candidates = []
    for order, customer in rows:
        customer_name = normalize_customer_name(customer.name)
        customer_vat = (customer.vat_number or "").strip().upper()
        same_customer = bool(
            d.customer_id and order.customer_id == d.customer_id
        ) or bool(
            d_customer_name and customer_name and d_customer_name.casefold() == customer_name.casefold()
        ) or bool(
            d_customer_vat and customer_vat and d_customer_vat == customer_vat
        )
        reference_match = order_references_match(d.order_reference, order.order_number)

        if raw_search:
            direct_match = (
                search_upper in (order.order_number or "").upper()
                or search_upper in customer_name.upper()
                or search_upper in customer_vat
            )
            reference_search_match = order_references_match(raw_search, order.order_number)
            if not direct_match and not reference_search_match:
                continue

        score = (10000 if same_customer else 0) + (5000 if reference_match else 0)
        if raw_search:
            if search_upper in (order.order_number or "").upper():
                score += 3000
            if search_upper in customer_name.upper():
                score += 1500
            if search_upper in customer_vat:
                score += 1000
            if order_references_match(raw_search, order.order_number):
                score += 4000
        score += int(order.order_date.strftime("%Y%m%d") if order.order_date else "0")
        candidates.append((score, order, customer, reference_match, same_customer))

    candidates.sort(key=lambda x: x[0], reverse=True)
    result = []
    for _, order, customer, reference_match, same_customer in candidates[:limit]:
        result.append({
            "id": order.id,
            "order_number": order.order_number,
            "order_date": order.order_date,
            "customer_id": customer.id,
            "customer_name": customer.name,
            "customer_vat": customer.vat_number,
            "reference_match": reference_match,
            "same_customer": same_customer,
        })
    return result


@router.get("/ddts/{ddt_id}/suggestions")
def ddt_order_suggestions(ddt_id: int, db: Session = Depends(get_db)):
    d = db.get(DeliveryNote, ddt_id)
    if not d:
        raise HTTPException(404, "DDT non trovato")
    if d.order_id:
        return []

    d_customer = db.get(Customer, d.customer_id) if d.customer_id else None
    d_customer_name = normalize_customer_name(d_customer.name) if d_customer else ""
    d_customer_vat = (d_customer.vat_number or "").strip().upper() if d_customer else ""
    d_codes = {normalize_product_code(x.supplier_product_code) for x in d.lines}
    candidates = []

    for order in db.scalars(select(Order).order_by(Order.order_date.desc())).all():
        customer = db.get(Customer, order.customer_id)
        customer_name = normalize_customer_name(customer.name) if customer else ""
        customer_vat = (customer.vat_number or "").strip().upper() if customer else ""
        same_customer = bool(d.customer_id and order.customer_id == d.customer_id) or bool(
            d_customer_name and customer_name and d_customer_name.casefold() == customer_name.casefold()
        ) or bool(d_customer_vat and customer_vat and d_customer_vat == customer_vat)

        order_codes = {normalize_product_code(x.product.supplier_product_code) for x in order.lines if x.product}
        overlap = len(d_codes & order_codes)
        days = abs((d.ddt_date - order.order_date).days)
        reference_match = order_references_match(d.order_reference, order.order_number)
        score = (100 * int(same_customer)) + overlap * 30 + max(0, 30 - min(days, 30)) + (200 if reference_match else 0)
        if overlap == 0 and not reference_match:
            score = max(0, score - 20)
        candidates.append((score, order, overlap, same_customer, reference_match))

    candidates.sort(key=lambda x: (x[0], x[1].order_date), reverse=True)
    return [{
        "id":o.id,
        "order_number":o.order_number,
        "order_date":o.order_date,
        "customer_id":o.customer_id,
        "match_products":overlap,
        "reference_match":reference_match,
        "same_customer":same_customer,
        "score":score,
    } for score,o,overlap,same_customer,reference_match in candidates[:5]]


@router.patch("/ddts/{ddt_id}")
def update_ddt(ddt_id: int, payload: DDTUpdate, db: Session = Depends(get_db)):
    d = db.get(DeliveryNote, ddt_id)
    if not d: raise HTTPException(404, "DDT non trovato")
    if payload.ddt_number is not None: d.ddt_number = payload.ddt_number.strip()
    if payload.ddt_date is not None: d.ddt_date = payload.ddt_date
    if payload.customer_id is not None:
        c=db.get(Customer,payload.customer_id)
        if not c: raise HTTPException(422,"Cliente non valido")
        d.customer_id=c.id
    if payload.order_id is not None:
        order=db.get(Order,payload.order_id)
        if not order: raise HTTPException(422,"Ordine non valido")
        d.order_id=order.id
    if payload.lines is not None:
        existing={x.id:x for x in d.lines}
        for change in payload.lines:
            line=existing.get(change.id)
            if not line: raise HTTPException(422,f"Riga DDT {change.id} non valida")
            if change.supplier_product_code is not None:
                line.supplier_product_code=change.supplier_product_code.strip()
                product=db.scalar(select(Product).where(_product_code_filter(line.supplier_product_code)))
                line.product_id=product.id if product else None
            if change.description is not None: line.description=change.description.strip() or None
            if change.quantity is not None: line.quantity=change.quantity
            if change.unit_code is not None: line.unit_code=normalize_unit_code(change.unit_code)
            if change.lot_number is not None: line.lot_number=change.lot_number.strip() or None
            if change.expiry_date is not None: line.expiry_date=change.expiry_date
            if change.is_gift is not None: line.is_gift=change.is_gift
            if line.is_gift: line.order_line_id=None; line.is_unordered=False
    db.flush()
    if d.order_id: refresh_order_delivery(db,d.order_id)
    refresh_ddt_status(db,d)
    db.commit()
    return ddt_detail(ddt_id,db)


@router.patch("/ddts/{ddt_id}/link")
def link_ddt(ddt_id: int, payload: DDTLinkPayload, db: Session = Depends(get_db)):
    d = db.get(DeliveryNote, ddt_id)
    if not d: raise HTTPException(404, "DDT non trovato")
    order = db.get(Order, payload.order_id) if payload.order_id else None
    if payload.order_id and not order: raise HTTPException(404, "Ordine non trovato")
    old_order_id = d.order_id
    relink_ddt(db, d, order)
    if old_order_id and old_order_id != (order.id if order else None):
        refresh_order_delivery(db, old_order_id)
        db.commit()
    return ddt_detail(ddt_id, db)


@router.patch("/ddts/{ddt_id}/lines/{line_id}/gift")
def mark_ddt_line_gift(ddt_id: int, line_id: int, payload: DDTLineGiftPayload, db: Session = Depends(get_db)):
    d = db.get(DeliveryNote, ddt_id)
    line = db.get(DeliveryNoteLine, line_id)
    if not d or not line or line.ddt_id != d.id: raise HTTPException(404, "Riga DDT non trovata")
    old_order = d.order_id
    line.is_gift = payload.is_gift
    if payload.is_gift:
        line.order_line_id = None
        line.is_unordered = False
    if old_order:
        refresh_order_delivery(db, old_order)
    refresh_ddt_status(db, d)
    db.commit()
    return ddt_detail(ddt_id, db)


@router.delete("/ddts/{ddt_id}")
def delete_ddt(ddt_id: int, db: Session = Depends(get_db)):
    d=db.get(DeliveryNote,ddt_id)
    if not d: raise HTTPException(404,"DDT non trovato")
    order_id=d.order_id
    db.delete(d); db.commit()
    if order_id:
        refresh_order_delivery(db, order_id); db.commit()
    return {"status":"DELETED","id":ddt_id}


@router.post("/ddts/upload")
def upload_ddt(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "È consentito solo un file PDF")
    data = file.file.read()
    if not data:
        raise HTTPException(400, "Il file è vuoto")
    _archive("ddt", data, ".pdf", "application/pdf")
    with tempfile.TemporaryDirectory() as tmp:
        dest = Path(tmp) / Path(file.filename).name
        dest.write_bytes(data)
        try:
            ddt, warnings = import_ddt(dest, db)
            return {
                "status": "SUCCESS",
                "ddt_id": ddt.id,
                "ddt_number": ddt.ddt_number,
                "line_count": len(ddt.lines),
                "warnings": warnings,
            }
        except DuplicateDDTError as exc: raise HTTPException(409, str(exc)) from exc
        except Exception as exc: raise HTTPException(400, str(exc)) from exc


@router.post("/ddts/upload-multiple")
def upload_multiple_ddts(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Importa più PDF DDT o PDF contenuti in uno ZIP e restituisce un esito per file."""
    if not files:
        raise HTTPException(400, "Seleziona almeno un PDF o un file ZIP")
    results = []
    pdf_payloads = []
    for uploaded in files:
        name = Path(uploaded.filename or "file").name
        data = uploaded.file.read()
        if name.lower().endswith(".pdf"):
            pdf_payloads.append((name, data))
        elif name.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for member in archive.infolist():
                        if member.is_dir() or not member.filename.lower().endswith(".pdf"):
                            continue
                        # Evita archivi con percorsi pericolosi: viene usato solo il nome del file.
                        pdf_payloads.append((Path(member.filename).name, archive.read(member)))
            except zipfile.BadZipFile as exc:
                results.append({"file": name, "status": "ERRORE", "message": "Archivio ZIP non valido"})
        else:
            results.append({"file": name, "status": "ERRORE", "message": "Formato non supportato: seleziona PDF o ZIP"})
    if not pdf_payloads and not results:
        raise HTTPException(400, "Nessun PDF trovato nei file selezionati")
    for name, data in pdf_payloads:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                dest = Path(tmp) / name
                dest.write_bytes(data)
                save_document("ddt", data, ".pdf", "application/pdf")
                ddt, warnings = import_ddt(dest, db)
                results.append({"file": name, "status": "IMPORTATO", "ddt_number": ddt.ddt_number, "ddt_id": ddt.id, "line_count": len(ddt.lines), "message": "; ".join(warnings) if warnings else "Importazione completata"})
        except DuplicateDDTError as exc:
            db.rollback()
            results.append({"file": name, "status": "DUPLICATO", "message": str(exc)})
        except Exception as exc:
            db.rollback()
            results.append({"file": name, "status": "ERRORE", "message": str(exc)})
    success = sum(1 for x in results if x["status"] == "IMPORTATO")
    duplicates = sum(1 for x in results if x["status"] == "DUPLICATO")
    errors = sum(1 for x in results if x["status"] == "ERRORE")
    return {"total": len(results), "success": success, "duplicates": duplicates, "errors": errors, "items": results, "message": f"Elaborati {len(results)} PDF: {success} importati, {duplicates} duplicati, {errors} errori."}


@router.get("/imports")
def imports(db: Session = Depends(get_db)):
    rows = db.scalars(select(ImportJob).order_by(ImportJob.started_at.desc())).all()
    return [
        {
            "id": x.id,
            "filename": x.filename,
            "status": x.status,
            "error_message": x.error_message,
            "warnings": x.warnings,
            "started_at": x.started_at,
            "completed_at": x.completed_at,
        }
        for x in rows
    ]


@router.post("/imports/upload")
def upload_import(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".xml"):
        raise HTTPException(400, "È consentito solo un file XML")
    data = file.file.read()
    if not data:
        raise HTTPException(400, "Il file è vuoto")
    _archive("orders", data, ".xml", "application/xml")
    with tempfile.TemporaryDirectory() as tmpdir:
        dest = Path(tmpdir) / Path(file.filename).name
        dest.write_bytes(data)
        try:
            order, warnings = import_xml(dest, db)
            return {
                "status": "SUCCESS",
                "order_id": order.id,
                "order_number": order.order_number,
                "warnings": warnings,
            }
        except DuplicateOrderError as exc:
            raise HTTPException(409, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc


@router.post("/imports/upload-multiple")
def upload_multiple_imports(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """Importa più XML Peppol oppure un archivio ZIP contenente XML."""
    if not files:
        raise HTTPException(400, "Seleziona almeno un file XML o ZIP.")
    results = []
    with tempfile.TemporaryDirectory(prefix="peppol-bulk-") as tmpdir:
        root = Path(tmpdir)
        xml_paths: list[Path] = []
        for uploaded in files:
            name = Path(uploaded.filename or "").name
            if not name:
                continue
            content = uploaded.file.read()
            if name.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(content)) as archive:
                        for member in archive.infolist():
                            if member.is_dir() or not member.filename.lower().endswith(".xml"):
                                continue
                            # Use only the basename: never extract archive paths directly.
                            safe_name = Path(member.filename).name
                            if not safe_name:
                                continue
                            dest_dir = root / f"file_{len(xml_paths):05d}"
                            dest_dir.mkdir(parents=True, exist_ok=True)
                            dest = dest_dir / safe_name
                            dest.write_bytes(archive.read(member))
                            xml_paths.append(dest)
                except zipfile.BadZipFile:
                    results.append({"file": name, "status": "ERROR", "message": "Archivio ZIP non valido."})
            elif name.lower().endswith(".xml"):
                dest_dir = root / f"file_{len(xml_paths):05d}"
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest = dest_dir / name
                dest.write_bytes(content)
                xml_paths.append(dest)
            else:
                results.append({"file": name, "status": "ERROR", "message": "Formato non supportato: seleziona XML o ZIP."})
        for path in xml_paths:
            original_name = path.name
            try:
                save_document("orders", path.read_bytes(), ".xml", "application/xml")
                order, warnings = import_xml(path, db)
                results.append({"file": original_name, "status": "SUCCESS", "order_id": order.id, "order_number": order.order_number, "warnings": warnings, "message": "Ordine importato correttamente."})
            except DuplicateOrderError as exc:
                results.append({"file": original_name, "status": "DUPLICATE", "message": str(exc)})
            except Exception as exc:
                results.append({"file": original_name, "status": "ERROR", "message": str(exc)})
    success = sum(1 for item in results if item["status"] == "SUCCESS")
    duplicates = sum(1 for item in results if item["status"] == "DUPLICATE")
    errors = sum(1 for item in results if item["status"] == "ERROR")
    return {"total": len(results), "success": success, "duplicates": duplicates, "errors": errors, "items": results, "message": f"Importazione massiva conclusa: {success} importati, {duplicates} duplicati, {errors} errori."}



@router.get("/exports/ddts")
def export_ddts(format: str = Query("xlsx", pattern="^(csv|xlsx)$"), db: Session = Depends(get_db)):
    rows=db.execute(select(DeliveryNote,Customer,Order).outerjoin(Customer,DeliveryNote.customer_id==Customer.id).outerjoin(Order,DeliveryNote.order_id==Order.id).order_by(DeliveryNote.ddt_date.desc())).all()
    return export_response("ddt", ["Numero DDT","Data","Cliente","Ordine","Riferimento ordine","Stato","Righe"], [
        [d.ddt_number,d.ddt_date,c.name if c else "",o.order_number if o else "",d.order_reference or "",d.status,len(d.lines)] for d,c,o in rows
    ], format)


@router.get("/exports/orders")
def export_orders(
    format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
    search: Optional[str] = None, customer_id: Optional[int] = None,
    date_from: Optional[date] = None, date_to: Optional[date] = None,
    db: Session = Depends(get_db),
):
    stmt = select(Order, Customer).join(Customer, Order.customer_id == Customer.id)
    filters = _order_filters(date_from, date_to, customer_id)
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(Order.order_number.ilike(term), Customer.name.ilike(term), Customer.vat_number.ilike(term)))
    if filters:
        stmt = stmt.where(and_(*filters))
    rows = db.execute(stmt.order_by(Order.order_date.desc(), Order.id.desc())).all()
    return export_response("ordini", ["Numero ordine","Data","Cliente","P.IVA","Imponibile","IVA","Totale","Valuta"], [
        [o.order_number, o.order_date.isoformat(), c.name, c.vat_number, o.total_net, o.total_vat, o.total_gross, o.currency] for o,c in rows
    ], format)


@router.get("/exports/products")
def export_products(
    format: str = Query("xlsx", pattern="^(csv|xlsx)$"), search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    stmt = (select(Product.supplier_product_code, Product.description,
                   func.coalesce(func.sum(OrderLine.quantity),0).label("quantity"),
                   func.count(func.distinct(OrderLine.order_id)).label("orders"),
                   func.count(func.distinct(Order.customer_id)).label("customers"),
                   func.coalesce(func.sum(OrderLine.line_net),0).label("net"))
            .outerjoin(OrderLine, OrderLine.product_id == Product.id)
            .outerjoin(Order, Order.id == OrderLine.order_id)
            .group_by(Product.id))
    if search:
        raw=search.strip(); term=f"%{raw}%"; normalized=f"%{normalize_product_code(raw)}%"
        stmt=stmt.where(or_(_normalized_product_expr().like(normalized), Product.description.ilike(term)))
    rows=db.execute(stmt.order_by(Product.supplier_product_code)).all()
    return export_response("prodotti", ["Codice fornitore","Descrizione","Quantità ordinata","Ordini","Clienti","Fatturato netto"], [
        [r.supplier_product_code,r.description,r.quantity,r.orders,r.customers,r.net] for r in rows
    ], format)


@router.get("/exports/customers")
def export_customers(
    format: str = Query("xlsx", pattern="^(csv|xlsx)$"), search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    orders_sub=(select(Order.customer_id.label("customer_id"), func.count(Order.id).label("orders"), func.coalesce(func.sum(Order.total_net),0).label("net")).group_by(Order.customer_id).subquery())
    lines_sub=(select(Order.customer_id.label("customer_id"), func.count(func.distinct(OrderLine.product_id)).label("products"), func.coalesce(func.sum(OrderLine.quantity),0).label("quantity")).join(OrderLine,OrderLine.order_id==Order.id).group_by(Order.customer_id).subquery())
    stmt=(select(Customer.name,Customer.vat_number,func.coalesce(orders_sub.c.orders,0).label("orders"),func.coalesce(lines_sub.c.products,0).label("products"),func.coalesce(lines_sub.c.quantity,0).label("quantity"),func.coalesce(orders_sub.c.net,0).label("net"))
          .outerjoin(orders_sub,orders_sub.c.customer_id==Customer.id).outerjoin(lines_sub,lines_sub.c.customer_id==Customer.id))
    if search:
        term=f"%{search.strip()}%"; stmt=stmt.where(or_(Customer.name.ilike(term),Customer.vat_number.ilike(term)))
    rows=db.execute(stmt.order_by(Customer.name)).all()
    return export_response("clienti", ["Cliente","P.IVA","Ordini","Prodotti","Quantità","Fatturato netto"], [[r.name,r.vat_number,r.orders,r.products,r.quantity,r.net] for r in rows], format)


@router.get("/exports/analytics")
def export_analytics(
    format: str = Query("xlsx", pattern="^(csv|xlsx)$"),
    date_from: Optional[date] = None, date_to: Optional[date] = None,
    customer_id: Optional[int] = None, supplier_product_code: Optional[str] = None,
    db: Session = Depends(get_db),
):
    stmt=(select(Customer.name.label("customer"), Product.supplier_product_code, Product.description, OrderLine.unit_code, func.sum(OrderLine.quantity).label("quantity"), func.sum(OrderLine.line_net).label("net"))
          .join(Order,Order.customer_id==Customer.id).join(OrderLine,OrderLine.order_id==Order.id).join(Product,Product.id==OrderLine.product_id))
    filters=_order_filters(date_from,date_to,customer_id)
    if supplier_product_code: filters.append(_product_code_filter(supplier_product_code))
    if filters: stmt=stmt.where(and_(*filters))
    rows=db.execute(stmt.group_by(Customer.id,Product.id,OrderLine.unit_code).order_by(Customer.name,Product.supplier_product_code)).all()
    return export_response("analisi", ["Cliente","Codice fornitore","Descrizione","UM","Quantità","Fatturato netto"], [[r.customer,r.supplier_product_code,r.description,r.unit_code,r.quantity,r.net] for r in rows], format)



def _original_xml_path(order: Order, folder: str) -> Optional[Path]:
    """Scarica l'XML originale dall'archivio documenti in una cartella temporanea."""
    try:
        data = load_document(build_key("orders", order.source_hash, ".xml"))
    except StorageError as exc:
        raise HTTPException(502, str(exc)) from exc
    if data is None:
        return None
    path = Path(folder) / "ordine.xml"
    path.write_bytes(data)
    return path


@router.get("/orders/{order_id}/restore-preview")
def restore_order_preview(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order: raise HTTPException(404, "Ordine non trovato")
    with tempfile.TemporaryDirectory() as tmp:
        path = _original_xml_path(order, tmp)
        if not path: raise HTTPException(404, "XML originale non disponibile nell'archivio documenti")
        parsed = parse_peppol_order(path)
    current = order_detail(order_id, db)
    original = {
        "order_number": parsed.order_number, "order_date": parsed.order_date, "customer_name": parsed.customer.name,
        "customer_vat": parsed.customer.vat_number, "currency": parsed.currency, "total_net": parsed.total_net,
        "total_vat": parsed.total_vat, "total_gross": parsed.total_gross,
        "lines": [{"line_number": x.line_number, "supplier_product_code": x.supplier_product_code, "description": x.description,
                   "quantity": x.quantity, "unit_code": normalize_unit_code(x.unit_code), "unit_price": x.unit_price,
                   "vat_category": x.vat_category, "vat_rate": x.vat_rate, "line_net": x.line_net, "line_vat": x.line_vat, "line_gross": x.line_gross} for x in parsed.lines]
    }
    return {"available": True, "source_file": order.source_filename, "current": current, "original": original}


@router.post("/orders/{order_id}/restore")
def restore_order(order_id: int, db: Session = Depends(get_db)):
    order = db.get(Order, order_id)
    if not order: raise HTTPException(404, "Ordine non trovato")
    with tempfile.TemporaryDirectory() as tmp:
        path = _original_xml_path(order, tmp)
        if not path: raise HTTPException(404, "XML originale non disponibile nell'archivio documenti")
        parsed = parse_peppol_order(path)
    vat_key = normalize_vat_number(parsed.customer.vat_number)
    customer = None
    if vat_key:
        customer = next((candidate for candidate in db.scalars(select(Customer)).all() if normalize_vat_number(candidate.vat_number) == vat_key), None)
    if customer is None:
        customer = Customer(name=normalize_customer_name(parsed.customer.name), vat_number=parsed.customer.vat_number.strip().upper(), peppol_endpoint=parsed.customer.peppol_endpoint)
        db.add(customer); db.flush()
    order.order_number = parsed.order_number; order.order_date = parsed.order_date; order.customer_id = customer.id; order.currency = parsed.currency
    order.total_net = parsed.total_net; order.total_vat = parsed.total_vat; order.total_gross = parsed.total_gross
    for line in list(order.lines): db.delete(line)
    db.flush()
    for line in parsed.lines:
        normalized = normalize_product_code(line.supplier_product_code)
        product = db.scalar(select(Product).where(_normalized_product_expr() == normalized))
        if product is None:
            product = Product(supplier_product_code=line.supplier_product_code, description=line.description); db.add(product); db.flush()
        product.description = line.description
        db.add(OrderLine(order_id=order.id, product_id=product.id, line_number=line.line_number, description_snapshot=line.description,
                         quantity=line.quantity, unit_code=normalize_unit_code(line.unit_code), unit_price=line.unit_price,
                         line_net=line.line_net, vat_category=line.vat_category, vat_rate=line.vat_rate, line_vat=line.line_vat, line_gross=line.line_gross))
    db.commit()
    refresh_order_delivery(db, order.id)
    db.commit()
    return {"status":"RESTORED", "order_id": order.id, "order_number": order.order_number}


@router.get("/search")
def global_search(q: str = Query(..., min_length=2), limit: int = Query(8, ge=1, le=20), db: Session = Depends(get_db)):
    term = f"%{q.strip()}%"; normalized = f"%{normalize_product_code(q)}%"
    orders = db.execute(select(Order, Customer).join(Customer).where(or_(Order.order_number.ilike(term), Customer.name.ilike(term), Customer.vat_number.ilike(term))).order_by(Order.order_date.desc()).limit(limit)).all()
    customers = db.scalars(select(Customer).where(or_(Customer.name.ilike(term), Customer.vat_number.ilike(term))).order_by(Customer.name).limit(limit)).all()
    products = db.scalars(select(Product).where(or_(_normalized_product_expr().like(normalized), Product.description.ilike(term))).order_by(Product.supplier_product_code).limit(limit)).all()
    return {"orders":[{"id":o.id,"order_number":o.order_number,"order_date":o.order_date,"customer":c.name} for o,c in orders],
            "customers":[{"id":c.id,"name":c.name,"vat_number":c.vat_number} for c in customers],
            "products":[{"id":x.id,"supplier_product_code":x.supplier_product_code,"description":x.description} for x in products]}


def _period_metrics(db: Session, start: date, end: date):
    orders = db.scalars(select(Order).where(Order.order_date >= start, Order.order_date <= end)).all()
    return {"net": float(sum((o.total_net for o in orders), Decimal("0"))), "gross": float(sum((o.total_gross for o in orders), Decimal("0"))),
            "orders": len(orders), "customers": len({o.customer_id for o in orders})}


def _pct_change(current: float, previous: float):
    if previous == 0: return None if current != 0 else 0.0
    return ((current - previous) / previous) * 100



@router.get("/dashboard/delivery-summary")
def dashboard_delivery_summary(db: Session = Depends(get_db)):
    orders = db.scalars(select(Order)).all()
    open_orders = 0
    partial = 0
    complete = 0
    over = 0
    residual = Decimal("0")
    for order in orders:
        summary = _delivery_summary_for_order(db, order.id)
        if summary["status"] == "NON_CONSEGNATO":
            open_orders += 1
        elif summary["status"] == "PARZIALMENTE_CONSEGNATO":
            partial += 1
        elif summary["status"] == "COMPLETAMENTE_CONSEGNATO":
            complete += 1
        elif summary["status"] == "SOVRACONSEGNATO":
            over += 1
        residual += summary["residual_quantity"]
    ddt_count = db.scalar(select(func.count(DeliveryNote.id))) or 0
    return {"open_orders":open_orders,"partial_orders":partial,"complete_orders":complete,"over_orders":over,
            "residual_quantity":residual,"ddt_count":ddt_count}


@router.get("/analytics/period-comparison")
def period_comparison(date_from: date, date_to: date, db: Session = Depends(get_db)):
    if date_to < date_from: raise HTTPException(400, "Intervallo date non valido")
    days = (date_to - date_from).days + 1
    prev_to = date_from - timedelta(days=1); prev_from = prev_to - timedelta(days=days-1)
    current = _period_metrics(db, date_from, date_to); previous = _period_metrics(db, prev_from, prev_to)
    changes = {k:_pct_change(float(current[k]), float(previous[k])) for k in current}
    return {"current_period":{"from":date_from,"to":date_to}, "previous_period":{"from":prev_from,"to":prev_to}, "current":current, "previous":previous, "change_percent":changes}
