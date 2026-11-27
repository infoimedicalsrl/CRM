# Peppol Sales Analytics V6.9.15 — Fatture e Ordini Clienti

## Fatture acquisti
- Import Excel riconosce anche l'intestazione `Nr. acquisto` come numero fattura.
- Rimossa la dicitura del formato sotto al numero fattura.
- Card di importazione con selezione file diretta, senza form intermedio.
- Rimossa la descrizione lunga dall'intestazione della pagina.
- Badge di stato e riconciliazione non vanno a capo; tabella con larghezza minima adeguata.
- Riconciliazione bancaria più prudente: importo e fornitore sono verificati; quando esistono più movimenti compatibili, la causale deve contenere il numero fattura. Se non è possibile distinguere con sicurezza, non viene dichiarato un abbinamento automatico.

## Fatture vendita
- Rimossa l'azione/colonna `Trova incasso` dalla tabella; rimane visibile lo stato di riconciliazione.
- I campi del dettaglio restano in sola lettura fino al pulsante `Modifica fattura`.

## Ordini Clienti
- Sezione rinominata `Ordini Clienti` nella pagina e nella navigazione.
- Aggiunte le card `Totale ordini`, `Ordini visualizzati` e `Importa un Ordine`.
- Il totale e il conteggio seguono i filtri attivi.
- Importazione diretta da card: selezione XML singolo o ZIP massivo; non viene aperto il vecchio pannello di importazione.

## Verifiche
- Compilazione sintattica Python completata.
- 24 test backend superati (i test che dipendono da file XML di ambiente non disponibili sono esclusi).
- La build frontend completa non è stata eseguita in questo ambiente: il pacchetto non contiene `node_modules`.
