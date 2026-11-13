# Inventario Casa v2.5.5

## Italiano

Questa versione rafforza la sicurezza dei ripristini senza cambiare lo schema SQLite.

- Richieste al database serializzate durante il ripristino e connessioni SQLite chiuse esplicitamente.
- Backup estranei, incompleti, con riferimenti non validi o schema futuro rifiutati prima della sostituzione.
- Migrazioni del candidato temporaneo prima del ripristino; blocco se il backup di sicurezza di un database sano fallisce.
- Recupero da database corrente corrotto e compatibilit? con backup legacy mantenuti.
- Correzione della retention dei backup pre-restore e della paginazione con nomi contenenti caratteri speciali.
- Foto e miniature conservate su disco dopo la rimozione dall?inventario per mantenere recuperabili i vecchi backup.

**Fotografie:** i backup `.db` non includono i file immagine. Salvare separatamente `/media/inventario_casa/oggetti/`. Le immagini rimosse continuano a occupare spazio e non vengono pulite automaticamente. Non ? possibile recuperare immagini gi? eliminate dalle versioni precedenti senza un backup media.

**Verifiche:** 14 test Python superati su Windows e Linux; 8 azioni di paginazione JavaScript; verifica sintassi frontend, traduzioni e prova dell?app completa in container Linux isolato, senza rete e senza dati di produzione. La verifica visuale su smartphone dopo installazione resta da eseguire.

## English

This release hardens restore safety without changing the SQLite schema.

- Serialized database requests during restore and explicitly closed SQLite connections.
- Rejected unrelated/incomplete backups, invalid references and future schemas before replacement.
- Migrated the temporary candidate before restoring; stopped if a healthy database cannot be backed up safely.
- Preserved recovery from corrupt current databases and compatibility with legacy backups.
- Fixed pre-restore backup retention and pagination with special characters in names.
- Retained photos and thumbnails on disk after removing inventory records so older backups remain recoverable.

**Photos:** `.db` backups do not contain image files. Back up `/media/inventario_casa/oggetti/` separately. Removed images continue to occupy storage and are not automatically cleaned up. Images deleted by earlier releases require a media backup to recover.

**Validation:** 14 Python tests passed on Windows and Linux; 8 JavaScript pagination actions; frontend syntax, translations and full-app smoke checks in an isolated Linux container without network access or production data. Visual checks on a smartphone after installation remain outstanding.
