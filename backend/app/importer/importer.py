from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
from typing import List, Tuple, Union
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Customer, ImportJob, Order, OrderLine, Product, ProductCodeVariant
from app.parser.peppol_parser import parse_peppol_order
from app.parser.validator import validate_order
from app.normalization import normalize_product_code, normalize_unit_code, normalize_customer_name, normalize_vat_number
from app.importer.ddt_importer import link_pending_ddts_for_order


class DuplicateOrderError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()




def _record_product_variant(db: Session, product: Product, raw_code: str) -> None:
    raw = raw_code.strip()
    key = normalize_product_code(raw)
    variant = db.scalar(
        select(ProductCodeVariant).where(
            ProductCodeVariant.product_id == product.id,
            ProductCodeVariant.raw_code == raw,
        )
    )
    if variant is None:
        db.add(ProductCodeVariant(
            product_id=product.id, raw_code=raw, normalized_code=key, occurrences=1,
            first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
        ))
    else:
        variant.occurrences += 1
        variant.last_seen_at = datetime.utcnow()


def import_xml(path: Union[str, Path], db: Session) -> Tuple[Order, List[str]]:
    path = Path(path)
    digest = sha256_file(path)
    job = ImportJob(filename=path.name, file_hash=digest, status="PROCESSING")
    db.add(job)
    db.flush()

    try:
        if db.scalar(select(Order).where(Order.source_hash == digest)):
            raise DuplicateOrderError("File già importato (SHA-256 già presente)")

        parsed = parse_peppol_order(path)
        if db.scalar(select(Order).where(Order.order_number == parsed.order_number)):
            raise DuplicateOrderError(f"Ordine {parsed.order_number} già presente")

        warnings = validate_order(parsed)

        parsed_vat_key = normalize_vat_number(parsed.customer.vat_number)
        customer = None
        if parsed_vat_key:
            customer = next((candidate for candidate in db.scalars(select(Customer)).all() if normalize_vat_number(candidate.vat_number) == parsed_vat_key), None)
        if customer is None:
            customer = Customer(
                name=normalize_customer_name(parsed.customer.name),
                vat_number=parsed.customer.vat_number.strip().upper(),
                peppol_endpoint=parsed.customer.peppol_endpoint,
            )
            db.add(customer)
            db.flush()
        else:
            # Customer name is user-editable in the local app. Preserve the stored name
            # on subsequent imports so a manual correction is not overwritten by XML.
            customer.peppol_endpoint = parsed.customer.peppol_endpoint

        order = Order(
            order_number=parsed.order_number,
            order_date=parsed.order_date,
            customer_id=customer.id,
            currency=parsed.currency,
            total_net=parsed.total_net,
            total_vat=parsed.total_vat,
            total_gross=parsed.total_gross,
            source_filename=path.name,
            source_hash=digest,
        )
        db.add(order)
        db.flush()

        for line in parsed.lines:
            normalized_code = normalize_product_code(line.supplier_product_code)
            product = db.scalar(
                select(Product).where(
                    func.upper(func.replace(Product.supplier_product_code, " ", "")) == normalized_code
                )
            )
            if product is None:
                product = Product(
                    supplier_product_code=line.supplier_product_code,
                    description=line.description,
                )
                db.add(product)
                db.flush()
            else:
                # Product identity is ONLY supplier_product_code; description is latest known label.
                product.description = line.description

            _record_product_variant(db, product, line.supplier_product_code)

            db.add(
                OrderLine(
                    order_id=order.id,
                    product_id=product.id,
                    line_number=line.line_number,
                    description_snapshot=line.description,
                    quantity=line.quantity,
                    unit_code=normalize_unit_code(line.unit_code),
                    unit_price=line.unit_price,
                    line_net=line.line_net,
                    vat_category=line.vat_category,
                    vat_rate=line.vat_rate,
                    line_vat=line.line_vat,
                    line_gross=line.line_gross,
                )
            )

        job.status = "SUCCESS"
        job.warnings = "\n".join(warnings) if warnings else None
        job.completed_at = datetime.utcnow()
        db.commit()
        db.refresh(order)
        link_pending_ddts_for_order(db, order)
        db.refresh(order)
        return order, warnings
    except Exception as exc:
        db.rollback()
        # Persist failed import in a clean transaction.
        failed_job = ImportJob(
            filename=path.name,
            file_hash=digest,
            status="ERROR",
            error_message=str(exc),
            completed_at=datetime.utcnow(),
        )
        db.add(failed_job)
        db.commit()
        raise
