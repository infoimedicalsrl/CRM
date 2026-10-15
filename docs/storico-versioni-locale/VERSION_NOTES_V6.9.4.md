# Peppol V6.9.4 — Dettaglio fatture e importazioni riorganizzate

## Fatture di vendita
- Rimosso il selettore a tendina per l'ordinamento; la colonna Data usa una freccia per alternare dalla più recente alla più vecchia e viceversa.
- La riga fattura apre una pagina di dettaglio.
- La pagina di dettaglio riproduce i dati archiviati della fattura e permette di modificare numero, data, cliente, identificativi fiscali, valuta e importi.
- Nella pagina di dettaglio vengono mostrate le righe dell'estratto conto cliente abbinate, gli incassi bancari collegati e i DDT associati al cliente identificato.
- Il pulsante di inserimento manuale è ora un'icona a matita vicino ad Aggiorna.

## Clienti
- Aggiunta la card Fatture sotto la card Ordini, con le fatture riconosciute per partita IVA o nome cliente e collegamento al dettaglio.

## Importazioni
- Spostato il caricamento estratto conto cliente nella pagina Importazioni, dentro una card collassabile chiusa inizialmente.
- Tutte le modalità di importazione sono organizzate in card collassabili e chiuse inizialmente.
- Aggiunta importazione massiva ordini fornitori: selezione di più XML oppure un archivio ZIP con XML.
- Aggiunti riepiloghi per fatture, estratto conto cliente e importazione massiva ordini, con esito per ciascun file.

## Verifiche
- Verificata la sintassi Python e l'importazione dei moduli backend.
- La build TypeScript/Vite non è stata completata in questo ambiente: le dipendenze frontend non sono disponibili e l'installazione npm è andata in timeout per problemi di rete.
- L'importazione massiva XML/ZIP e la UI devono ancora essere verificate end-to-end su Mac con le dipendenze installate.
