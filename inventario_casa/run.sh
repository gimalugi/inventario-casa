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

# L'import dell'app esegue init_db(): crea un database nuovo quando manca
# oppure applica esclusivamente le migrazioni additive previste.
python3 -c 'import app'

if [ "${FIRST_START}" -eq 1 ]; then
    bashio::log.info "[Inventario Casa] Database inizializzato correttamente."
else
    bashio::log.info "[Inventario Casa] Verifica struttura e migrazioni completata."
fi

exec gunicorn \
  --bind 0.0.0.0:8099 \
  --workers 1 \
  --threads 4 \
  --access-logfile - \
  --error-logfile - \
  app:app
