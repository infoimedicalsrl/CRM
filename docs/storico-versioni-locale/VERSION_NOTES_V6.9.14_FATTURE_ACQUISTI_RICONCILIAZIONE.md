# Peppol Sales Analytics V6.9.14 — Fatture vendita/acquisti e riconciliazione

## Fatture vendita
- Aggiunte tre card in testa alla pagina: **Totale vendita**, **Fatture visualizzate** e **Importa fattura**.
- La card di importazione apre direttamente il selettore file e instrada automaticamente l'importazione in base all'estensione: PDF/XML verso il parser fattura già esistente, XLS/XLSX/XLSM verso l'importazione massiva Excel.
- Non viene più aperto il pannello che chiedeva di scegliere manualmente il tipo di importazione.

## Fatture acquisti
- L'elenco mostra Data, Nr. Fattura, Fornitore, Valuta orig., Imponibile, IVA, Prox scadenza, Stato e Riconciliazione.
- Ogni riga apre una pagina dettaglio con layout coerente con il dettaglio delle fatture vendita e possibilità di modificare/salvare i dati.
- Il dettaglio contiene solo la card **Movimenti bancari** nella sezione Documenti collegati.
- I campi estesi del file Excel vengono memorizzati: data, prossima scadenza, numero fattura, fornitore, partita IVA, codice fiscale, indirizzo, comune, provincia, CAP, paese, descrizione, valuta originale, imponibile e IVA.
- La migrazione SQLite aggiunge colonne senza eliminare i dati già presenti.
- Lo stato viene calcolato come Pagata quando si trova un movimento bancario in uscita con importo corrispondente al totale della fattura (tolleranza € 0,02) e controparte/causale compatibile col fornitore. La colonna Riconciliazione indica Riconciliata o Da riconciliare.
- Il matching normalizza nomi e ragioni sociali, così un fornitore come “Eurosets Srl” può corrispondere a una causale che riporta semplicemente “EUROSETS”.

## Verifiche
- `python -m compileall -q backend/app`: superato.
- Test backend: 24 superati (`PYTHONPATH=. pytest -q --ignore=tests/test_parser.py`). I test `test_parser.py` richiedono variabili ambiente specifiche e non sono inclusi in questa esecuzione.
- Il controllo TypeScript/build frontend non è stato completato: l'installazione npm nell'ambiente è andata in timeout e mancava `vite/client`. Il progetto deve completare l'installazione delle dipendenze al primo avvio.

## Aggiornamento
Prima di sostituire una versione già in uso, fai una copia di sicurezza e conserva il tuo `data/database.sqlite`. Non sovrascrivere il database di produzione con quello incluso nel pacchetto.
