# Istruzioni operative per Inventario Casa

Queste istruzioni si applicano all'intero repository.

## Architettura attuale

Inventario Casa è un'app per Home Assistant con backend Python/Flask, database SQLite e frontend HTML, CSS e JavaScript puro. Il codice applicativo risiede in `inventario_casa/`.

- `app.py` crea l'app Flask, inizializza il database, registra i blueprint delle API e serve la pagina principale o la pagina Recovery.
- `wsgi.py` espone l'app a Gunicorn; `run.sh` avvia il server sulla porta 8099. `config.yaml` configura l'app e Home Assistant Ingress; `Dockerfile` e `requirements.txt` definiscono ambiente e dipendenze.
- `inventory_routes.py`, `item_routes.py`, `type_routes.py`, `location_routes.py`, `media_routes.py`, `lookup_routes.py` e `backup_routes.py` suddividono le API per responsabilità.
- `database.py` gestisce connessioni SQLite, inizializzazione e migrazioni. `backup.py` e `backup_restore.py` gestiscono backup, conservazione e ripristino. La versione dello schema è registrata in `app_meta`; la versione attesa è definita in `app.py`.
- `templates/index.html` definisce la struttura dell'interfaccia; `static/js/app.js` contiene la logica del browser e `static/css/app.css` gli stili. `frontend.py` carica le traduzioni e calcola il versionamento degli asset tramite hash. `templates/recovery.html` contiene l'interfaccia di recupero.
- Il frontend comunica con le API Flask tramite `fetch()` e URL relativi `api/...`, con dati JSON; gli upload usano `FormData`. Le immagini sono servite da `/files/...`. Preservare i percorsi relativi utilizzati dal browser per funzionare dietro Ingress.
- `static/translations/it.json` e `en.json` contengono i testi dell'interfaccia; `translations/it.yaml` e `en.yaml` traducono le opzioni di configurazione in Home Assistant.
- I percorsi persistenti di produzione sono `/data/inventario_casa/inventario.db`, `/media/inventario_casa/oggetti/` e `/media/inventario_casa/db_backups/`.
- `DOCS.md`, `CHANGELOG.md` e `REGRESSION_CHECKLIST.md`, nella cartella `inventario_casa/`, contengono documentazione, cronologia e verifiche di regressione.

## Modifiche al codice

- Prima di modificare codice, analizzare i file coinvolti e limitare le modifiche allo stretto necessario.
- Non modificare funzionalità non interessate dalla richiesta.
- Non eliminare o sovrascrivere funzioni esistenti senza verificarne gli utilizzi.
- Mantenere separati frontend e backend secondo l'architettura esistente, rispettando la suddivisione dei moduli per responsabilità.
- Preservare la compatibilità con Home Assistant Ingress, inclusi i percorsi di API, asset e fotografie.
- Preservare italiano e inglese. Quando si aggiungono testi all'interfaccia, aggiornare entrambe le traduzioni pertinenti.
- Evitare nuove dipendenze JavaScript o framework se non esplicitamente richiesti.

## Database e protezione dei dati

- Non modificare direttamente database SQLite di produzione o dati presenti in `/data` e `/media`.
- Qualsiasi modifica allo schema del database deve utilizzare il sistema di migrazione esistente e mantenere la compatibilità con installazioni precedenti, preservando i dati già presenti.
- Per operazioni potenzialmente distruttive prevedere un backup e una possibilità concreta di rollback prima di procedere.
- Per le verifiche usare dati temporanei o copie isolate, senza intervenire sui dati di produzione.

## Verifiche

- Prima di considerare terminata una modifica, verificare le possibili regressioni e utilizzare `inventario_casa/REGRESSION_CHECKLIST.md` quando pertinente.
- Eseguire verifiche proporzionate alle modifiche e riportare quelle effettuate, segnalando eventuali verifiche non eseguite o limiti riscontrati.

## Versioni e release

- Non incrementare automaticamente la versione dell'app.
- Non creare tag, release GitHub, push o commit salvo richiesta esplicita.
- Prima di una release mostrare un riepilogo delle modifiche e attendere conferma.
- Mantenere aggiornato `inventario_casa/CHANGELOG.md` quando viene preparata una release.
