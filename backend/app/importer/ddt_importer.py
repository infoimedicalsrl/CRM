
from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from decimal import Decimal
from typing import Tuple, List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Customer, DeliveryNote, DeliveryNoteLine, Order, OrderLine, Product
from app.normalization import normalize_product_code, normalize_unit_code, normalize_customer_name, normalize_vat_number
from app.parser.ddt_parser import ParsedDDT, parse_ddt


class DuplicateDDTError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _find_customer(db: Session, parsed: ParsedDDT) -> Customer | None:
    if parsed.customer_vat:
        key = normalize_vat_number(parsed.customer_vat)
        if key:
            customer = next((candidate for candidate in db.scalars(select(Customer)).all() if normalize_vat_number(candidate.vat_number) == key), None)
            if customer:
                return customer
    if parsed.customer_name:
        return db.scalar(select(Customer).where(func.lower(Customer.name) == normalize_customer_name(parsed.customer_name).lower()))
    return None


def _normalize_order_reference(value: str | None) -> str:
    """Normalize order references for matching across supplier document formats.

    The same order may be printed by the Peppol XML as ``2026/9562V1`` and
    on the DDT as ``9562V1/26``.  We therefore remove spaces/separators and,
    when a four-digit year is present at either end, keep a canonical key
    containing the two-digit year plus the order body.
    """
    if not value:
        return ""
    return value.strip().upper().replace(" ", "")


def _parse_order_reference(value: str | None) -> tuple[str | None, str]:
    import re
    raw = _normalize_order_reference(value)
    if not raw:
        return None, ""
    match = re.fullmatch(r"(20\d{2})/(.+)", raw)
    if match:
        return match.group(1)[2:], match.group(2).replace("/", "").replace("-", "")
    match = re.fullmatch(r"(.+)/(\d{2})", raw)
    if match:
        return match.group(2), match.group(1).replace("/", "").replace("-", "")
    return None, raw.replace("/", "").replace("-", "")


def order_references_match(left: str | None, right: str | None) -> bool:
    left_year, left_body = _parse_order_reference(left)
    right_year, right_body = _parse_order_reference(right)
    if not left_body or not right_body or left_body != right_body:
        return False
    # If both references carry a year, it must be the same year. If only one
    # carries a year, the unqualified reference is still allowed to match it.
    return not left_year or not right_year or left_year == right_year


def _find_order(db: Session, parsed: ParsedDDT, customer: Customer | None) -> Order | None:
    if not parsed.order_reference:
        return None
    ref = parsed.order_reference.strip()
    # First try exact match, then tolerant format matching.
    order = db.scalar(select(Order).where(Order.order_number == ref))
    if order and (customer is None or order.customer_id == customer.id):
        return order
    for candidate in db.scalars(select(Order).order_by(Order.order_date.desc())).all():
        if (customer is None or candidate.customer_id == customer.id) and order_references_match(ref, candidate.order_number):
            return candidate
    return None


def _find_product(db: Session, code: str) -> Product | None:
    key = normalize_product_code(code)
    return db.scalar(select(Product).where(func.upper(func.replace(Product.supplier_product_code, " ", "")) == key))


def _link_lines(db: Session, ddt: DeliveryNote, order: Order | None) -> None:
    for line in ddt.lines:
        product = _find_product(db, line.supplier_product_code)
        line.product_id = product.id if product else None
        line.is_unordered = False
        line.order_line_id = None
        if not order:
            continue
        candidates = [
            ol for ol in db.scalars(select(OrderLine).where(OrderLine.order_id == order.id)).all()
            if product and ol.product_id == product.id
        ]
        if candidates:
            # Prefer the line with the largest remaining quantity.
            def remaining(ol: OrderLine) -> Decimal:
                delivered = sum(
                    (x.quantity for x in db.scalars(
                        select(DeliveryNoteLine).where(
                            DeliveryNoteLine.order_line_id == ol.id,
                            DeliveryNoteLine.is_gift.is_(False),
                            DeliveryNoteLine.ddt_id != ddt.id,
                        )
                    ).all()),
                    Decimal("0"),
                )
                return Decimal(ol.quantity) - delivered
            candidates.sort(key=remaining, reverse=True)
            line.order_line_id = candidates[0].id
        else:
            line.is_unordered = True


def refresh_ddt_status(db: Session, ddt: DeliveryNote) -> None:
    """Set DDT status from the actual line-to-order-line links.

    ``order_id`` alone is only the selected order container. A DDT is
    considered connected only when at least one non-gift line is really
    associated with an OrderLine.
    """
    lines = list(ddt.lines)
    real_lines = [x for x in lines if not x.is_gift]
    linked_count = sum(1 for x in real_lines if x.order_line_id is not None)
    if not ddt.order_id or not real_lines or linked_count == 0:
        ddt.status = "NON_COLLEGATO"
    elif linked_count < len(real_lines):
        ddt.status = "PARZIALMENTE_COLLEGATO"
    else:
        ddt.status = "COLLEGATO"


def refresh_order_delivery(db: Session, order_id: int) -> None:
    """Reconcile DDT lines against the current order lines.

    The supplier product code is the canonical matching key. We deliberately
    do not depend on ``product_id`` being already populated on the DDT line:
    a DDT can be imported before/without a perfectly matching catalog row.
    Matching is case-insensitive and ignores spaces, exactly like the rest of
    the application. Gift/unordered lines remain outside delivered totals.
    """
    order = db.get(Order, order_id)
    if not order:
        return

    ddt_lines = db.scalars(
        select(DeliveryNoteLine)
        .join(DeliveryNote, DeliveryNote.id == DeliveryNoteLine.ddt_id)
        .where(DeliveryNote.order_id == order_id)
    ).all()

    by_code: dict[str, list[OrderLine]] = {}
    for ol in order.lines:
        product = db.get(Product, ol.product_id) if ol.product_id else None
        if product:
            key = normalize_product_code(product.supplier_product_code)
        else:
            key = ""
        if key:
            by_code.setdefault(key, []).append(ol)

    # Refresh product references from the canonical DDT code and clear old
    # line links before reallocating all DDTs in chronological order.
    for line in ddt_lines:
        product = _find_product(db, line.supplier_product_code)
        line.product_id = product.id if product else None
        line.order_line_id = None
        line.is_unordered = False

    notes = db.scalars(
        select(DeliveryNote)
        .where(DeliveryNote.order_id == order_id)
        .order_by(DeliveryNote.ddt_date, DeliveryNote.id)
    ).all()

    for note in notes:
        for line in note.lines:
            if line.is_gift:
                line.order_line_id = None
                line.is_unordered = False
                continue

            code_key = normalize_product_code(line.supplier_product_code)
            candidates = by_code.get(code_key, [])
            if candidates:
                # Prefer the order line with the largest quantity still
                # available after previous DDT allocations.
                def remaining(ol: OrderLine) -> Decimal:
                    delivered = sum(
                        (x.quantity for x in db.scalars(
                            select(DeliveryNoteLine).where(
                                DeliveryNoteLine.order_line_id == ol.id,
                                DeliveryNoteLine.is_gift.is_(False),
                            )
                        ).all()),
                        Decimal("0"),
                    )
                    return Decimal(ol.quantity) - delivered

                candidates = sorted(candidates, key=remaining, reverse=True)
                positive = [x for x in candidates if remaining(x) > 0]
                target = positive[0] if positive else candidates[0]
                line.order_line_id = target.id
                line.is_unordered = False
            else:
                line.order_line_id = None
                line.is_unordered = True

        refresh_ddt_status(db, note)


def import_ddt(path: str | Path, db: Session) -> Tuple[DeliveryNote, List[str]]:
    path = Path(path)
    digest = sha256_file(path)
    parsed = parse_ddt(path)

    existing = db.scalar(select(DeliveryNote).where(DeliveryNote.source_hash == digest))
    if existing:
        # Re-uploading the exact same PDF is treated as an explicit reprocessing
        # request. This is important after improving the parser: an old DDT in
        # the database must not remain stuck with an incomplete/incorrect parse.
        old_order_id = existing.order_id
        customer = _find_customer(db, parsed)
        if customer:
            existing.customer_id = customer.id
        order = _find_order(db, parsed, customer)
        existing.order_id = order.id if order else None
        existing.ddt_number = parsed.ddt_number
        existing.ddt_date = parsed.ddt_date
        existing.order_reference = parsed.order_reference
        existing.source_filename = path.name

        old_lines = list(existing.lines)
        # Preserve an explicit Omaggio flag when the same product is reprocessed.
        gift_flags: dict[str, list[bool]] = {}
        for line in old_lines:
            gift_flags.setdefault(normalize_product_code(line.supplier_product_code), []).append(bool(line.is_gift))
        for line in old_lines:
            db.delete(line)
        db.flush()

        warnings: list[str] = ["DDT già presente: dati rielaborati dal PDF con il parser aggiornato."]
        missing_description = missing_lot = missing_expiry = 0
        for parsed_line in parsed.lines:
            if not parsed_line.description:
                missing_description += 1
            if not parsed_line.lot_number:
                missing_lot += 1
            if not parsed_line.expiry_date:
                missing_expiry += 1
            product = _find_product(db, parsed_line.supplier_product_code)
            key = normalize_product_code(parsed_line.supplier_product_code)
            flags = gift_flags.get(key, [])
            is_gift = flags.pop(0) if flags else False
            db.add(DeliveryNoteLine(
                ddt_id=existing.id,
                product_id=product.id if product else None,
                supplier_product_code=parsed_line.supplier_product_code,
                description=parsed_line.description,
                quantity=parsed_line.quantity,
                unit_code=normalize_unit_code(parsed_line.unit_code),
                lot_number=parsed_line.lot_number,
                expiry_date=parsed_line.expiry_date,
                is_gift=is_gift,
            ))
            if not product:
                warnings.append(f"Prodotto non presente in anagrafica: {parsed_line.supplier_product_code}")
        if missing_description:
            warnings.append(f"Descrizione non estratta per {missing_description} righe")
        if missing_lot:
            warnings.append(f"Lotto non presente/estratto per {missing_lot} righe")
        if missing_expiry:
            warnings.append(f"Scadenza non presente/estratta per {missing_expiry} righe")
        db.flush()
        if old_order_id:
            refresh_order_delivery(db, old_order_id)
        if order and order.id != old_order_id:
            refresh_order_delivery(db, order.id)
        else:
            refresh_ddt_status(db, existing)
        refresh_ddt_status(db, existing)
        if existing.status == "NON_COLLEGATO":
            existing.order_id = None
        db.commit()
        db.refresh(existing)
        return existing, warnings

    customer = _find_customer(db, parsed)
    if customer is None and parsed.customer_vat:
        customer = Customer(name=normalize_customer_name(parsed.customer_name), vat_number=parsed.customer_vat)
        db.add(customer)
        db.flush()
    elif customer is None and parsed.customer_name:
        # DDTs without a VAT number are still retained; the customer may be matched later.
        customer = Customer(name=normalize_customer_name(parsed.customer_name), vat_number=f"DDT-{digest[:20]}")
        db.add(customer)
        db.flush()
    order = _find_order(db, parsed, customer)

    ddt = DeliveryNote(
        ddt_number=parsed.ddt_number,
        ddt_date=parsed.ddt_date,
        customer_id=customer.id if customer else None,
        order_id=order.id if order else None,
        source_filename=path.name,
        source_hash=digest,
        order_reference=parsed.order_reference,
    )
    db.add(ddt)
    db.flush()
    warnings: list[str] = []
    missing_description = 0
    missing_lot = 0
    missing_expiry = 0
    for parsed_line in parsed.lines:
        if not parsed_line.description:
            missing_description += 1
        if not parsed_line.lot_number:
            missing_lot += 1
        if not parsed_line.expiry_date:
            missing_expiry += 1
        product = _find_product(db, parsed_line.supplier_product_code)
        line = DeliveryNoteLine(
            ddt_id=ddt.id,
            product_id=product.id if product else None,
            supplier_product_code=parsed_line.supplier_product_code,
            description=parsed_line.description,
            quantity=parsed_line.quantity,
            unit_code=normalize_unit_code(parsed_line.unit_code),
            lot_number=parsed_line.lot_number,
            expiry_date=parsed_line.expiry_date,
        )
        db.add(line)
        if not product:
            warnings.append(f"Prodotto non presente in anagrafica: {parsed_line.supplier_product_code}")
    db.flush()
    if missing_description:
        warnings.append(f"Descrizione non estratta per {missing_description} righe")
    if missing_lot:
        warnings.append(f"Lotto non presente/estratto per {missing_lot} righe")
    if missing_expiry:
        warnings.append(f"Scadenza non presente/estratta per {missing_expiry} righe")
    if order:
        refresh_order_delivery(db, order.id)
        refresh_ddt_status(db, ddt)
        if ddt.status == "NON_COLLEGATO":
            ddt.order_id = None
    else:
        refresh_ddt_status(db, ddt)
    db.commit()
    db.refresh(ddt)
    return ddt, warnings


def relink_ddt(db: Session, ddt: DeliveryNote, order: Order | None) -> None:
    """Link a DDT to an order and immediately reconcile its individual lines.

    Merely selecting an order is not enough to mark a DDT as connected: each
    non-gift DDT line must be matched to an actual order line.
    """
    old_order_id = ddt.order_id
    ddt.order_id = order.id if order else None
    if order and not ddt.customer_id:
        ddt.customer_id = order.customer_id

    if order:
        # Reconcile every DDT belonging to the target order. This allocates
        # lines by normalized supplier product code and refreshes the DDT
        # status from the real line links.
        refresh_order_delivery(db, order.id)
        db.flush()
        refresh_ddt_status(db, ddt)
        # If not even one real DDT line matches an order line, do not persist
        # a fake order association: the DDT remains genuinely unlinked.
        if ddt.status == "NON_COLLEGATO":
            ddt.order_id = None
    else:
        for line in ddt.lines:
            line.order_line_id = None
            line.is_unordered = False
        refresh_ddt_status(db, ddt)

    if old_order_id and old_order_id != ddt.order_id:
        refresh_order_delivery(db, old_order_id)
    db.flush()
    refresh_ddt_status(db, ddt)
    db.commit()


def link_pending_ddts_for_order(db: Session, order: Order) -> int:
    """Link previously imported DDTs that referenced this order before it existed."""
    candidates = db.scalars(
        select(DeliveryNote).where(
            DeliveryNote.order_id.is_(None),
            DeliveryNote.order_reference.is_not(None),
        )
    ).all()
    order_customer = db.get(Customer, order.customer_id)
    order_customer_name = normalize_customer_name(order_customer.name) if order_customer else ""
    order_customer_vat = (order_customer.vat_number or "").strip().upper() if order_customer else ""
    linked = 0
    for ddt in candidates:
        same_customer = ddt.customer_id == order.customer_id
        if not same_customer and ddt.customer_id and order_customer:
            ddt_customer = db.get(Customer, ddt.customer_id)
            if ddt_customer:
                same_customer = (
                    normalize_customer_name(ddt_customer.name).casefold() == order_customer_name.casefold()
                    or (ddt_customer.vat_number or "").strip().upper() == order_customer_vat
                )
        if same_customer and order_references_match(ddt.order_reference, order.order_number):
            ddt.order_id = order.id
            refresh_order_delivery(db, order.id)
            refresh_ddt_status(db, ddt)
            if ddt.status != "NON_COLLEGATO":
                linked += 1
            else:
                ddt.order_id = None
    if linked:
        db.commit()
    return linked
