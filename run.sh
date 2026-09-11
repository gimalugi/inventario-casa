#!/usr/bin/with-contenv bashio
set -e

mkdir -p /data/inventario_casa
mkdir -p /media/inventario_casa/oggetti

cd /app
exec gunicorn   --bind 0.0.0.0:8099   --workers 1   --threads 4   --access-logfile -   --error-logfile -   app:app
