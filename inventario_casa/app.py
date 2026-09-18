import hashlib
from flask import Flask, request, jsonify, render_template, render_template_string, send_from_directory
import sqlite3
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageOps
from pyzbar.pyzbar import decode as zbar_decode
import uuid
import json
import re
import threading
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

APP_NAME = "Inventario Casa"
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
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def table_columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def read_schema_version():
    if not DB_PATH.exists():
        return 0

    conn = sqlite3.connect(DB_PATH)
    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='app_meta'"
        ).fetchone()

        if not exists:
            return 0

        row = conn.execute(
            "SELECT value FROM app_meta WHERE key='schema_version'"
        ).fetchone()

        if not row:
            return 0

        try:
            return int(row[0])
        except (TypeError, ValueError):
            return 0
    finally:
        conn.close()


def create_pre_migration_backup(from_version, to_version):
    DB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = DB_BACKUP_DIR / (
        f"inventario_pre_schema_{from_version}_to_{to_version}_{stamp}.db"
    )

    source = sqlite3.connect(DB_PATH)
    target = sqlite3.connect(backup_path)

    try:
        source.backup(target)
        target.commit()

        result = target.execute("PRAGMA integrity_check").fetchone()
        integrity = result[0] if result else ""

        if integrity != "ok":
            raise RuntimeError(
                f"Backup DB non valido: integrity_check={integrity!r}"
            )
    except Exception:
        target.close()
        source.close()

        try:
            backup_path.unlink(missing_ok=True)
        except Exception:
            pass

        raise
    else:
        target.close()
        source.close()

    print(
        f"[Inventario Casa] Backup pre-migrazione creato: {backup_path}"
    )

    return backup_path



def inspect_database_file(path):
    """Controlla integrità e informazioni essenziali di un DB SQLite."""
    path = Path(path)

    result = {
        "valid": False,
        "integrity": "",
        "items": None,
        "types": None,
        "photos": None,
        "schema_version": None,
    }

    if not path.exists():
        result["integrity"] = "file non trovato"
        return result

    conn = None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)

        row = conn.execute("PRAGMA integrity_check").fetchone()
        integrity = row[0] if row else ""

        result["integrity"] = integrity
        result["valid"] = integrity == "ok"

        if not result["valid"]:
            return result

        tables = {
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }

        if "items" in tables:
            result["items"] = conn.execute(
                "SELECT COUNT(*) FROM items"
            ).fetchone()[0]

        if "item_types" in tables:
            result["types"] = conn.execute(
                "SELECT COUNT(*) FROM item_types"
            ).fetchone()[0]

        if "item_photos" in tables:
            result["photos"] = conn.execute(
                "SELECT COUNT(*) FROM item_photos"
            ).fetchone()[0]

        if "app_meta" in tables:
            row = conn.execute(
                "SELECT value FROM app_meta WHERE key='schema_version'"
            ).fetchone()
            if row:
                try:
                    result["schema_version"] = int(row[0])
                except (TypeError, ValueError):
                    result["schema_version"] = row[0]
        else:
            result["schema_version"] = 0

        return result

    except Exception as exc:
        result["integrity"] = str(exc)
        return result

    finally:
        if conn is not None:
            conn.close()


def backup_path_from_name(filename):
    """Accetta esclusivamente file .db presenti nella cartella backup."""
    filename = Path(str(filename or "")).name

    if not filename or not filename.endswith(".db"):
        raise ValueError("Nome backup non valido")

    path = DB_BACKUP_DIR / filename

    try:
        path.resolve().relative_to(DB_BACKUP_DIR.resolve())
    except ValueError:
        raise ValueError("Percorso backup non valido")

    if not path.exists() or not path.is_file():
        raise FileNotFoundError("Backup non trovato")

    return path


def create_database_backup(prefix="inventario_manuale", verify=True):
    """Crea una copia SQLite consistente del database corrente."""
    if not DB_PATH.exists():
        raise FileNotFoundError("Database principale non trovato")

    DB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = DB_BACKUP_DIR / f"{prefix}_{stamp}.db"

    source = sqlite3.connect(DB_PATH)
    target = sqlite3.connect(backup_path)

    try:
        source.backup(target)
        target.commit()
    finally:
        target.close()
        source.close()

    if verify:
        check = inspect_database_file(backup_path)
        if not check["valid"]:
            try:
                backup_path.unlink(missing_ok=True)
            except Exception:
                pass
            raise RuntimeError(
                "Il backup creato non supera il controllo di integrità: "
                + str(check["integrity"])
            )

    return backup_path


def list_database_backups():
    DB_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    rows = []

    for path in sorted(
        DB_BACKUP_DIR.glob("*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        stat = path.stat()
        check = inspect_database_file(path)

        rows.append({
            "filename": path.name,
            "size": stat.st_size,
            "modified": datetime.fromtimestamp(
                stat.st_mtime
            ).isoformat(timespec="seconds"),
            **check,
        })

    return rows


def restore_database_backup(filename):
    """
    Ripristina un backup verificato.

    Il backup viene prima copiato in un database SQLite temporaneo,
    verificato e solo dopo sostituisce atomicamente il database corrente.
    Questo permette il recovery anche quando il DB corrente è corrotto.
    """
    global STARTUP_DB_ERROR

    with DB_MAINTENANCE_LOCK:
        backup_path = backup_path_from_name(filename)

        # 1. Verifica preventiva del backup scelto.
        backup_info = inspect_database_file(backup_path)

        if backup_info.get("integrity") != "ok":
            raise RuntimeError(
                "Il backup selezionato non supera il controllo di integrità"
            )

        safety_backup = None
        safety_warning = None

        # 2. Prova a salvare il DB corrente prima del restore.
        #
        # In Recovery Mode il database corrente può essere illeggibile:
        # in quel caso il mancato safety backup NON deve impedire il
        # ripristino di un backup valido.
        if DB_PATH.exists():
            try:
                safety_backup = create_database_backup(
                    prefix="inventario_pre_restore",
                    verify=True,
                )
            except Exception as exc:
                safety_warning = (
                    "Impossibile creare il backup di sicurezza del "
                    f"database corrente: {type(exc).__name__}: {exc}"
                )
                print(
                    "[Inventario Casa] ATTENZIONE: "
                    + safety_warning
                )

        DATA_DIR.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        restore_tmp = DATA_DIR / f".inventario_restore_{stamp}.db"

        source = None
        target = None

        try:
            # 3. Ricostruisce il backup in un NUOVO DB.
            #
            # Non utilizziamo DB_PATH come destinazione perché potrebbe
            # essere un file SQLite corrotto.
            source = sqlite3.connect(str(backup_path))
            target = sqlite3.connect(str(restore_tmp))

            source.backup(target)
            target.commit()

            target.close()
            target = None

            source.close()
            source = None

            # 4. Verifica il DB temporaneo PRIMA di sostituire quello attivo.
            restored_info = inspect_database_file(restore_tmp)

            if restored_info.get("integrity") != "ok":
                raise RuntimeError(
                    "Il database ripristinato non supera "
                    "il controllo di integrità"
                )

            # 5. Elimina eventuali WAL/SHM del vecchio database.
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(DB_PATH) + suffix)
                try:
                    sidecar.unlink()
                except FileNotFoundError:
                    pass

            # 6. Sostituzione atomica del database corrente.
            restore_tmp.replace(DB_PATH)

            # 7. Esegue eventuali migrazioni necessarie.
            init_db()

            # 8. Verifica finale dopo init/migrazioni.
            final_info = inspect_database_file(DB_PATH)

            if final_info.get("integrity") != "ok":
                raise RuntimeError(
                    "Il database non supera il controllo "
                    "di integrità dopo il ripristino"
                )

            STARTUP_DB_ERROR = None

            return {
                "ok": True,
                "filename": backup_path.name,
                "safety_backup": (
                    safety_backup.name
                    if safety_backup is not None
                    else None
                ),
                "safety_warning": safety_warning,
                "database": final_info,
            }

        except Exception as exc:
            STARTUP_DB_ERROR = f"{type(exc).__name__}: {exc}"

            print(
                "[Inventario Casa] ERRORE ripristino database: "
                + STARTUP_DB_ERROR
            )

            raise

        finally:
            if target is not None:
                target.close()

            if source is not None:
                source.close()

            if restore_tmp.exists():
                try:
                    restore_tmp.unlink()
                except Exception:
                    pass


def write_schema_version(conn, version):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    conn.execute(
        """
        INSERT OR REPLACE INTO app_meta(key,value)
        VALUES('schema_version', ?)
        """,
        (str(version),),
    )


def ensure_column(conn, table, col, declaration):
    if col not in table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {declaration}")


def ensure_type_field(conn, type_name, label, field_type="text", required=0, options="", sort_order=0):
    t = conn.execute("SELECT id FROM item_types WHERE name=?", (type_name,)).fetchone()
    if not t:
        return
    exists = conn.execute(
        "SELECT id FROM type_fields WHERE type_id=? AND lower(label)=lower(?)",
        (t["id"], label),
    ).fetchone()
    if not exists:
        conn.execute(
            """INSERT INTO type_fields(type_id,label,field_type,required,options,sort_order,active)
               VALUES(?,?,?,?,?,?,1)""",
            (t["id"], label, field_type, required, options, sort_order),
        )


def init_db():
    # Le tipologie standard vengono create esclusivamente quando il database
    # viene creato per la prima volta. Dopo l'inizializzazione, tipologie e
    # campi appartengono all'utente e non devono essere ricreati al riavvio.
    new_database = not DB_PATH.exists()

    previous_schema_version = read_schema_version()

    if (
        DB_PATH.exists()
        and previous_schema_version < CURRENT_SCHEMA_VERSION
    ):
        print(
            "[Inventario Casa] Migrazione schema richiesta: "
            f"{previous_schema_version} -> {CURRENT_SCHEMA_VERSION}"
        )

        create_pre_migration_backup(
            previous_schema_version,
            CURRENT_SCHEMA_VERSION,
        )

    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS item_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                icon TEXT DEFAULT '📦',
                subgroup_field_id INTEGER,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                quantity INTEGER NOT NULL DEFAULT 1,
                item_type_id INTEGER,
                environment TEXT DEFAULT '',
                furniture TEXT DEFAULT '',
                shelf TEXT DEFAULT '',
                container_name TEXT DEFAULT '',
                container_code TEXT DEFAULT '',
                tags TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(item_type_id) REFERENCES item_types(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS type_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type_id INTEGER NOT NULL,
                label TEXT NOT NULL,
                field_type TEXT NOT NULL DEFAULT 'text',
                required INTEGER NOT NULL DEFAULT 0,
                options TEXT DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(type_id) REFERENCES item_types(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS item_custom_values (
                item_id INTEGER NOT NULL,
                field_id INTEGER NOT NULL,
                value TEXT DEFAULT '',
                PRIMARY KEY(item_id, field_id),
                FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE,
                FOREIGN KEY(field_id) REFERENCES type_fields(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS item_photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                thumb_filename TEXT NOT NULL,
                label TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_items_name ON items(name);
            CREATE INDEX IF NOT EXISTS idx_items_type ON items(item_type_id);
            CREATE INDEX IF NOT EXISTS idx_items_environment ON items(environment);
            """
        )

        ensure_column(conn, "items", "environment", "TEXT DEFAULT ''")
        ensure_column(conn, "items", "furniture", "TEXT DEFAULT ''")
        ensure_column(conn, "items", "shelf", "TEXT DEFAULT ''")
        ensure_column(conn, "items", "container_name", "TEXT DEFAULT ''")
        ensure_column(conn, "type_fields", "active", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(conn, "type_fields", "placeholder", "TEXT DEFAULT ''")
        ensure_column(conn, "item_types", "subgroup_field_id", "INTEGER")

        # Migrazione foto da versioni precedenti:
        # alcune versioni usavano 'caption' invece di 'label'.
        photo_cols = table_columns(conn, "item_photos")
        if "label" not in photo_cols:
            conn.execute("ALTER TABLE item_photos ADD COLUMN label TEXT DEFAULT ''")
            photo_cols.add("label")
        if "caption" in photo_cols:
            conn.execute(
                "UPDATE item_photos "
                "SET label=caption "
                "WHERE TRIM(COALESCE(label,''))='' "
                "AND TRIM(COALESCE(caption,''))<>''"
            )

        # Tipologie iniziali: vengono proposte soltanto su un database nuovo.
        # Dopo la prima inizializzazione l'utente può modificarle o eliminarle
        # e Inventario Casa non le ricreerà automaticamente.
        if new_database:
            now = datetime.now().isoformat(timespec="seconds")
            defaults = [
                ("Apparecchiature elettroniche", "🔌"),
                ("Libri", "📚"),
                ("Oggetti", "📦"),
            ]
            for name, icon in defaults:
                conn.execute(
                    "INSERT OR IGNORE INTO item_types(name,icon,created_at) VALUES(?,?,?)",
                    (name, icon, now),
                )

            libri = [
                ("Autore", "text", 0, ""),
                ("ISBN", "text", 0, ""),
                ("Editore", "text", 0, ""),
                ("Anno", "number", 0, ""),
            ]
            for idx, f in enumerate(libri):
                ensure_type_field(conn, "Libri", *f, sort_order=idx)

        write_schema_version(conn, CURRENT_SCHEMA_VERSION)

        print(
            "[Inventario Casa] Schema database verificato: "
            f"versione {CURRENT_SCHEMA_VERSION}"
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


def type_rows(conn):
    result = [dict(r) for r in conn.execute(
        "SELECT id,name,icon,subgroup_field_id FROM item_types ORDER BY name COLLATE NOCASE"
    )]
    for t in result:
        t["fields"] = [dict(r) for r in conn.execute(
            """SELECT id,label,field_type,required,options,sort_order,active,placeholder
               FROM type_fields
               WHERE type_id=?
               ORDER BY sort_order,id""",
            (t["id"],),
        )]
    return result


def item_custom_values(conn, item_id):
    return {
        str(r["field_id"]): r["value"]
        for r in conn.execute(
            "SELECT field_id,value FROM item_custom_values WHERE item_id=?",
            (item_id,),
        )
    }


def distinct_values(conn, column):
    return [
        r["v"]
        for r in conn.execute(
            f"""SELECT DISTINCT {column} AS v
                FROM items
                WHERE TRIM(COALESCE({column},'')) <> ''
                ORDER BY v COLLATE NOCASE"""
        )
    ]


@app.get("/api/bootstrap")
def api_bootstrap():
    q = request.args.get("q", "").strip()
    try:
        limit = int(request.args.get("limit", "20"))
    except (TypeError, ValueError):
        limit = 20
    if limit not in {20, 50, 100}:
        limit = 20

    with db() as conn:
        types = type_rows(conn)

        where_sql = ""
        params = []
        if q:
            like = f"%{q}%"
            cols = [
                "i.name", "i.description", "i.tags", "i.notes",
                "i.environment", "i.furniture", "i.shelf",
                "i.container_name", "i.container_code"
            ]
            where_sql = " WHERE " + " OR ".join(f"{c} LIKE ?" for c in cols)
            where_sql += """ OR EXISTS(
                SELECT 1 FROM item_custom_values cv
                WHERE cv.item_id=i.id AND cv.value LIKE ?
            )"""
            params = [like] * (len(cols) + 1)

        matched_count = conn.execute(
            "SELECT COUNT(*) FROM items i" + where_sql,
            params,
        ).fetchone()[0]

        sql = """
            SELECT i.*, t.name AS type_name, t.icon AS type_icon
            FROM items i
            LEFT JOIN item_types t ON t.id=i.item_type_id
        """ + where_sql
        sql += " ORDER BY i.updated_at DESC, i.name COLLATE NOCASE LIMIT ?"

        items = [dict(r) for r in conn.execute(sql, [*params, limit])]
        for item in items:
            item["custom_values"] = item_custom_values(conn, item["id"])
            item["photos"] = [dict(r) for r in conn.execute(
                """SELECT id,filename,thumb_filename,COALESCE(label,'') AS label
                   FROM item_photos
                   WHERE item_id=?
                   ORDER BY id""",
                (item["id"],),
            )]
            item["position_path"] = " → ".join(
                x for x in [
                    item["environment"],
                    item["furniture"],
                    item["shelf"],
                    item["container_name"],
                ] if x
            )

        envs = distinct_values(conn, "environment")
        return jsonify(
            types=types,
            items=items,
            list_limit=limit,
            matched_count=matched_count,
            suggestions={
                "environment": envs,
                "furniture": distinct_values(conn, "furniture"),
                "shelf": distinct_values(conn, "shelf"),
                "container": distinct_values(conn, "container_name"),
            },
            counts={
                "items": conn.execute("SELECT COUNT(*) FROM items").fetchone()[0],
                "environments": len(envs),
                "types": len(types),
            }
        )



def inventory_search_where(q):
    q = (q or "").strip()
    if not q:
        return "", []
    like = f"%{q}%"
    cols = [
        "i.name", "i.description", "i.tags", "i.notes",
        "i.environment", "i.furniture", "i.shelf",
        "i.container_name", "i.container_code"
    ]
    where_sql = " WHERE " + " OR ".join(f"{c} LIKE ?" for c in cols)
    where_sql += """ OR EXISTS(
        SELECT 1 FROM item_custom_values cv
        WHERE cv.item_id=i.id AND cv.value LIKE ?
    )"""
    return where_sql, [like] * (len(cols) + 1)


def append_inventory_condition(where_sql, condition):
    if not condition:
        return where_sql
    if where_sql:
        return where_sql + " AND " + condition
    return " WHERE " + condition


def inventory_sort_select_sql():
    # Se la tipologia possiede un campo attivo chiamato "Numero",
    # lo usa per l'ordinamento numerico. Per i tipi senza Numero
    # il normale ordinamento alfabetico resta invariato.
    return """
        , (
            SELECT cv_num.value
            FROM item_custom_values cv_num
            JOIN type_fields tf_num ON tf_num.id=cv_num.field_id
            WHERE cv_num.item_id=i.id
              AND tf_num.type_id=i.item_type_id
              AND tf_num.active=1
              AND LOWER(TRIM(tf_num.label))='numero'
            ORDER BY tf_num.sort_order, tf_num.id
            LIMIT 1
          ) AS _sort_num
        , (
            SELECT cv_suffix.value
            FROM item_custom_values cv_suffix
            JOIN type_fields tf_suffix ON tf_suffix.id=cv_suffix.field_id
            WHERE cv_suffix.item_id=i.id
              AND tf_suffix.type_id=i.item_type_id
              AND tf_suffix.active=1
              AND LOWER(TRIM(tf_suffix.label))='suffisso numero'
            ORDER BY tf_suffix.sort_order, tf_suffix.id
            LIMIT 1
          ) AS _sort_suffix
    """


def inventory_order_sql():
    return """
        ORDER BY
          CASE
            WHEN TRIM(COALESCE(_sort_num,''))='' THEN 1
            ELSE 0
          END,
          CASE
            WHEN TRIM(COALESCE(_sort_num,''))='' THEN 0
            ELSE CAST(REPLACE(_sort_num, ',', '.') AS REAL)
          END,
          CASE
            WHEN TRIM(COALESCE(_sort_suffix,''))='' THEN 0
            WHEN LOWER(TRIM(_sort_suffix))='bis' THEN 1
            ELSE 2
          END,
          i.name COLLATE NOCASE,
          i.id
    """


def hydrate_inventory_items(conn, rows):
    items = [dict(r) for r in rows]
    for item in items:
        item.pop("_sort_num", None)
        item.pop("_sort_suffix", None)
        item["custom_values"] = item_custom_values(conn, item["id"])
        item["photos"] = [dict(r) for r in conn.execute(
            """SELECT id,filename,thumb_filename,COALESCE(label,'') AS label
               FROM item_photos
               WHERE item_id=?
               ORDER BY id""",
            (item["id"],),
        )]
        item["position_path"] = " → ".join(
            x for x in [
                item.get("environment"),
                item.get("furniture"),
                item.get("shelf"),
                item.get("container_name"),
            ] if x
        )
    return items


@app.get("/api/inventory-groups")
def api_inventory_groups():
    q = request.args.get("q", "").strip()
    grouping = request.args.get("group_by", "type").strip().lower()
    if grouping not in {"type", "environment", "none"}:
        grouping = "type"

    where_sql, params = inventory_search_where(q)

    with db() as conn:
        if grouping == "type":
            sql = """
                SELECT
                    COALESCE(CAST(i.item_type_id AS TEXT),'none') AS group_key,
                    COALESCE(t.name,'Senza tipologia') AS label,
                    COALESCE(t.icon,'📦') AS icon,
                    COUNT(*) AS item_count
                FROM items i
                LEFT JOIN item_types t ON t.id=i.item_type_id
            """ + where_sql + """
                GROUP BY i.item_type_id, t.name, t.icon
                ORDER BY label COLLATE NOCASE
            """
        elif grouping == "environment":
            sql = """
                SELECT
                    CASE WHEN TRIM(COALESCE(i.environment,''))='' THEN '__none__' ELSE TRIM(i.environment) END AS group_key,
                    CASE WHEN TRIM(COALESCE(i.environment,''))='' THEN 'Senza ambiente' ELSE TRIM(i.environment) END AS label,
                    '🏠' AS icon,
                    COUNT(*) AS item_count
                FROM items i
            """ + where_sql + """
                GROUP BY CASE WHEN TRIM(COALESCE(i.environment,''))='' THEN '__none__' ELSE TRIM(i.environment) END
                ORDER BY label COLLATE NOCASE
            """
        else:
            count = conn.execute("SELECT COUNT(*) FROM items i" + where_sql, params).fetchone()[0]
            groups = [{"group_key":"all","label":"Tutti gli elementi","icon":"📦","item_count":count}] if count else []
            return jsonify(groups=groups, matched_count=count, page_size=50)

        groups = [dict(r) for r in conn.execute(sql, params)]
        matched_count = sum(int(g["item_count"]) for g in groups)
        return jsonify(groups=groups, matched_count=matched_count, page_size=50)


@app.get("/api/inventory-subgroups")
def api_inventory_subgroups():
    q = request.args.get("q", "").strip()
    try:
        type_id = int(request.args.get("type_id", "0"))
    except (TypeError, ValueError):
        return jsonify(error="Tipologia non valida"), 400
    where_sql, params = inventory_search_where(q)
    with db() as conn:
        t = conn.execute(
            "SELECT subgroup_field_id FROM item_types WHERE id=?", (type_id,)
        ).fetchone()
        if not t or not t["subgroup_field_id"]:
            return jsonify(subgroups=[], enabled=False)
        fid = int(t["subgroup_field_id"])
        f = conn.execute(
            "SELECT label FROM type_fields WHERE id=? AND type_id=? AND active=1", (fid,type_id)
        ).fetchone()
        if not f:
            return jsonify(subgroups=[], enabled=False)
        where_sql = append_inventory_condition(where_sql, "i.item_type_id=?")
        all_params = [*params, type_id, fid]
        sql = """
            SELECT CASE WHEN TRIM(COALESCE(cv.value,''))='' THEN '__none__' ELSE TRIM(cv.value) END AS subgroup_key,
                   CASE WHEN TRIM(COALESCE(cv.value,''))='' THEN 'Senza valore' ELSE TRIM(cv.value) END AS label,
                   COUNT(*) AS item_count
            FROM items i
            LEFT JOIN item_custom_values cv ON cv.item_id=i.id AND cv.field_id=?
        """ + where_sql + """
            GROUP BY CASE WHEN TRIM(COALESCE(cv.value,''))='' THEN '__none__' ELSE TRIM(cv.value) END
            ORDER BY label COLLATE NOCASE
        """
        # JOIN placeholder precedes WHERE placeholders.
        query_params=[fid,*params,type_id]
        rows=[dict(r) for r in conn.execute(sql,query_params)]
        return jsonify(subgroups=rows, enabled=True, field_id=fid, field_label=f["label"],
                       matched_count=sum(int(x["item_count"]) for x in rows), page_size=50)


@app.get("/api/inventory-subgroup-items")
def api_inventory_subgroup_items():
    q=request.args.get("q","").strip()
    subgroup_key=request.args.get("subgroup_key","").strip()
    try:
        type_id=int(request.args.get("type_id","0")); offset=max(0,int(request.args.get("offset","0")))
    except (TypeError,ValueError):
        return jsonify(error="Parametri non validi"),400
    page_size=50
    where_sql,params=inventory_search_where(q)
    with db() as conn:
        t=conn.execute("SELECT subgroup_field_id FROM item_types WHERE id=?",(type_id,)).fetchone()
        if not t or not t["subgroup_field_id"]: return jsonify(error="Sottogruppo non configurato"),400
        fid=int(t["subgroup_field_id"])
        where_sql=append_inventory_condition(where_sql,"i.item_type_id=?")
        params=[*params,type_id]
        if subgroup_key=='__none__':
            where_sql=append_inventory_condition(where_sql,"TRIM(COALESCE(cv.value,''))=''")
            extra=[]
        else:
            where_sql=append_inventory_condition(where_sql,"TRIM(COALESCE(cv.value,''))=?")
            extra=[subgroup_key]
        base=" FROM items i LEFT JOIN item_custom_values cv ON cv.item_id=i.id AND cv.field_id=? "
        all_params=[fid,*params,*extra]
        total=conn.execute("SELECT COUNT(*)"+base+where_sql,all_params).fetchone()[0]
        sql=(
            """SELECT i.*, t.name AS type_name, t.icon AS type_icon
            """
            + inventory_sort_select_sql()
            + """
                 FROM items i
                 LEFT JOIN item_types t ON t.id=i.item_type_id
                 LEFT JOIN item_custom_values cv ON cv.item_id=i.id AND cv.field_id=?
              """
            + where_sql
            + inventory_order_sql()
            + " LIMIT ? OFFSET ?"
        )
        rows=conn.execute(sql,[*all_params,page_size,offset])
        items=hydrate_inventory_items(conn,rows); nxt=offset+len(items)
        return jsonify(items=items,total=total,offset=offset,next_offset=nxt,page_size=page_size,has_more=nxt<total)


@app.get("/api/inventory-items")
def api_inventory_items():
    q = request.args.get("q", "").strip()
    grouping = request.args.get("group_by", "type").strip().lower()
    group_key = request.args.get("group_key", "").strip()
    if grouping not in {"type", "environment", "none"}:
        grouping = "type"
    try:
        offset = max(0, int(request.args.get("offset", "0")))
    except (TypeError, ValueError):
        offset = 0
    # v2: dimensione pagina fissa per evitare liste enormi sul browser.
    page_size = 50

    where_sql, params = inventory_search_where(q)
    condition = ""
    extra = []
    if grouping == "type":
        if group_key == "none":
            condition = "i.item_type_id IS NULL"
        else:
            try:
                type_id = int(group_key)
            except (TypeError, ValueError):
                return jsonify(error="Gruppo tipologia non valido"), 400
            condition = "i.item_type_id=?"
            extra.append(type_id)
    elif grouping == "environment":
        if group_key == "__none__":
            condition = "TRIM(COALESCE(i.environment,''))=''"
        else:
            condition = "TRIM(COALESCE(i.environment,''))=?"
            extra.append(group_key)

    where_sql = append_inventory_condition(where_sql, condition)
    all_params = [*params, *extra]

    with db() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM items i" + where_sql,
            all_params,
        ).fetchone()[0]
        sql = (
            """
            SELECT i.*, t.name AS type_name, t.icon AS type_icon
            """
            + inventory_sort_select_sql()
            + """
            FROM items i
            LEFT JOIN item_types t ON t.id=i.item_type_id
            """
            + where_sql
            + inventory_order_sql()
            + " LIMIT ? OFFSET ?"
        )
        rows = conn.execute(sql, [*all_params, page_size, offset])
        items = hydrate_inventory_items(conn, rows)
        next_offset = offset + len(items)
        return jsonify(
            items=items,
            total=total,
            offset=offset,
            next_offset=next_offset,
            page_size=page_size,
            has_more=next_offset < total,
        )


@app.get("/api/items/<int:item_id>")
def api_get_item(item_id):
    with db() as conn:
        row = conn.execute(
            """SELECT i.*, t.name AS type_name, t.icon AS type_icon
               FROM items i LEFT JOIN item_types t ON t.id=i.item_type_id
               WHERE i.id=?""",
            (item_id,),
        ).fetchone()
        if not row:
            return jsonify(error="Elemento non trovato"), 404
        items = hydrate_inventory_items(conn, [row])
        return jsonify(items[0])


@app.get("/api/lookup-book")
def api_lookup_book():
    raw = request.args.get("code", "").strip()
    code = re.sub(r"[^0-9Xx]", "", raw).upper()

    if len(code) not in {10, 13}:
        return jsonify(error="Inserisci un ISBN di 10 o 13 caratteri."), 400
    if len(code) == 13 and not code.startswith(("978", "979")):
        return jsonify(error="Questo EAN non sembra un ISBN. Per ora la ricerca automatica gestisce ISBN 10/13."), 400

    def fetch_json(url):
        req = Request(url, headers={
            "User-Agent": "InventarioCasa/2.0.0 (Home Assistant local app)",
            "Accept": "application/json",
        })
        with urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # Fonte primaria: Google Books
    google_error = None
    try:
        data = fetch_json(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{code}&maxResults=5&printType=books")
        items = data.get("items") or []
        selected = None
        for item in items:
            info = item.get("volumeInfo") or {}
            ids = info.get("industryIdentifiers") or []
            values = {re.sub(r"[^0-9Xx]", "", str(x.get("identifier") or "")).upper() for x in ids if isinstance(x, dict)}
            if code in values:
                selected = item
                break
        if selected is None and items:
            selected = items[0]
        if selected:
            info = selected.get("volumeInfo") or {}
            publish_date = str(info.get("publishedDate") or "").strip()
            ym = re.search(r"(?:18|19|20)\d{2}", publish_date)
            year = ym.group(0) if ym else ""
            return jsonify(
                source="Google Books",
                code=code,
                title=str(info.get("title") or "").strip(),
                authors=[str(a).strip() for a in (info.get("authors") or []) if str(a).strip()],
                publisher=str(info.get("publisher") or "").strip(),
                publish_date=publish_date,
                year=year,
            )
    except HTTPError as exc:
        google_error = f"HTTP {exc.code}"
    except (URLError, TimeoutError, ValueError) as exc:
        google_error = str(exc) or "errore di connessione"

    # Fallback: Open Library
    try:
        book = fetch_json(f"https://openlibrary.org/isbn/{code}.json")
    except HTTPError as exc:
        if exc.code == 404:
            msg = "Codice non trovato né su Google Books né su Open Library."
            if google_error:
                msg += f" Google Books non era disponibile ({google_error})."
            return jsonify(error=msg), 404
        return jsonify(error=f"Open Library ha risposto con errore HTTP {exc.code}."), 502
    except (URLError, TimeoutError, ValueError):
        if google_error:
            return jsonify(error="Impossibile contattare sia Google Books sia Open Library. Controlla la connessione Internet e riprova."), 502
        return jsonify(error="Impossibile contattare Open Library. Controlla la connessione Internet e riprova."), 502

    authors = []
    for ref in (book.get("authors") or [])[:5]:
        key = ref.get("key") if isinstance(ref, dict) else None
        if not key:
            continue
        try:
            a = fetch_json(f"https://openlibrary.org{key}.json")
            if a.get("name"):
                authors.append(a["name"])
        except Exception:
            pass

    publishers = book.get("publishers") or []
    publish_date = str(book.get("publish_date") or "").strip()
    ym = re.search(r"(?:18|19|20)\d{2}", publish_date)
    year = ym.group(0) if ym else ""

    return jsonify(
        source="Open Library",
        code=code,
        title=str(book.get("title") or "").strip(),
        authors=authors,
        publisher=str(publishers[0] if publishers else "").strip(),
        publish_date=publish_date,
        year=year,
    )



@app.post("/api/decode-barcode")
def api_decode_barcode():
    """Decodifica un barcode da una singola immagine inviata su richiesta.
    Usato come fallback quando BarcodeDetector non è disponibile nel browser.
    """
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return jsonify(error="Immagine mancante."), 400

    try:
        image = Image.open(upload.stream)
        image = ImageOps.exif_transpose(image).convert("RGB")
        # Limita il carico durante la scansione live senza penalizzare le foto.
        if max(image.size) > 1800:
            image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)

        found = []
        for result in zbar_decode(image):
            try:
                raw = result.data.decode("utf-8", errors="ignore")
            except Exception:
                raw = str(result.data or "")
            code = re.sub(r"[^0-9Xx]", "", raw).upper()
            if len(code) in {8, 10, 12, 13}:
                found.append({
                    "raw": raw,
                    "code": code,
                    "format": str(getattr(result, "type", "") or ""),
                })

        if not found:
            return jsonify(found=False, barcodes=[])
        return jsonify(found=True, barcodes=found)
    except Exception as exc:
        app.logger.warning("Errore decodifica barcode: %s", exc)
        return jsonify(error="Non sono riuscito a leggere il codice da questa immagine."), 422

def normalize_field_type(value):
    allowed = {"text", "number", "date", "textarea", "select", "checkbox"}
    return value if value in allowed else "text"


@app.post("/api/types")
def api_create_type():
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    icon = (data.get("icon") or "📦").strip() or "📦"
    if not name:
        return jsonify(error="Il nome della tipologia è obbligatorio"), 400
    try:
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO item_types(name,icon,created_at) VALUES(?,?,?)",
                (name, icon, datetime.now().isoformat(timespec="seconds")),
            )
            type_id = cur.lastrowid
            for order, field in enumerate(data.get("fields") or []):
                label = (field.get("label") or "").strip()
                if not label:
                    continue
                conn.execute(
                    """INSERT INTO type_fields(type_id,label,field_type,required,options,sort_order,active,placeholder)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        type_id,
                        label,
                        normalize_field_type(field.get("field_type")),
                        1 if field.get("required") else 0,
                        (field.get("options") or "").strip(),
                        order,
                        1 if field.get("active", True) else 0,
                        (field.get("placeholder") or "").strip(),
                    ),
                )
            return jsonify(id=type_id), 201
    except sqlite3.IntegrityError:
        return jsonify(error="Esiste già una tipologia con questo nome"), 409


@app.put("/api/types/<int:type_id>")
def api_update_type(type_id):
    data = request.get_json(force=True)
    name = (data.get("name") or "").strip()
    icon = (data.get("icon") or "📦").strip() or "📦"
    if not name:
        return jsonify(error="Il nome della tipologia è obbligatorio"), 400

    try:
        with db() as conn:
            if not conn.execute("SELECT id FROM item_types WHERE id=?", (type_id,)).fetchone():
                return jsonify(error="Tipologia non trovata"), 404

            conn.execute(
                "UPDATE item_types SET name=?,icon=? WHERE id=?",
                (name, icon, type_id),
            )

            existing = {
                r["id"] for r in conn.execute(
                    "SELECT id FROM type_fields WHERE type_id=?", (type_id,)
                )
            }
            incoming = set()

            for order, field in enumerate(data.get("fields") or []):
                label = (field.get("label") or "").strip()
                if not label:
                    continue
                fid = field.get("id")
                values = (
                    label,
                    normalize_field_type(field.get("field_type")),
                    1 if field.get("required") else 0,
                    (field.get("options") or "").strip(),
                    order,
                    1 if field.get("active", True) else 0,
                    (field.get("placeholder") or "").strip(),
                )
                if fid:
                    fid = int(fid)
                    incoming.add(fid)
                    conn.execute(
                        """UPDATE type_fields
                           SET label=?,field_type=?,required=?,options=?,sort_order=?,active=?,placeholder=?
                           WHERE id=? AND type_id=?""",
                        values + (fid, type_id),
                    )
                else:
                    cur = conn.execute(
                        """INSERT INTO type_fields(type_id,label,field_type,required,options,sort_order,active,placeholder)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (type_id,) + values,
                    )
                    incoming.add(cur.lastrowid)

            # Mai cancellare un campo automaticamente: se sparisce dal form lo disattiviamo.
            for fid in existing - incoming:
                conn.execute(
                    "UPDATE type_fields SET active=0 WHERE id=? AND type_id=?",
                    (fid, type_id),
                )

            subgroup_field_id = data.get("subgroup_field_id")
            if subgroup_field_id in (None, "", 0, "0"):
                subgroup_field_id = None
            else:
                try:
                    subgroup_field_id = int(subgroup_field_id)
                except (TypeError, ValueError):
                    subgroup_field_id = None
                if subgroup_field_id and not conn.execute(
                    "SELECT 1 FROM type_fields WHERE id=? AND type_id=? AND active=1",
                    (subgroup_field_id, type_id),
                ).fetchone():
                    subgroup_field_id = None
            conn.execute("UPDATE item_types SET subgroup_field_id=? WHERE id=?", (subgroup_field_id, type_id))

            return jsonify(ok=True)
    except sqlite3.IntegrityError:
        return jsonify(error="Esiste già una tipologia con questo nome"), 409


def item_payload(data):
    return (
        (data.get("name") or "").strip(),
        (data.get("description") or "").strip(),
        max(1, int(data.get("quantity") or 1)),
        data.get("item_type_id") or None,
        (data.get("environment") or "").strip(),
        (data.get("furniture") or "").strip(),
        (data.get("shelf") or "").strip(),
        (data.get("container_name") or "").strip(),
        (data.get("container_code") or "").strip(),
        (data.get("tags") or "").strip(),
        (data.get("notes") or "").strip(),
    )


def save_custom_values(conn, item_id, type_id, values):
    values = values or {}
    if not type_id:
        return

    fields = {
        str(r["id"]): dict(r)
        for r in conn.execute(
            "SELECT id,required,active FROM type_fields WHERE type_id=?",
            (type_id,),
        )
    }

    for fid, meta in fields.items():
        if not meta["active"]:
            continue
        value = values.get(fid, "")
        if isinstance(value, bool):
            value = "1" if value else ""
        value = str(value).strip()

        if meta["required"] and not value:
            raise ValueError("Manca un campo obbligatorio")

        conn.execute(
            "DELETE FROM item_custom_values WHERE item_id=? AND field_id=?",
            (item_id, int(fid)),
        )
        if value:
            conn.execute(
                "INSERT INTO item_custom_values(item_id,field_id,value) VALUES(?,?,?)",
                (item_id, int(fid), value),
            )


@app.delete("/api/types/<int:type_id>")
def api_delete_type(type_id):
    with db() as conn:
        row = conn.execute(
            "SELECT name FROM item_types WHERE id=?",
            (type_id,),
        ).fetchone()
        if not row:
            return jsonify(error="Tipologia non trovata"), 404

        used = conn.execute(
            "SELECT COUNT(*) FROM items WHERE item_type_id=?",
            (type_id,),
        ).fetchone()[0]
        if used:
            return jsonify(
                error=f"Impossibile eliminare la tipologia: è usata da {used} elemento/i. Cambia prima la tipologia di questi elementi."
            ), 409

        conn.execute("DELETE FROM item_types WHERE id=?", (type_id,))
        return jsonify(ok=True)


@app.post("/api/items")
def api_create_item():
    data = request.get_json(force=True)
    values = item_payload(data)
    if not values[0]:
        return jsonify(error="Il nome dell'elemento è obbligatorio"), 400

    now = datetime.now().isoformat(timespec="seconds")
    try:
        with db() as conn:
            cur = conn.execute(
                """INSERT INTO items(
                    name,description,quantity,item_type_id,environment,furniture,shelf,
                    container_name,container_code,tags,notes,created_at,updated_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                values + (now, now),
            )
            save_custom_values(
                conn, cur.lastrowid, values[3], data.get("custom_values")
            )
            return jsonify(id=cur.lastrowid), 201
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@app.put("/api/items/<int:item_id>")
def api_update_item(item_id):
    data = request.get_json(force=True)
    values = item_payload(data)
    if not values[0]:
        return jsonify(error="Il nome dell'elemento è obbligatorio"), 400

    try:
        with db() as conn:
            if not conn.execute("SELECT id FROM items WHERE id=?", (item_id,)).fetchone():
                return jsonify(error="Elemento non trovato"), 404
            conn.execute(
                """UPDATE items SET
                    name=?,description=?,quantity=?,item_type_id=?,environment=?,furniture=?,
                    shelf=?,container_name=?,container_code=?,tags=?,notes=?,updated_at=?
                   WHERE id=?""",
                values + (datetime.now().isoformat(timespec="seconds"), item_id),
            )
            save_custom_values(
                conn, item_id, values[3], data.get("custom_values")
            )
            return jsonify(ok=True)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@app.delete("/api/items/<int:item_id>")
def api_delete_item(item_id):
    with db() as conn:
        photos = list(conn.execute(
            "SELECT filename,thumb_filename FROM item_photos WHERE item_id=?",
            (item_id,),
        ))
        for photo in photos:
            for filename in (photo["filename"], photo["thumb_filename"]):
                try:
                    (MEDIA_DIR / filename).unlink(missing_ok=True)
                except Exception:
                    pass
        conn.execute("DELETE FROM items WHERE id=?", (item_id,))
    return jsonify(ok=True)


@app.post("/api/items/<int:item_id>/photos")
def api_upload_photo(item_id):
    if "file" not in request.files:
        return jsonify(error="Nessun file selezionato"), 400

    with db() as conn:
        item = conn.execute(
            """SELECT i.id,t.name AS type_name
               FROM items i LEFT JOIN item_types t ON t.id=i.item_type_id
               WHERE i.id=?""",
            (item_id,),
        ).fetchone()
        if not item:
            return jsonify(error="Elemento non trovato"), 404

    profile = request.form.get("profile", "auto")
    if profile == "auto":
        profile = "collectible" if (item["type_name"] or "").lower() == "fumetto" else "standard"

    max_px, quality = (2400, 90) if profile == "collectible" else (1600, 84)

    upload = request.files["file"]
    uid = uuid.uuid4().hex
    full_name = f"{item_id}_{uid}.webp"
    thumb_name = f"{item_id}_{uid}_thumb.webp"

    try:
        image = Image.open(upload.stream)
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((max_px, max_px))
        image.save(MEDIA_DIR / full_name, "WEBP", quality=quality, method=6)

        thumb = image.copy()
        thumb.thumbnail((360, 360))
        thumb.save(MEDIA_DIR / thumb_name, "WEBP", quality=80, method=6)

        with db() as conn:
            cur = conn.execute(
                """INSERT INTO item_photos(item_id,filename,thumb_filename,label,created_at)
                   VALUES(?,?,?,?,?)""",
                (
                    item_id,
                    full_name,
                    thumb_name,
                    (request.form.get("label") or "").strip(),
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            return jsonify(id=cur.lastrowid), 201
    except Exception as exc:
        for filename in (full_name, thumb_name):
            try:
                (MEDIA_DIR / filename).unlink(missing_ok=True)
            except Exception:
                pass
        return jsonify(error=f"Immagine non valida: {exc}"), 400


@app.delete("/api/photos/<int:photo_id>")
def api_delete_photo(photo_id):
    with db() as conn:
        photo = conn.execute(
            "SELECT filename,thumb_filename FROM item_photos WHERE id=?",
            (photo_id,),
        ).fetchone()
        if not photo:
            return jsonify(error="Foto non trovata"), 404

        for filename in (photo["filename"], photo["thumb_filename"]):
            try:
                (MEDIA_DIR / filename).unlink(missing_ok=True)
            except Exception:
                pass

        conn.execute("DELETE FROM item_photos WHERE id=?", (photo_id,))
    return jsonify(ok=True)



@app.get("/api/backups")
def api_backups():
    return jsonify(
        backups=list_database_backups(),
        startup_error=STARTUP_DB_ERROR,
        current_database=inspect_database_file(DB_PATH),
    )


@app.post("/api/backups/create")
def api_create_backup():
    try:
        with DB_MAINTENANCE_LOCK:
            path = create_database_backup("inventario_manuale")

        return jsonify(
            ok=True,
            filename=path.name,
            database=inspect_database_file(path),
        ), 201

    except Exception as exc:
        return jsonify(error=str(exc)), 500


@app.post("/api/backups/restore")
def api_restore_backup():
    data = request.get_json(silent=True) or {}
    filename = data.get("filename")

    try:
        with DB_MAINTENANCE_LOCK:
            result = restore_database_backup(filename)

        return jsonify(ok=True, **result)

    except FileNotFoundError as exc:
        return jsonify(error=str(exc)), 404

    except ValueError as exc:
        return jsonify(error=str(exc)), 400

    except Exception as exc:
        return jsonify(
            error=str(exc),
            startup_error=STARTUP_DB_ERROR,
        ), 500


@app.get("/api/backups/download/<path:filename>")
def api_download_backup(filename):
    try:
        path = backup_path_from_name(filename)
    except (ValueError, FileNotFoundError):
        return jsonify(error="Backup non trovato"), 404

    return send_from_directory(
        DB_BACKUP_DIR,
        path.name,
        as_attachment=True,
    )


@app.get("/files/<path:filename>")
def media_file(filename):
    return send_from_directory(MEDIA_DIR, filename)


RECOVERY_PAGE = r"""
<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Inventario Casa - Recovery</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{
  margin:0;
  min-height:100vh;
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
  color:#f7f9fb;
  background:
    radial-gradient(circle at 10% 5%,#185b78 0%,transparent 38%),
    radial-gradient(circle at 90% 10%,#8e3348 0%,transparent 40%),
    linear-gradient(145deg,#123f58,#24204c 48%,#8e3348);
  padding:18px;
}
.wrap{max-width:720px;margin:auto}
.card{
  margin-bottom:14px;
  padding:16px;
  border-radius:16px;
  border:1.5px solid rgba(255,255,255,.42);
  background:rgba(255,255,255,.12);
  backdrop-filter:blur(12px);
}
h1,h2{margin-top:0}
.error{
  white-space:pre-wrap;
  word-break:break-word;
  padding:12px;
  border-radius:10px;
  border:1px solid #ff7b7b;
  background:rgba(120,20,30,.22);
}
.backup{
  padding:12px;
  border:1px solid rgba(255,255,255,.32);
  border-radius:12px;
  margin:8px 0;
  background:rgba(0,0,0,.15);
}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px}
button,a.btn{
  border-radius:10px;
  border:1px solid rgba(255,255,255,.38);
  padding:9px 12px;
  font:inherit;
  font-weight:700;
  cursor:pointer;
  text-decoration:none;
  background:#55aef7;
  color:#07111c;
}
.secondary{background:rgba(255,255,255,.12)!important;color:#fff!important}
.ok{color:#72e49d}.bad{color:#ff9b9b}.muted{color:#c7ced7}
/* v2.3.0 - Backup & Recovery */
.backup-panel-head{
  display:flex;
  justify-content:space-between;
  align-items:center;
  gap:8px;
}
.backup-panel-head h2{margin:0!important}
.backup-list{display:grid;gap:9px;margin-top:12px}
.backup-row{
  padding:11px;
  border:1.5px solid rgba(255,255,255,.38);
  border-radius:12px;
  background:rgba(0,0,0,.14);
}
.backup-row-name{
  font-weight:800;
  overflow-wrap:anywhere;
}
.backup-row-meta{
  margin-top:3px;
  font-size:.78rem;
  color:var(--inv-muted,var(--muted));
}
.backup-row-status{
  margin-top:5px;
  font-size:.82rem;
}
.backup-row-status.ok{color:#72e49d}
.backup-row-status.bad{color:#ff9b9b}
.backup-row-actions{
  display:flex;
  gap:7px;
  flex-wrap:wrap;
  margin-top:9px;
}
.backup-row-actions button,
.backup-row-actions a{
  flex:1;
  min-width:110px;
}
.backup-info{
  margin:10px 0;
  padding:10px;
  border:1.5px solid rgba(79,176,255,.40);
  border-radius:11px;
  background:rgba(79,176,255,.07);
}
@media(max-width:640px){
  .backup-row-actions{
    display:grid;
    grid-template-columns:1fr 1fr;
  }
}


</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1 id="recoveryTitle">🛟 Inventario Casa - Recovery</h1>
    <p id="recoveryDescription">
      Inventario Casa non è riuscito ad aprire o aggiornare correttamente
      il database. I backup restano disponibili.
    </p>
    <div class="error">{{ startup_error }}</div>
  </div>

  <div class="card">
    <h2 id="recoveryBackupsTitle">Backup disponibili</h2>
    <div id="backups">Caricamento…</div>
  </div>
</div>

<script>
const $=id=>document.getElementById(id);

const RECOVERY_I18N={
  it:{
    title:'🛟 Inventario Casa - Recovery',
    description:'Inventario Casa non è riuscito ad aprire o aggiornare correttamente il database. I backup restano disponibili.',
    available_backups:'Backup disponibili',
    loading:'Caricamento…',
    valid_backup:'✓ Backup integro',
    items:'elementi',
    types:'tipologie',
    photos:'foto',
    download:'Scarica',
    restore:'Ripristina',
    no_backups:'Nessun backup disponibile.',
    error:'Errore',
    restore_confirm:'Ripristinare questo backup?\n\n{name}\n\nIl database corrente verrà sostituito.',
    restore_keyword:'Per confermare il ripristino scrivi:\n\nRIPRISTINA',
    restore_failed:'Ripristino non riuscito',
    restore_ok:'Backup ripristinato correttamente.',
    integrity:'Integrity check'
  },
  en:{
    title:'🛟 Home Inventory - Recovery',
    description:'Home Inventory could not open or update the database correctly. Backups remain available.',
    available_backups:'Available backups',
    loading:'Loading…',
    valid_backup:'✓ Valid backup',
    items:'items',
    types:'types',
    photos:'photos',
    download:'Download',
    restore:'Restore',
    no_backups:'No backups available.',
    error:'Error',
    restore_confirm:'Restore this backup?\n\n{name}\n\nThe current database will be replaced.',
    restore_keyword:'To confirm the restore, type:\n\nRIPRISTINA',
    restore_failed:'Restore failed',
    restore_ok:'Backup restored successfully.',
    integrity:'Integrity check'
  }
};

function recoveryLanguage(){
  try{
    if(window.parent && window.parent!==window){
      const lang=(
        window.parent.document.documentElement.lang||''
      ).toLowerCase();

      if(lang.startsWith('en')) return 'en';
      if(lang.startsWith('it')) return 'it';
    }
  }catch(e){}

  const lang=(navigator.language||'it').toLowerCase();
  return lang.startsWith('en')?'en':'it';
}

const recoveryLang=recoveryLanguage();

function rt(key){
  return RECOVERY_I18N[recoveryLang]?.[key]
      ?? RECOVERY_I18N.it[key]
      ?? key;
}

function rtf(key,vars={}){
  return rt(key).replace(/\{(\w+)\}/g,(_,name)=>
    Object.prototype.hasOwnProperty.call(vars,name)
      ? vars[name]
      : `{${name}}`
  );
}

document.documentElement.lang=recoveryLang;
$('recoveryTitle').textContent=rt('title');
$('recoveryDescription').textContent=rt('description');
$('recoveryBackupsTitle').textContent=rt('available_backups');
$('backups').textContent=rt('loading');

const esc=s=>String(s??'')
 .replaceAll('&','&amp;')
 .replaceAll('<','&lt;')
 .replaceAll('>','&gt;')
 .replaceAll('"','&quot;');

function bytes(n){
  n=Number(n||0);
  if(n<1024)return n+' B';
  if(n<1024*1024)return (n/1024).toFixed(1)+' KB';
  return (n/1024/1024).toFixed(1)+' MB';
}

async function loadBackups(){
  try{
    const r=await fetch('api/backups');
    const d=await r.json();
    const rows=d.backups||[];

    $('backups').innerHTML=rows.length
      ? rows.map(b=>`
        <div class="backup">
          <strong>${esc(b.filename)}</strong><br>
          <span class="muted">${esc(b.modified)} · ${bytes(b.size)}</span><br>
          <span class="${b.valid?'ok':'bad'}">
            ${b.valid?rt('valid_backup'):'⚠ '+esc(b.integrity)}
          </span>
          ${b.items!==null
            ? `<div class="muted">${b.items} ${rt('items')} · ${b.types??'?'} ${rt('types')} · ${b.photos??'?'} ${rt('photos')}</div>`
            : ''}
          <div class="actions">
            <a class="btn secondary"
               href="api/backups/download/${encodeURIComponent(b.filename)}">
               ${rt('download')}
            </a>
            ${b.valid?`
              <button onclick="restoreBackup('${esc(b.filename)}')">
                ${rt('restore')}
              </button>`:''}
          </div>
        </div>
      `).join('')
      : `<div class="muted">${rt('no_backups')}</div>`;

  }catch(e){
    $('backups').textContent=rt('error')+': '+e.message;
  }
}

async function restoreBackup(name){
  if(!confirm(rtf('restore_confirm',{name})))return;

  const confirmText=prompt(rt('restore_keyword'));

  if(confirmText!=='RIPRISTINA')return;

  const r=await fetch('api/backups/restore',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({filename:name})
  });

  const d=await r.json().catch(()=>({}));

  if(!r.ok){
    alert(d.error||rt('restore_failed'));
    await loadBackups();
    return;
  }

  alert(
    rt('restore_ok')+'\n\n'+
    rt('items')+': '+(d.database?.items??'?')+'\n'+
    rt('integrity')+': '+(d.database?.integrity??'?')
  );

  location.reload();
}

loadBackups();
</script>
</body>
</html>
"""





FRONTEND_ASSETS = (
    "css/app.css",
    "js/translations.js",
    "js/app.js",
)

def frontend_asset_version():
    digest = hashlib.sha256()
    static_dir = Path(app.static_folder)

    for filename in FRONTEND_ASSETS:
        digest.update((static_dir / filename).read_bytes())

    return digest.hexdigest()[:12]

FRONTEND_ASSET_VERSION = frontend_asset_version()


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
        return render_template_string(
            RECOVERY_PAGE,
            startup_error=STARTUP_DB_ERROR,
        )
    return render_template("index.html", asset_version=FRONTEND_ASSET_VERSION)

