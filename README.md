# Peppol Sales Analytics — versione cloud (Vercel + Supabase)

Web app con **login obbligatorio**. Dati su **Supabase PostgreSQL**, documenti originali (XML, PDF, CSV, Excel)
su **Supabase Storage** (bucket privato). Frontend React statico e backend FastAPI come funzione serverless, nello stesso progetto Vercel.

```
frontend/    React + Vite (login Supabase, nessun dato senza sessione)
backend/     FastAPI (app/, tests/)         -> esposto da api/index.py come Vercel Function
api/         entrypoint Vercel
supabase/    migrazioni SQL: schema, RLS, bucket
scripts/     migrazione dati dal vecchio SQLite
docs/        storico delle versioni locali
```

## Deploy passo-passo

### 1. Supabase
1. Crea un progetto su supabase.com.
2. **SQL Editor** → esegui in ordine `supabase/migrations/001_initial_schema.sql`, `002_security_rls.sql`, `003_storage_bucket.sql`.
3. **Authentication → Sign In / Providers**: lascia attivo *Email*, **disattiva "Allow new users to sign up"**.
4. **Authentication → Users → Add user**: crea il tuo utente (email + password, "Auto confirm").
5. **Project Settings → API**: copia `Project URL`, la chiave `anon`/publishable e la chiave `service_role`/secret.
6. **Connect → Transaction pooler** (porta 6543): copia la connection string e sostituisci la password del database.

### 2. GitHub
Crea un repository (**privato**) e carica questa cartella. `.gitignore` esclude segreti, dati e documenti.

### 3. Vercel
1. *Add New → Project* → importa il repository (nessun framework preset: `vercel.json` configura tutto).
2. **Environment Variables** (Production, e Preview se serve):

| Nome | Valore |
|---|---|
| `DATABASE_URL` | stringa del Transaction pooler |
| `SUPABASE_URL` | Project URL |
| `SUPABASE_ANON_KEY` | chiave anon/publishable |
| `SUPABASE_SERVICE_ROLE_KEY` | chiave service_role/secret (**segreta**) |
| `PEPPOL_ALLOWED_EMAILS` | la tua email (più email separate da virgola) |
| `VITE_SUPABASE_URL` | Project URL |
| `VITE_SUPABASE_ANON_KEY` | chiave anon/publishable |

3. Deploy. Apri l'URL, accedi con l'utente creato.

### 4. (Facoltativo) Importare i dati del vecchio database locale
```bash
pip install -r requirements.txt
cp .env.example .env     # compila i valori sopra
python scripts/migrate_sqlite_to_supabase.py --sqlite /percorso/peppol.sqlite \
    --documents-dir /percorso/ordini --documents-dir /percorso/ddt
```

## Sicurezza
- **Login obbligatorio**: ogni rotta `/api/*` (tranne `/api/health`, che non espone dati) verifica il token Supabase. Con `PEPPOL_ALLOWED_EMAILS` entrano solo le email indicate.
- **Tabelle non leggibili dal browser**: RLS attiva su tutte le tabelle e privilegi revocati a `anon`/`authenticated`. Il browser usa solo la chiave pubblica; i dati passano solo dalle API.
- **Bucket privato**: i documenti si leggono solo tramite il backend (service-role key, mai nel frontend).
- `PEPPOL_AUTH_DISABLED` (solo sviluppo locale) viene **ignorato su Vercel**; l'avvio fallisce se mancano `DATABASE_URL` o le chiavi Supabase.
- Documentazione API (`/docs`) disattivata in produzione; header di sicurezza e CSP configurati in `vercel.json` e nel backend.
- **Non committare mai** `.env`, la `service_role` key o la password del database. Se sono già state condivise, rigenerale da Supabase.

## Sviluppo locale
```bash
pip install -r backend/requirements-dev.txt
cp .env.example .env                       # oppure lascia vuoto DATABASE_URL: usa SQLite in .local/
cd backend && PEPPOL_AUTH_DISABLED=1 uvicorn app.main:app --reload     # API su :8000
cd frontend && npm ci && VITE_API_BASE_URL=http://127.0.0.1:8000 npm run dev
pytest backend/tests                       # con DATABASE_URL=postgresql://... gira su Postgres
```

## Limiti della versione cloud
- Ogni richiesta verso Vercel accetta circa 4,5 MB: il frontend invia i file a gruppi; un singolo file/ZIP più grande va diviso.
- Rimosse perché legate al Mac locale: cartelle sorvegliate (watcher), backup SQLite, notifiche macOS, OCR (PDF scansionati senza testo non sono leggibili), sincronizzazione dashboard-cloud.
- I backup del database sono quelli gestiti da Supabase (verifica il piano per i backup/point-in-time).
