from sqlalchemy import create_engine, func, inspect, literal_column, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool
from app.config import DATABASE_URL, IS_REMOTE_DATABASE
from app.normalization import normalize_product_code, normalize_customer_name

if IS_REMOTE_DATABASE:
    # Serverless + pooler Supabase (Supavisor): niente pool lato app e niente prepared
    # statements, incompatibili con la modalità "transaction" del pooler.
    _engine_options = {"poolclass": NullPool, "connect_args": {"prepare_threshold": None, "connect_timeout": 10}}
else:
    _engine_options = {"pool_pre_ping": True, "connect_args": {"check_same_thread": False}}
engine = create_engine(DATABASE_URL, **_engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def month_expr(column):
    """Raggruppamento per mese ('AAAA-MM') valido sia su PostgreSQL sia su SQLite."""
    if engine.dialect.name == "postgresql":
        # Formato inline (non come parametro): SELECT e GROUP BY devono avere la stessa espressione.
        return func.to_char(column, literal_column("'YYYY-MM'"))
    return func.strftime("%Y-%m", column)


def reconcile_product_codes() -> None:
    """Merge legacy products that differ only by spaces/case and seed variant history."""
    from datetime import datetime
    from sqlalchemy import select
    from .models import OrderLine, Product, ProductCodeVariant

    session = SessionLocal()
    try:
        canonical_by_key = {}
        for product in session.scalars(select(Product).order_by(Product.id)).all():
            key = normalize_product_code(product.supplier_product_code)
            canonical = canonical_by_key.get(key)
            if canonical is None:
                canonical_by_key[key] = product
                canonical = product
            elif canonical.id != product.id:
                for line in session.scalars(select(OrderLine).where(OrderLine.product_id == product.id)).all():
                    line.product_id = canonical.id
                if not canonical.description and product.description:
                    canonical.description = product.description
                session.delete(product)

            raw = product.supplier_product_code.strip()
            variant = session.scalar(
                select(ProductCodeVariant).where(
                    ProductCodeVariant.product_id == canonical.id,
                    ProductCodeVariant.raw_code == raw,
                )
            )
            if variant is None:
                session.add(ProductCodeVariant(
                    product_id=canonical.id, raw_code=raw, normalized_code=key, occurrences=1,
                    first_seen_at=datetime.utcnow(), last_seen_at=datetime.utcnow(),
                ))
        session.commit()
    finally:
        session.close()



def reconcile_customer_names() -> None:
    """Clean legacy customer names such as ``924 - Azienda ...`` once at startup."""
    from sqlalchemy import select
    from .models import Customer

    session = SessionLocal()
    try:
        changed = False
        for customer in session.scalars(select(Customer)).all():
            normalized = normalize_customer_name(customer.name)
            if normalized and normalized != customer.name:
                customer.name = normalized
                changed = True
        if changed:
            session.commit()
    finally:
        session.close()


def reconcile_delivery_links() -> None:
    """Repair legacy DDT/order links after delivery-linking logic changes."""
    from sqlalchemy import select
    from .models import DeliveryNote, Order
    from app.importer.ddt_importer import refresh_ddt_status, refresh_order_delivery

    session = SessionLocal()
    try:
        order_ids = set(session.scalars(select(DeliveryNote.order_id).where(DeliveryNote.order_id.is_not(None))).all())
        changed = False
        for order_id in order_ids:
            refresh_order_delivery(session, int(order_id))
        for ddt in session.scalars(select(DeliveryNote).where(DeliveryNote.order_id.is_not(None))).all():
            refresh_ddt_status(session, ddt)
            if ddt.status == "NON_COLLEGATO":
                ddt.order_id = None
                changed = True
        if order_ids or changed:
            session.commit()
    finally:
        session.close()

def init_db() -> None:
    """Create the application schema and apply additive legacy migrations.

    The same ORM schema works with local SQLite and remote PostgreSQL. The
    additive migrations are kept for existing SQLite installations; a fresh
    PostgreSQL database is created empty from the current SQLAlchemy models.
    """
    from . import models  # noqa: F401
    if IS_REMOTE_DATABASE:
        # Su Supabase lo schema si crea una sola volta con supabase/migrations/*.sql.
        # Nessuna DDL né riparazione dati a ogni avvio della funzione serverless.
        return
    Base.metadata.create_all(bind=engine)

    # Keep old local SQLite databases compatible with the current model.
    additions = {
        "order_lines": {
            "manual_delivered_quantity": "NUMERIC(18, 4)",
        },
        "sales_invoices": {
            "customer_cf": "VARCHAR(64)",
        },
        "purchase_invoices": {
            "supplier_cf": "VARCHAR(64)",
            "due_date": "DATE",
            "supplier_address": "VARCHAR(255)",
            "supplier_city": "VARCHAR(128)",
            "supplier_province": "VARCHAR(32)",
            "supplier_postal_code": "VARCHAR(16)",
            "supplier_country": "VARCHAR(64)",
            "description": "TEXT",
            "original_currency": "VARCHAR(8)",
        },
        "bank_movements": {
            "invoice_amount": "NUMERIC(18, 2)",
            "invoice_details": "TEXT",
            "cig_codes": "TEXT",
            "linked_sales_invoice_id": "INTEGER",
        },
    }
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        for table, columns_to_add in additions.items():
            if table not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspect(connection).get_columns(table)}
            for column, sql_type in columns_to_add.items():
                if column not in existing_columns:
                    connection.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'))
        if "bank_movements" in existing_tables:
            connection.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_bank_movements_linked_sales_invoice_id "
                "ON bank_movements (linked_sales_invoice_id)"
            ))
        if "order_lines" in existing_tables:
            connection.execute(text(
                "UPDATE order_lines SET unit_code = 'PZ' "
                "WHERE UPPER(TRIM(unit_code)) IN ('C62', 'PZ')"
            ))

    reconcile_product_codes()
    reconcile_customer_names()
    reconcile_delivery_links()
