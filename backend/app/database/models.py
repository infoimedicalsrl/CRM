from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from decimal import Decimal
from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    vat_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    peppol_endpoint: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    orders: Mapped[list["Order"]] = relationship(back_populates="customer")


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_product_code: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("order_number", name="uq_order_number"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(String(128), index=True)
    order_date: Mapped[date] = mapped_column(Date, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    total_net: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    total_vat: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    total_gross: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    source_filename: Mapped[str] = mapped_column(String(512))
    source_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    customer: Mapped[Customer] = relationship(back_populates="orders")
    lines: Mapped[list["OrderLine"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderLine(Base):
    __tablename__ = "order_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    line_number: Mapped[str] = mapped_column(String(64))
    description_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 5))
    line_net: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    vat_category: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    line_vat: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    line_gross: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    # Nullable manual override for delivery tracking. When set, this value
    # is the authoritative delivered quantity for this order line; when null,
    # delivered quantity is calculated from linked DDTs.
    manual_delivered_quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4), nullable=True)
    order: Mapped[Order] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()


class ImportJob(Base):
    __tablename__ = "imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    file_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warnings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ProductCodeVariant(Base):
    __tablename__ = "product_code_variants"
    __table_args__ = (UniqueConstraint("product_id", "raw_code", name="uq_product_code_variant"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    raw_code: Mapped[str] = mapped_column(String(128))
    normalized_code: Mapped[str] = mapped_column(String(128), index=True)
    occurrences: Mapped[int] = mapped_column(default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    product: Mapped[Product] = relationship()


class DeliveryNote(Base):
    __tablename__ = "delivery_notes"
    __table_args__ = (UniqueConstraint("source_hash", name="uq_delivery_note_source_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ddt_number: Mapped[str] = mapped_column(String(128), index=True)
    ddt_date: Mapped[date] = mapped_column(Date, index=True)
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id"), nullable=True, index=True)
    source_filename: Mapped[str] = mapped_column(String(512))
    source_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="NON_COLLEGATO", index=True)
    order_reference: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    customer: Mapped[Optional[Customer]] = relationship()
    order: Mapped[Optional[Order]] = relationship()
    lines: Mapped[list["DeliveryNoteLine"]] = relationship(back_populates="ddt", cascade="all, delete-orphan")


class DeliveryNoteLine(Base):
    __tablename__ = "delivery_note_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    ddt_id: Mapped[int] = mapped_column(ForeignKey("delivery_notes.id"), index=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    order_line_id: Mapped[Optional[int]] = mapped_column(ForeignKey("order_lines.id"), nullable=True, index=True)
    supplier_product_code: Mapped[str] = mapped_column(String(128))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    unit_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    lot_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_gift: Mapped[bool] = mapped_column(default=False)
    is_unordered: Mapped[bool] = mapped_column(default=False)
    ddt: Mapped[DeliveryNote] = relationship(back_populates="lines")
    product: Mapped[Optional[Product]] = relationship()
    order_line: Mapped[Optional[OrderLine]] = relationship()


class BankMovement(Base):
    __tablename__ = "bank_movements"
    __table_args__ = (UniqueConstraint("import_key", name="uq_bank_movement_import_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    booking_date: Mapped[date] = mapped_column(Date, index=True)
    value_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    direction: Mapped[str] = mapped_column(String(16), index=True)
    description: Mapped[str] = mapped_column(Text)
    # Campi strutturati estratti dalla causale; restano separati dall'importo bancario.
    invoice_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    invoice_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cig_codes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    counterparty: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    counterparty_iban: Mapped[Optional[str]] = mapped_column(String(34), nullable=True, index=True)
    balance_after: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    source_filename: Mapped[str] = mapped_column(String(512))
    import_key: Mapped[str] = mapped_column(String(64), index=True)
    possible_duplicate: Mapped[bool] = mapped_column(default=False, index=True)
    duplicate_reviewed: Mapped[bool] = mapped_column(default=False)
    linked_order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id"), nullable=True)
    linked_sales_invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sales_invoices.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BankStatement(Base):
    __tablename__ = "bank_statements"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    opening_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    closing_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    calculated_closing_balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    reconciliation_difference: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    transaction_count: Mapped[int] = mapped_column(default=0)
    warnings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SalesInvoice(Base):
    __tablename__ = "sales_invoices"
    __table_args__ = (UniqueConstraint("source_hash", name="uq_sales_invoice_source_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(128), index=True)
    issue_date: Mapped[date] = mapped_column(Date, index=True)
    customer_name: Mapped[str] = mapped_column(String(255), index=True)
    customer_vat: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    customer_cf: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(32), default="DA_INCASSARE", index=True)
    source_filename: Mapped[str] = mapped_column(String(512))
    source_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_format: Mapped[str] = mapped_column(String(16))
    extraction_warnings: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PurchaseInvoice(Base):
    """Fattura ricevuta da un fornitore, separata dalle fatture emesse."""
    __tablename__ = "purchase_invoices"
    __table_args__ = (UniqueConstraint("source_hash", name="uq_purchase_invoice_source_hash"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_number: Mapped[str] = mapped_column(String(128), index=True)
    issue_date: Mapped[date] = mapped_column(Date, index=True)
    supplier_name: Mapped[str] = mapped_column(String(255), index=True)
    supplier_vat: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    supplier_cf: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    net_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    supplier_address: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    supplier_city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    supplier_province: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    supplier_postal_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    supplier_country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    source_filename: Mapped[str] = mapped_column(String(512))
    source_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_format: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CounterpartyRule(Base):
    __tablename__ = "bank_counterparty_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    normalized_counterparty: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_counterparty: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CustomerStatementImport(Base):
    __tablename__ = "customer_statement_imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    file_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    file_format: Mapped[str] = mapped_column(String(16))
    stored_path: Mapped[str] = mapped_column(String(1024))
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source_year: Mapped[int] = mapped_column(default=2026)
    rows_imported: Mapped[int] = mapped_column(default=0)
    rows_ignored_other_year: Mapped[int] = mapped_column(default=0)
    rows_unmatched: Mapped[int] = mapped_column(default=0)
    rows_matched: Mapped[int] = mapped_column(default=0)


class CustomerStatementRow(Base):
    __tablename__ = "customer_statement_rows"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_id: Mapped[int] = mapped_column(ForeignKey("customer_statement_imports.id", ondelete="CASCADE"), index=True)
    invoice_id: Mapped[Optional[int]] = mapped_column(ForeignKey("sales_invoices.id"), nullable=True, index=True)
    office_document_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    document_number: Mapped[str] = mapped_column(String(255), index=True)
    order_number: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    vat_withholdings: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    paid: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    balance: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    liquidated: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    row_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    match_status: Mapped[str] = mapped_column(String(32), default="NON_ABBINATA", index=True)
    match_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_data: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
