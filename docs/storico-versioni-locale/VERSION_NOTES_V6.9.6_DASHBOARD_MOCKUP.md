# Peppol Sales Analytics V6.9.6 — Dashboard e tema grafico

## Modifiche
- Ridisegnata la dashboard in base al mockup `Dashboard italiano Peppol Sales Analytics.png` recuperato dalla Libreria.
- Layout con sidebar blu notte, area contenuti chiara, bordi azzurri, card economiche colorate, grafico annuale, distribuzione clienti, fatture per stato, top 5 clienti e colonna destra con fatture recenti e attività basate sulle fatture presenti.
- Aggiunta la quarta metrica “Crediti verso i clienti”, calcolata come somma degli importi lordi degli ordini clienti nel periodo selezionato (coerente con la richiesta “somma tutti gli ordini clienti”; non rappresenta un saldo contabile al netto degli incassi).
- Filtro predefinito dall'1 gennaio al 31 dicembre dell'anno corrente; selezione rapida dell'anno e filtro avanzato mantenuti.
- Aggiornata la palette semantica globale e lo stile della sidebar per avvicinare tutte le sezioni al tema del mockup.

## Note di verifica
- Il pacchetto mantiene backend, database e funzionalità della V6.9.5.
- Verifica dell'integrità ZIP effettuata alla creazione.
- Build frontend non completata nell'ambiente di preparazione: `npm ci` è andato in timeout e il binario locale di TypeScript/Vite non era disponibile. Eseguire `npm install` al primo avvio con connessione Internet e verificare l'interfaccia sul Mac prima di considerare la versione convalidata end-to-end.
