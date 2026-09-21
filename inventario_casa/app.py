from flask import Flask, render_template, send_from_directory
import os
from pathlib import Path
import json
import threading
from frontend import FRONTEND_ASSETS, asset_version, load_translations
from backup_routes import create_backup_blueprint
from media_routes import create_media_blueprint
from type_routes import create_type_blueprint
from item_routes import create_item_blueprint
from lookup_routes import create_lookup_blueprint
from inventory_routes import create_inventory_blueprint
from location_routes import create_location_blueprint
from backup_restore import restore_database_backup as backup_restore_database
from database import (
    db as database_connect,
    table_columns,
    read_schema_version as database_read_schema_version,
    write_schema_version,
    ensure_column,
    ensure_type_field,
    init_db as database_init,
)

APP_NAME = "Inventario Casa"

def env_int(name, default, minimum=1):
    try:
        value = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)


BACKUP_KEEP_MANUAL = env_int("INVENTORY_BACKUP_KEEP_MANUAL", 10)
BACKUP_KEEP_PRE_RESTORE = env_int("INVENTORY_BACKUP_KEEP_PRE_RESTORE", 5)
BACKUP_KEEP_PRE_SCHEMA = env_int("INVENTORY_BACKUP_KEEP_PRE_SCHEMA", 5)
DATA_DIR = Path("/data/inventario_casa")
DB_PATH = DATA_DIR / "inventario.db"
MEDIA_DIR = Path("/media/inventario_casa/oggetti")
DB_BACKUP_DIR = Path("/media/inventario_casa/db_backups")

CURRENT_SCHEMA_VERSION = 1

DB_MAINTENANCE_LOCK = threading.Lock()
STARTUP_DB_ERROR = None

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 25 * 1024 * 1024



def db():
    return database_connect(DB_PATH, DATA_DIR, MEDIA_DIR)


def read_schema_version():
    return database_read_schema_version(DB_PATH)




def set_startup_db_error(value):
    global STARTUP_DB_ERROR
    STARTUP_DB_ERROR = value


def restore_database_backup(filename):
    return backup_restore_database(
        filename,
        db_path=DB_PATH,
        data_dir=DATA_DIR,
        backup_dir=DB_BACKUP_DIR,
        maintenance_lock=DB_MAINTENANCE_LOCK,
        backup_keep_pre_restore=BACKUP_KEEP_PRE_RESTORE,
        init_db=init_db,
        set_startup_error=set_startup_db_error,
    )


def init_db():
    return database_init(
        DB_PATH,
        DATA_DIR,
        MEDIA_DIR,
        DB_BACKUP_DIR,
        CURRENT_SCHEMA_VERSION,
        BACKUP_KEEP_PRE_SCHEMA,
    )

try:
    init_db()
except Exception as exc:
    STARTUP_DB_ERROR = f"{type(exc).__name__}: {exc}"
    print(
        "[Inventario Casa] ERRORE inizializzazione database. "
        "Avvio modalità Recovery: "
        + STARTUP_DB_ERROR
    )


app.register_blueprint(
    create_inventory_blueprint(
        db=db,
    )
)


app.register_blueprint(
    create_location_blueprint(
        db=db,
    )
)


app.register_blueprint(
    create_lookup_blueprint()
)


app.register_blueprint(
    create_backup_blueprint(
        db_path=DB_PATH,
        backup_dir=DB_BACKUP_DIR,
        maintenance_lock=DB_MAINTENANCE_LOCK,
        backup_keep_manual=BACKUP_KEEP_MANUAL,
        get_startup_error=lambda: STARTUP_DB_ERROR,
        restore_database_backup=restore_database_backup,
    )
)


app.register_blueprint(
    create_item_blueprint(
        db=db,
        media_dir=MEDIA_DIR,
    )
)


app.register_blueprint(
    create_type_blueprint(
        db=db,
    )
)


app.register_blueprint(
    create_media_blueprint(
        db=db,
        media_dir=MEDIA_DIR,
    )
)






FRONTEND_ASSET_VERSION = asset_version(app.static_folder)
FRONTEND_TRANSLATIONS = load_translations(app.static_folder)


@app.get("/assets/<version>/<path:filename>")
def frontend_asset(version, filename):
    if version != FRONTEND_ASSET_VERSION:
        return "", 404

    if filename not in FRONTEND_ASSETS:
        return "", 404

    return send_from_directory(app.static_folder, filename)


@app.get("/")
def index():
    if STARTUP_DB_ERROR:
        return render_template(
            "recovery.html",
            startup_error=STARTUP_DB_ERROR,
        )
    return render_template(
        "index.html",
        asset_version=FRONTEND_ASSET_VERSION,
        translations=FRONTEND_TRANSLATIONS,
        default_language=os.environ.get("INVENTORY_LANGUAGE", "it"),
    )

