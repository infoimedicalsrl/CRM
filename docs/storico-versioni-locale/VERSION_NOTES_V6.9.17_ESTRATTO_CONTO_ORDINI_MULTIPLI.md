# Peppol Sales Analytics V6.9.17 — Estratto conto online e ordini multipli

## Ordini Clienti
- La card `Importa un Ordine` consente di scegliere un singolo XML, più file XML contemporaneamente oppure un archivio ZIP.
- Un singolo XML usa l'endpoint di importazione singola; selezioni multiple e ZIP usano l'endpoint di importazione massiva.
- Al termine dell'importazione vengono aggiornati gli ordini e i dati collegati nella dashboard, clienti, prodotti e analisi.

## Estratto conto online
- Riorganizzata la pagina in tre card: `Righe importate`, `Abbinate` e caricamento dell'estratto conto.
- Rimosso il pulsante Import dalla barra delle azioni; restano `Ricalcola abbinamenti` e `Aggiorna`.
- Il caricamento CSV/PDF è accessibile direttamente dalla card, con selezione file e importazione.
- Rimossi dalla scheda di riepilogo il nome del file, l'anno elaborato, i conteggi testuali duplicati, la descrizione CSV e il collegamento `Apri originale`.
- La tabella occupa tutta la larghezza disponibile. Lo storico importazioni è stato spostato in un pannello espandibile sopra la tabella, per lasciare più spazio ai dati.

## Verifica
- Il controllo di build frontend non è stato completato in questo ambiente: il pacchetto `vite/client` non era disponibile e l'installazione delle dipendenze è andata in timeout. Eseguire `npm ci` e `npm run build` nella cartella `frontend` prima della distribuzione.
