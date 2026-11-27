-- Peppol Sales Analytics - schema iniziale PostgreSQL (Supabase).
-- Generato dai modelli SQLAlchemy; SOLO struttura, nessun dato.
-- Eseguire per primo nel SQL Editor di un progetto Supabase nuovo/vuoto.

CREATE TABLE customers (
	id SERIAL NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	vat_number VARCHAR(64) NOT NULL, 
	peppol_endpoint VARCHAR(128), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_customers_vat_number ON customers (vat_number);

CREATE TABLE products (
	id SERIAL NOT NULL, 
	supplier_product_code VARCHAR(128) NOT NULL, 
	description TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_products_supplier_product_code ON products (supplier_product_code);

CREATE TABLE imports (
	id SERIAL NOT NULL, 
	filename VARCHAR(512) NOT NULL, 
	file_hash VARCHAR(64), 
	status VARCHAR(32) NOT NULL, 
	error_message TEXT, 
	warnings TEXT, 
	started_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	completed_at TIMESTAMP WITHOUT TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_imports_status ON imports (status);

CREATE INDEX ix_imports_file_hash ON imports (file_hash);

CREATE TABLE bank_statements (
	id SERIAL NOT NULL, 
	filename VARCHAR(512) NOT NULL, 
	imported_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	opening_balance NUMERIC(18, 2), 
	closing_balance NUMERIC(18, 2), 
	calculated_closing_balance NUMERIC(18, 2), 
	reconciliation_difference NUMERIC(18, 2), 
	transaction_count INTEGER NOT NULL, 
	warnings TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE sales_invoices (
	id SERIAL NOT NULL, 
	invoice_number VARCHAR(128) NOT NULL, 
	issue_date DATE NOT NULL, 
	customer_name VARCHAR(255) NOT NULL, 
	customer_vat VARCHAR(64), 
	customer_cf VARCHAR(64), 
	currency VARCHAR(8) NOT NULL, 
	net_amount NUMERIC(18, 2) NOT NULL, 
	vat_amount NUMERIC(18, 2) NOT NULL, 
	gross_amount NUMERIC(18, 2) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	source_filename VARCHAR(512) NOT NULL, 
	source_hash VARCHAR(64) NOT NULL, 
	source_format VARCHAR(16) NOT NULL, 
	extraction_warnings TEXT, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_sales_invoice_source_hash UNIQUE (source_hash)
);

CREATE INDEX ix_sales_invoices_issue_date ON sales_invoices (issue_date);

CREATE INDEX ix_sales_invoices_customer_vat ON sales_invoices (customer_vat);

CREATE UNIQUE INDEX ix_sales_invoices_source_hash ON sales_invoices (source_hash);

CREATE INDEX ix_sales_invoices_customer_name ON sales_invoices (customer_name);

CREATE INDEX ix_sales_invoices_invoice_number ON sales_invoices (invoice_number);

CREATE INDEX ix_sales_invoices_status ON sales_invoices (status);

CREATE TABLE purchase_invoices (
	id SERIAL NOT NULL, 
	invoice_number VARCHAR(128) NOT NULL, 
	issue_date DATE NOT NULL, 
	supplier_name VARCHAR(255) NOT NULL, 
	supplier_vat VARCHAR(64), 
	supplier_cf VARCHAR(64), 
	currency VARCHAR(8) NOT NULL, 
	net_amount NUMERIC(18, 2) NOT NULL, 
	vat_amount NUMERIC(18, 2) NOT NULL, 
	gross_amount NUMERIC(18, 2) NOT NULL, 
	due_date DATE, 
	supplier_address VARCHAR(255), 
	supplier_city VARCHAR(128), 
	supplier_province VARCHAR(32), 
	supplier_postal_code VARCHAR(16), 
	supplier_country VARCHAR(64), 
	description TEXT, 
	original_currency VARCHAR(8), 
	source_filename VARCHAR(512) NOT NULL, 
	source_hash VARCHAR(64) NOT NULL, 
	source_format VARCHAR(16) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_purchase_invoice_source_hash UNIQUE (source_hash)
);

CREATE INDEX ix_purchase_invoices_invoice_number ON purchase_invoices (invoice_number);

CREATE INDEX ix_purchase_invoices_supplier_cf ON purchase_invoices (supplier_cf);

CREATE INDEX ix_purchase_invoices_issue_date ON purchase_invoices (issue_date);

CREATE UNIQUE INDEX ix_purchase_invoices_source_hash ON purchase_invoices (source_hash);

CREATE INDEX ix_purchase_invoices_supplier_vat ON purchase_invoices (supplier_vat);

CREATE INDEX ix_purchase_invoices_due_date ON purchase_invoices (due_date);

CREATE INDEX ix_purchase_invoices_supplier_name ON purchase_invoices (supplier_name);

CREATE TABLE bank_counterparty_rules (
	id SERIAL NOT NULL, 
	normalized_counterparty VARCHAR(255) NOT NULL, 
	display_counterparty VARCHAR(255) NOT NULL, 
	category VARCHAR(100) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_bank_counterparty_rules_normalized_counterparty ON bank_counterparty_rules (normalized_counterparty);

CREATE TABLE customer_statement_imports (
	id SERIAL NOT NULL, 
	filename VARCHAR(512) NOT NULL, 
	file_hash VARCHAR(64) NOT NULL, 
	file_format VARCHAR(16) NOT NULL, 
	stored_path VARCHAR(1024) NOT NULL, 
	imported_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	source_year INTEGER NOT NULL, 
	rows_imported INTEGER NOT NULL, 
	rows_ignored_other_year INTEGER NOT NULL, 
	rows_unmatched INTEGER NOT NULL, 
	rows_matched INTEGER NOT NULL, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_customer_statement_imports_file_hash ON customer_statement_imports (file_hash);

CREATE TABLE orders (
	id SERIAL NOT NULL, 
	order_number VARCHAR(128) NOT NULL, 
	order_date DATE NOT NULL, 
	customer_id INTEGER NOT NULL, 
	currency VARCHAR(8) NOT NULL, 
	total_net NUMERIC(18, 2) NOT NULL, 
	total_vat NUMERIC(18, 2) NOT NULL, 
	total_gross NUMERIC(18, 2) NOT NULL, 
	source_filename VARCHAR(512) NOT NULL, 
	source_hash VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_order_number UNIQUE (order_number), 
	FOREIGN KEY(customer_id) REFERENCES customers (id)
);

CREATE INDEX ix_orders_order_date ON orders (order_date);

CREATE INDEX ix_orders_order_number ON orders (order_number);

CREATE INDEX ix_orders_customer_id ON orders (customer_id);

CREATE UNIQUE INDEX ix_orders_source_hash ON orders (source_hash);

CREATE TABLE product_code_variants (
	id SERIAL NOT NULL, 
	product_id INTEGER NOT NULL, 
	raw_code VARCHAR(128) NOT NULL, 
	normalized_code VARCHAR(128) NOT NULL, 
	occurrences INTEGER NOT NULL, 
	first_seen_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	last_seen_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_product_code_variant UNIQUE (product_id, raw_code), 
	FOREIGN KEY(product_id) REFERENCES products (id)
);

CREATE INDEX ix_product_code_variants_product_id ON product_code_variants (product_id);

CREATE INDEX ix_product_code_variants_normalized_code ON product_code_variants (normalized_code);

CREATE TABLE customer_statement_rows (
	id SERIAL NOT NULL, 
	import_id INTEGER NOT NULL, 
	invoice_id INTEGER, 
	office_document_type VARCHAR(255), 
	document_number VARCHAR(255) NOT NULL, 
	order_number VARCHAR(255), 
	amount NUMERIC(18, 2), 
	vat_withholdings NUMERIC(18, 2), 
	paid NUMERIC(18, 2), 
	balance NUMERIC(18, 2), 
	liquidated VARCHAR(255), 
	row_date DATE, 
	status VARCHAR(255), 
	match_status VARCHAR(32) NOT NULL, 
	match_note TEXT, 
	raw_data TEXT NOT NULL, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(import_id) REFERENCES customer_statement_imports (id) ON DELETE CASCADE, 
	FOREIGN KEY(invoice_id) REFERENCES sales_invoices (id)
);

CREATE INDEX ix_customer_statement_rows_match_status ON customer_statement_rows (match_status);

CREATE INDEX ix_customer_statement_rows_import_id ON customer_statement_rows (import_id);

CREATE INDEX ix_customer_statement_rows_invoice_id ON customer_statement_rows (invoice_id);

CREATE INDEX ix_customer_statement_rows_row_date ON customer_statement_rows (row_date);

CREATE INDEX ix_customer_statement_rows_document_number ON customer_statement_rows (document_number);

CREATE TABLE order_lines (
	id SERIAL NOT NULL, 
	order_id INTEGER NOT NULL, 
	product_id INTEGER NOT NULL, 
	line_number VARCHAR(64) NOT NULL, 
	description_snapshot TEXT, 
	quantity NUMERIC(18, 4) NOT NULL, 
	unit_code VARCHAR(16), 
	unit_price NUMERIC(18, 5) NOT NULL, 
	line_net NUMERIC(18, 2) NOT NULL, 
	vat_category VARCHAR(16), 
	vat_rate NUMERIC(8, 4) NOT NULL, 
	line_vat NUMERIC(18, 2) NOT NULL, 
	line_gross NUMERIC(18, 2) NOT NULL, 
	manual_delivered_quantity NUMERIC(18, 4), 
	PRIMARY KEY (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id), 
	FOREIGN KEY(product_id) REFERENCES products (id)
);

CREATE INDEX ix_order_lines_order_id ON order_lines (order_id);

CREATE INDEX ix_order_lines_product_id ON order_lines (product_id);

CREATE TABLE delivery_notes (
	id SERIAL NOT NULL, 
	ddt_number VARCHAR(128) NOT NULL, 
	ddt_date DATE NOT NULL, 
	customer_id INTEGER, 
	order_id INTEGER, 
	source_filename VARCHAR(512) NOT NULL, 
	source_hash VARCHAR(64) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	order_reference VARCHAR(128), 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_delivery_note_source_hash UNIQUE (source_hash), 
	FOREIGN KEY(customer_id) REFERENCES customers (id), 
	FOREIGN KEY(order_id) REFERENCES orders (id)
);

CREATE INDEX ix_delivery_notes_status ON delivery_notes (status);

CREATE INDEX ix_delivery_notes_order_id ON delivery_notes (order_id);

CREATE INDEX ix_delivery_notes_ddt_date ON delivery_notes (ddt_date);

CREATE UNIQUE INDEX ix_delivery_notes_source_hash ON delivery_notes (source_hash);

CREATE INDEX ix_delivery_notes_order_reference ON delivery_notes (order_reference);

CREATE INDEX ix_delivery_notes_customer_id ON delivery_notes (customer_id);

CREATE INDEX ix_delivery_notes_ddt_number ON delivery_notes (ddt_number);

CREATE TABLE bank_movements (
	id SERIAL NOT NULL, 
	booking_date DATE NOT NULL, 
	value_date DATE, 
	amount NUMERIC(18, 2) NOT NULL, 
	direction VARCHAR(16) NOT NULL, 
	description TEXT NOT NULL, 
	invoice_amount NUMERIC(18, 2), 
	invoice_details TEXT, 
	cig_codes TEXT, 
	counterparty VARCHAR(255), 
	counterparty_iban VARCHAR(34), 
	balance_after NUMERIC(18, 2), 
	category VARCHAR(100), 
	source_filename VARCHAR(512) NOT NULL, 
	import_key VARCHAR(64) NOT NULL, 
	possible_duplicate BOOLEAN NOT NULL, 
	duplicate_reviewed BOOLEAN NOT NULL, 
	linked_order_id INTEGER, 
	linked_sales_invoice_id INTEGER, 
	created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_bank_movement_import_key UNIQUE (import_key), 
	FOREIGN KEY(linked_order_id) REFERENCES orders (id), 
	FOREIGN KEY(linked_sales_invoice_id) REFERENCES sales_invoices (id)
);

CREATE INDEX ix_bank_movements_category ON bank_movements (category);

CREATE INDEX ix_bank_movements_direction ON bank_movements (direction);

CREATE INDEX ix_bank_movements_value_date ON bank_movements (value_date);

CREATE INDEX ix_bank_movements_booking_date ON bank_movements (booking_date);

CREATE INDEX ix_bank_movements_possible_duplicate ON bank_movements (possible_duplicate);

CREATE INDEX ix_bank_movements_linked_sales_invoice_id ON bank_movements (linked_sales_invoice_id);

CREATE INDEX ix_bank_movements_counterparty_iban ON bank_movements (counterparty_iban);

CREATE INDEX ix_bank_movements_import_key ON bank_movements (import_key);

CREATE INDEX ix_bank_movements_counterparty ON bank_movements (counterparty);

CREATE TABLE delivery_note_lines (
	id SERIAL NOT NULL, 
	ddt_id INTEGER NOT NULL, 
	product_id INTEGER, 
	order_line_id INTEGER, 
	supplier_product_code VARCHAR(128) NOT NULL, 
	description TEXT, 
	quantity NUMERIC(18, 4) NOT NULL, 
	unit_code VARCHAR(16), 
	lot_number VARCHAR(128), 
	expiry_date DATE, 
	is_gift BOOLEAN NOT NULL, 
	is_unordered BOOLEAN NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(ddt_id) REFERENCES delivery_notes (id), 
	FOREIGN KEY(product_id) REFERENCES products (id), 
	FOREIGN KEY(order_line_id) REFERENCES order_lines (id)
);

CREATE INDEX ix_delivery_note_lines_order_line_id ON delivery_note_lines (order_line_id);

CREATE INDEX ix_delivery_note_lines_product_id ON delivery_note_lines (product_id);

CREATE INDEX ix_delivery_note_lines_ddt_id ON delivery_note_lines (ddt_id);
