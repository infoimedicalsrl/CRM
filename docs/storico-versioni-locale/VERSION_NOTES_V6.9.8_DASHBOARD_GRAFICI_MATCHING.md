Peppol Sales Analytics — V6.9.8

Modifiche:
- Dashboard: grafico andamento fatturato mostra netto e lordo insieme; i due pulsanti attivano/disattivano le serie senza nascondere entrambe.
- Dashboard: grafico a ciambella con dimensioni responsive e margini per evitare il taglio.
- Estratto conto cliente: l'abbinamento non limita più le fatture all'anno corrente; prova a disambiguare fatture con stesso numero usando la data incorporata nel riferimento.
- Estratto conto cliente: nuova azione “Ricalcola abbinamenti” per rieseguire il matching sulle righe già importate dopo aver corretto la logica o importato le fatture mancanti.

Verifiche eseguite:
- Compilazione sintattica Python (`compileall`) completata.
- Integrità ZIP verificata.
- Build frontend completa non eseguita in questo ambiente.
