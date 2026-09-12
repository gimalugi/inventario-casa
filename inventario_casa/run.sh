#!/usr/bin/with-contenv bashio
set -e

DATA_DIR="/data/inventario_casa"
DB_PATH="${DATA_DIR}/inventario.db"
MEDIA_DIR="/media/inventario_casa/oggetti"

if [ -f "${DB_PATH}" ]; then
    bashio::log.info "[Inventario Casa] Database esistente rilevato."
    FIRST_START=0
else
    bashio::log.info "[Inventario Casa] Database non trovato."
    bashio::log.info "[Inventario Casa] Creazione nuovo archivio..."
    FIRST_START=1
fi

mkdir -p "${DATA_DIR}"
mkdir -p "${MEDIA_DIR}"

cd /app

# L'import dell'app verifica il database.
# Se una migrazione fallisce, Flask viene comunque avviato in modalità Recovery.
if python3 -c 'import app,sys; sys.exit(1 if app.STARTUP_DB_ERROR else 0)'; then
    if [ "${FIRST_START}" -eq 1 ]; then
        bashio::log.info "[Inventario Casa] Database inizializzato correttamente."
    else
        bashio::log.info "[Inventario Casa] Verifica struttura e migrazioni completata."
    fi
else
    bashio::log.warning "[Inventario Casa] Problema database rilevato."
    bashio::log.warning "[Inventario Casa] Avvio interfaccia in modalità Recovery."
fi

exec gunicorn \
  --bind 0.0.0.0:8099 \
  --workers 1 \
  --threads 4 \
  --access-logfile - \
  --error-logfile - \
  app:app
