-- 002 - Sicurezza: nessun accesso diretto ai dati dal browser.
-- Il frontend NON legge mai le tabelle: passa dalle API Vercel, che si collegano
-- con il ruolo "postgres" (bypassa RLS). Abilitando RLS senza policy e revocando i
-- privilegi, la chiave "anon"/"publishable" non puo' leggere ne' scrivere nulla.

alter table public.customers enable row level security;
alter table public.products enable row level security;
alter table public.imports enable row level security;
alter table public.bank_statements enable row level security;
alter table public.sales_invoices enable row level security;
alter table public.purchase_invoices enable row level security;
alter table public.bank_counterparty_rules enable row level security;
alter table public.customer_statement_imports enable row level security;
alter table public.orders enable row level security;
alter table public.product_code_variants enable row level security;
alter table public.customer_statement_rows enable row level security;
alter table public.order_lines enable row level security;
alter table public.delivery_notes enable row level security;
alter table public.bank_movements enable row level security;
alter table public.delivery_note_lines enable row level security;

revoke all on all tables    in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;
revoke all on all functions in schema public from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on tables    from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on sequences from anon, authenticated;
alter default privileges for role postgres in schema public revoke all on functions from anon, authenticated;
