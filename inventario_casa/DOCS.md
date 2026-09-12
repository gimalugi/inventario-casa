# Inventario Casa v0.1.21

Versione correttiva e completa.

Aggiornamento:
1. Sostituire i file in `/addons/inventario_casa` con questa versione.
2. In Home Assistant ricostruire/reinstallare l'App.
3. Non cancellare i dati dell'App.

Persistenza:
- Database: `/data/inventario_casa/inventario.db`
- Foto: `/media/inventario_casa/oggetti`

La migrazione è additiva: conserva gli elementi e i campi già presenti.

Novità 0.1.7: ogni campo personalizzato può avere un testo di esempio facoltativo.

Novità 0.1.8: layout responsive smartphone completamente rivisto.

Novità 0.1.9: contrasto mobile migliorato e dettatura vocale nei campi testuali compatibili.

Correzione 0.1.10: migrazione automatica del vecchio schema foto (`caption` -> `label`).

Novità 0.1.11: pannello Tipologie compatto, ricerca, riduzione/espansione ed eliminazione sicura.
