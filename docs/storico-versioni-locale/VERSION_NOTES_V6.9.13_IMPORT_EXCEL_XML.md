# Peppol V6.9.13 — Import fatture acquisti Excel/XML

- La sezione Fatture acquisti accetta file Excel `.xls` e `.xlsx` (anche con più righe/fatture) oppure singoli XML FatturaPA.
- Tabella limitata alle colonne richieste: # Fattura ricevuta, Data, Fornitore, P.IVA, CF, Imponibile, IVA.
- Il CF del fornitore è letto dall'XML o dalla colonna CF del foglio Excel.
- Il totale acquisti resta calcolato come imponibile + IVA e risponde ai filtri attivi.
- L'importazione Excel riconosce le intestazioni nella prima parte del foglio e segnala righe non valide; non importa parzialmente un file con errori.
- La migrazione aggiunge `supplier_cf` senza eliminare i dati esistenti.
