# Peppol V6.9.7 — Correzione KPI dashboard

- Fatturato netto: somma degli imponibili delle fatture di vendita emesse nel periodo selezionato.
- IVA: somma dell’IVA registrata nelle fatture di vendita emesse nel periodo selezionato.
- Crediti verso i clienti: somma degli importi lordi degli ordini clienti nel periodo selezionato. Questo indicatore rappresenta il totale ordini, non il residuo contabile aperto dopo gli incassi.
- Totale incasso: somma dei movimenti bancari in entrata nel periodo selezionato, escludendo i movimenti marcati come possibili duplicati salvo revisione esplicita.
- Rimossa la card Fatturato lordo e rimosse le icone decorative dalle card KPI e dai titoli delle sezioni richieste.
- Aggiunto endpoint `/api/dashboard/financial-summary` per separare le fonti dati delle metriche.

Nota: il totale incasso riflette gli accrediti bancari importati, non necessariamente tutti i pagamenti non bancari o registrati fuori dall’app.
