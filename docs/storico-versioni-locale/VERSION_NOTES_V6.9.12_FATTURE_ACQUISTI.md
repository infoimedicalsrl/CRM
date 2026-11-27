# V6.9.13 — Fatture acquisti

- Aggiunta la voce **Fatture acquisti** sotto **Fatture vendita** nel menu laterale.
- Aggiunto un archivio database distinto per le fatture ricevute dai fornitori, senza modificare le fatture di vendita.
- Aggiunta card **Totale Acquisti**, calcolata sul backend e aggiornata con filtro fornitore e ricerca testuale.
- Aggiunta importazione XML FatturaPA e file Excel (.xls/.xlsx) o XML FatturaPA, tabella con ordinamento e prevenzione dei duplicati.
- Gli XML vengono interpretati usando `CedentePrestatore` come fornitore e `ImportoTotaleDocumento` come totale fattura.
- I PDF scansionati senza testo estraibile richiedono un XML o un file Excel (.xls/.xlsx) o XML FatturaPA.

## Verifiche

La creazione della tabella è gestita da `Base.metadata.create_all` all'avvio. Eseguire i controlli Python e la build frontend descritti nelle istruzioni del progetto prima dell'uso operativo.

## Esito controlli in ambiente di sviluppo

- Sintassi Python: superata.
- Test backend disponibili senza fixture esterne: 21 superati.
- Due test preesistenti di parsing ordini richiedono i percorsi XML tramite le variabili `PEPPOL_SIMPLE_XML` e `PEPPOL_MULTI_XML`, non disponibili in questo ambiente.
- TypeScript (`npx tsc --noEmit`): superato.
- La fase di bundling Vite non è stata completata nell'ambiente Linux di verifica: manca il binding nativo opzionale Rolldown per Linux. Lo script di avvio del progetto controlla e reinstalla le dipendenze frontend se incomplete; il bundle va comunque verificato su Mac con `npm install` e `npm run build`.
