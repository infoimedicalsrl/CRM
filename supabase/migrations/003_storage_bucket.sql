-- 003 - Bucket PRIVATO per i documenti originali (XML, PDF, CSV, Excel).
-- Nessuna policy su storage.objects: solo il backend, con la service-role key, puo' leggere/scrivere.
insert into storage.buckets (id, name, public, file_size_limit)
values ('documents', 'documents', false, 20971520)
on conflict (id) do update set public = false, file_size_limit = 20971520;
