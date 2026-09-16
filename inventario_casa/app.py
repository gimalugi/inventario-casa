from flask import Flask, request, jsonify, render_template_string, send_from_directory
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
    <h1>🛟 Inventario Casa - Recovery</h1>
    <p>
      Inventario Casa non è riuscito ad aprire o aggiornare correttamente
      il database. I backup restano disponibili.
    </p>
    <div class="error">{{ startup_error }}</div>
  </div>

  <div class="card">
    <h2>Backup disponibili</h2>
    <div id="backups">Caricamento…</div>
  </div>
</div>

<script>
const $=id=>document.getElementById(id);
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
            ${b.valid?'✓ Backup integro':'⚠ '+esc(b.integrity)}
          </span>
          ${b.items!==null?`<div class="muted">${b.items} elementi · ${b.types??'?'} tipologie · ${b.photos??'?'} foto</div>`:''}
          <div class="actions">
            <a class="btn secondary"
               href="api/backups/download/${encodeURIComponent(b.filename)}">
               Scarica
            </a>
            ${b.valid?`
              <button onclick="restoreBackup('${esc(b.filename)}')">
                Ripristina
              </button>`:''}
          </div>
        </div>
      `).join('')
      : '<div class="muted">Nessun backup disponibile.</div>';

  }catch(e){
    $('backups').textContent='Errore: '+e.message;
  }
}

async function restoreBackup(name){
  if(!confirm(
    'Ripristinare questo backup?\\n\\n'+name+
    '\\n\\nIl database corrente verrà sostituito.'
  ))return;

  const confirmText=prompt(
    'Per confermare il ripristino scrivi:\\n\\nRIPRISTINA'
  );

  if(confirmText!=='RIPRISTINA')return;

  const r=await fetch('api/backups/restore',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({filename:name})
  });

  const d=await r.json().catch(()=>({}));

  if(!r.ok){
    alert(d.error||'Ripristino non riuscito');
    await loadBackups();
    return;
  }

  alert(
    'Backup ripristinato correttamente.\\n\\n'+
    'Elementi: '+(d.database?.items??'?')+'\\n'+
    'Integrity check: '+(d.database?.integrity??'?')
  );

  location.reload();
}

loadBackups();
</script>
</body>
</html>
"""


PAGE = r"""
<!doctype html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Inventario Casa</title>
<style>
:root{
  color-scheme:dark;
  --bg:#111419;--panel:#1a1f27;--panel2:#222936;--text:#eef2f7;
  --muted:#9aa6b4;--border:#313a47;--accent:#72b3f5;--danger:#ff7b7b;
}
*{box-sizing:border-box}
body{
  margin:0;
  font-family:
    var(--ha-font-family-body,
    var(--paper-font-common-base_-_font-family,
    -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif));
  font-weight:400;
  -webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;
  text-rendering:optimizeLegibility;
  background:var(--bg);
  color:var(--text);
}
.wrap{max-width:1180px;margin:auto;padding:16px}
header{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap;margin-bottom:14px}
h1{margin:0;font-size:1.5rem}.sub,.meta,.hint{color:var(--muted)}
.search{display:flex;gap:7px;flex:1;min-width:260px;max-width:540px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;margin-bottom:14px}
.stat,.panel{background:var(--panel);border:1px solid var(--border);border-radius:14px;padding:13px}
.stat b{display:block;font-size:1.25rem}
.layout{display:grid;grid-template-columns:1fr 320px;gap:14px}
.panel{margin-bottom:14px}.panel h2{font-size:1rem;margin:0 0 11px}
input,select,textarea,button{font:inherit}
input,select,textarea{width:100%;background:#0f1318;color:var(--text);border:1px solid var(--border);border-radius:10px;padding:9px}
textarea{min-height:76px;resize:vertical}
button{border:0;border-radius:10px;padding:9px 12px;background:var(--accent);font-weight:750;cursor:pointer;color:#07111c}
button.secondary{background:var(--panel2);color:var(--text);border:1px solid var(--border)}
button.danger{background:#4d2528;color:#ffdada;border:1px solid #724046}
button.small{padding:6px 8px;font-size:.8rem}
.form{display:grid;grid-template-columns:1fr 1fr;gap:9px}.full{grid-column:1/-1}
.tabs{display:flex;gap:6px;overflow-x:auto;margin-bottom:12px;padding-bottom:2px}
.tabbtn{background:var(--panel2);color:var(--text);border:1px solid var(--border);white-space:nowrap}
.tabbtn.active{background:var(--accent);color:#07111c}
.tab{display:none}.tab.active{display:block}
.customgrid{display:grid;grid-template-columns:1fr 1fr;gap:9px}.customgrid .wide{grid-column:1/-1}
.item{background:var(--panel2);border:1px solid var(--border);border-radius:11px;padding:9px 12px;margin-bottom:6px}
.item-row{width:100%;min-height:44px;display:flex;align-items:center;justify-content:space-between;gap:10px;text-align:left;cursor:pointer;color:var(--text);font:inherit}
.item-row:hover{border-color:#5e7088}
.item-row:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.itemname{font-weight:800;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.item-chevron{flex:0 0 auto;font-size:1.55rem;line-height:1;color:var(--muted)}
.items-head-controls{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.items-group-wrap,.items-limit-wrap{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:.82rem}
.items-group-wrap select,.items-limit-wrap select{min-width:0}
.item-group{margin-top:8px}
.item-group:first-child{margin-top:0}
.item-group-head{width:100%;display:flex;align-items:center;justify-content:space-between;gap:10px;background:transparent;border:0;border-bottom:1px solid var(--border);padding:8px 2px;color:var(--text);font:inherit;cursor:pointer}
.item-group-title{display:flex;align-items:center;gap:8px;min-width:0;font-weight:800}
.item-group-count{font-size:.8rem;color:var(--muted);white-space:nowrap}
.item-group-arrow{font-size:1.15rem;color:var(--muted)}
.item-group-body{padding-top:6px}
.item-group.collapsed .item-group-body{display:none}
.item-group.collapsed .item-group-arrow{transform:rotate(-90deg)}
.tags{margin-top:6px}.tag{display:inline-block;border:1px solid var(--border);border-radius:999px;padding:2px 7px;margin:2px 3px 0 0;font-size:.79rem}
.typecard{border:1px solid var(--border);background:var(--panel2);border-radius:10px;padding:8px 9px;margin-bottom:6px;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:7px;cursor:pointer}
.typecard:hover{border-color:#506075}
.typecard-main{display:flex;align-items:center;gap:8px;min-width:0}
.typeicon{width:26px;text-align:center;font-size:1.05rem;flex:0 0 26px}
.typename{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:750}
.typecount{font-size:.76rem;color:var(--muted);white-space:nowrap}
.type-tools{display:flex;gap:6px;margin-bottom:8px}
.type-tools input{min-width:0}
.type-panel-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px}
.type-panel-head h2{margin:0}
.type-panel-head button{min-width:38px;padding:6px 8px}
.type-panel.collapsed .type-panel-body{display:none}
.type-add{width:100%;margin-top:4px}
.dialog-danger{margin-right:auto}
.dialogbg{display:none;position:fixed;inset:0;background:#000a;align-items:center;justify-content:center;padding:14px;z-index:30}.dialogbg.show{display:flex}
.dialog{width:min(820px,100%);max-height:93vh;overflow:auto;background:var(--panel);border:1px solid var(--border);border-radius:16px;padding:15px}
.fieldrow{display:grid;grid-template-columns:1.2fr .85fr auto auto auto auto;gap:6px;align-items:center;margin-bottom:7px}
.fieldrow.inactive{opacity:.5}.fieldrow .options{grid-column:1/-1}
.check{display:flex;align-items:center;gap:5px;font-size:.8rem;color:var(--muted)}.check input{width:auto}
.photo-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px}
.photo{background:var(--panel2);border:1px solid var(--border);border-radius:10px;padding:6px}
.photo img{width:100%;aspect-ratio:1;object-fit:cover;border-radius:7px;cursor:pointer}
.photo-lightbox{
  position:fixed;inset:0;z-index:99999;
  display:none;align-items:center;justify-content:center;
  padding:18px;background:rgba(0,0,0,.88)
}
.photo-lightbox.open{display:flex}
.photo-lightbox img{
  max-width:96vw;max-height:92vh;object-fit:contain;
  border-radius:12px;background:#111
}
.photo-lightbox-close{
  position:absolute;top:max(12px,env(safe-area-inset-top));right:14px;
  width:46px;height:46px;border-radius:50%;
  border:1px solid rgba(255,255,255,.35);
  background:rgba(20,20,24,.9);color:#fff;
  font-size:28px;line-height:1;cursor:pointer
}

.empty{padding:22px;text-align:center;color:var(--muted)}
.savebar{display:flex;gap:8px;justify-content:flex-end;margin-top:12px}
.notice{background:var(--panel2);border:1px dashed var(--border);border-radius:10px;padding:12px;color:var(--muted)}
/* Responsive: tablet */
@media(max-width:900px){
  .layout{grid-template-columns:1fr}
  main,aside,.panel,.item,.typecard{min-width:0}
  .wrap{padding:12px}
}

/* Responsive: smartphone */
@media(max-width:640px){
  body{font-size:15px;overflow-x:hidden}
  .wrap{width:100%;max-width:none;padding:8px}

  header{
    display:block;
    margin-bottom:10px;
  }
  header>div:first-child{margin-bottom:10px}
  h1{font-size:1.28rem}
  .sub{font-size:.84rem}

  .search{
    display:grid;
    grid-template-columns:minmax(0,1fr) 48px;
    width:100%;
    max-width:none;
    min-width:0;
    gap:6px;
  }

  .stats{
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:6px;
    margin-bottom:10px;
  }
  .stat{
    padding:9px 6px;
    text-align:center;
    min-width:0;
  }
  .stat b{font-size:1.05rem}
  .stat .sub{font-size:.72rem}

  .layout{display:block}
  .panel{
    padding:10px;
    border-radius:12px;
    margin-bottom:10px;
    overflow:hidden;
  }

  input,select,textarea{
    min-width:0;
    max-width:100%;
    font-size:16px;
    padding:11px 10px;
  }
  textarea{min-height:92px}

  button{
    min-height:44px;
    padding:10px 12px;
    touch-action:manipulation;
  }
  button.small{
    min-height:40px;
    min-width:40px;
    padding:8px 9px;
    font-size:.82rem;
  }

  .form,.customgrid{
    grid-template-columns:minmax(0,1fr);
    gap:9px;
  }
  .full,.customgrid .wide{grid-column:auto}

  .tabs{
    width:calc(100% + 20px);
    margin-left:-10px;
    padding:0 10px 7px;
    gap:6px;
    overflow-x:auto;
    overscroll-behavior-inline:contain;
    scroll-snap-type:x proximity;
    scrollbar-width:none;
    -webkit-overflow-scrolling:touch;
  }
  .tabs::-webkit-scrollbar{display:none}
  .tabbtn{
    flex:0 0 auto;
    min-height:42px;
    padding:8px 12px;
    scroll-snap-align:start;
  }

  .item{
    padding:10px;
    border-radius:11px;
  }
  .itemtop{
    display:grid;
    grid-template-columns:minmax(0,1fr);
    gap:9px;
  }
  .itemname{
    font-size:1rem;
    overflow-wrap:anywhere;
  }
  .meta{overflow-wrap:anywhere}
  .itemactions{
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    width:100%;
    gap:6px;
  }
  .itemactions button{
    width:100%;
    min-width:0;
  }

  .typecard{
    grid-template-columns:minmax(0,1fr) auto;
    padding:9px;
  }
  .type-tools{display:grid;grid-template-columns:minmax(0,1fr)}
  .type-panel-head button{min-height:40px}
  aside .panel{margin-bottom:8px}

  .dialogbg{
    padding:0;
    align-items:stretch;
  }
  .dialog{
    width:100%;
    max-width:none;
    height:100dvh;
    max-height:100dvh;
    border-radius:0;
    border-left:0;
    border-right:0;
    padding:10px;
    padding-bottom:84px;
    overflow-x:hidden;
  }
  .dialog h2{
    position:sticky;
    top:-10px;
    z-index:4;
    margin:0 -10px 10px;
    padding:12px 10px;
    background:var(--panel);
    border-bottom:1px solid var(--border);
  }

  .fieldrow{
    display:grid;
    grid-template-columns:minmax(0,1fr) minmax(0,1fr);
    gap:7px;
    padding:9px;
    margin-bottom:9px;
    background:var(--panel2);
    border:1px solid var(--border);
    border-radius:10px;
  }
  .fieldrow .flabel,
  .fieldrow .ftype,
  .fieldrow .options{
    grid-column:1/-1;
  }
  .fieldrow .check{
    grid-column:1/-1;
    min-height:36px;
  }
  .fieldrow button{
    width:100%;
  }
  .fieldrow .options{min-width:0}

  .savebar{
    position:sticky;
    bottom:-10px;
    z-index:5;
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:7px;
    margin:14px -10px -10px;
    padding:10px;
    background:linear-gradient(to top,var(--panel) 75%,rgba(26,31,39,.94));
    border-top:1px solid var(--border);
  }
  .savebar:has(> button:only-child){
    grid-template-columns:1fr;
  }
  .savebar button{width:100%}

  .photo-grid{
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:7px;
  }
  .photo{min-width:0}
  .photo .meta{
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
  }

  .notice{padding:10px;font-size:.88rem}
}

/* Telefoni molto stretti */
@media(max-width:380px){
  .stats{grid-template-columns:1fr}
  .stat{
    display:flex;
    justify-content:space-between;
    align-items:center;
    text-align:left;
  }
  .stat b{display:inline}
  .typecard{grid-template-columns:minmax(0,1fr) auto}
  .typecount{font-size:.72rem}
  .photo-grid{grid-template-columns:1fr}
}

.voicewrap{position:relative}
.voicewrap input,.voicewrap textarea{padding-right:48px}
.micbtn{
  position:absolute;
  right:6px;
  top:50%;
  transform:translateY(-50%);
  min-width:36px;
  min-height:36px;
  padding:0;
  border-radius:9px;
  background:var(--panel2);
  color:var(--text);
  border:1px solid var(--border);
  z-index:2;
}
.voicewrap.textarea .micbtn{top:10px;transform:none}
.micbtn.listening{
  box-shadow:0 0 0 2px rgba(114,179,245,.28),0 0 18px rgba(114,179,245,.25);
  border-color:var(--accent);
}
@media(max-width:640px){
  :root{
    --bg:#0b0d11;
    --panel:#171b22;
    --panel2:#242b35;
    --border:#566170;
    --text:#f7f9fb;
    --muted:#c0c7d0;
  }
  input,select,textarea{
    background:#2b333f;
    border-color:#687587;
    color:#ffffff;
    box-shadow:inset 0 0 0 1px rgba(255,255,255,.02);
  }
  input::placeholder,textarea::placeholder{color:#b6bfca;opacity:.95}
  input:focus,select:focus,textarea:focus{
    outline:none;
    border-color:#8ac7ff;
    box-shadow:0 0 0 2px rgba(114,179,245,.22);
  }
  .item,.typecard,.notice,.photo,.fieldrow{
    background:#202731;
    border-color:#4d5968;
  }
  .tabbtn{background:#2a323d;border-color:#536071}
  .micbtn{
    background:#343d49;
    border-color:#687587;
  }
}


/* v0.1.16 - card chiare trasparenti su ios-dark-mode-blue-red */
:root{
  --inv-bg-1:#123f58;
  --inv-bg-2:#24204c;
  --inv-bg-3:#8e3348;
  --inv-card:rgba(255,255,255,.12);
  --inv-card-strong:rgba(255,255,255,.17);
  --inv-card-soft:rgba(255,255,255,.09);
  --inv-field:rgba(10,14,20,.82);
  --inv-border:rgba(255,255,255,.24);
  --inv-border-strong:rgba(255,255,255,.40);
  --inv-text:#f7f9fb;
  --inv-muted:#d1d7df;
  --inv-focus:#78bdff;
}

html,body{
  min-height:100%;
  color:var(--inv-text) !important;
  background:
    radial-gradient(circle at 18% 7%, rgba(30,112,149,.78) 0%, rgba(30,112,149,0) 38%),
    radial-gradient(circle at 82% 8%, rgba(166,54,75,.76) 0%, rgba(166,54,75,0) 39%),
    linear-gradient(145deg,var(--inv-bg-1) 0%,var(--inv-bg-2) 48%,var(--inv-bg-3) 100%) !important;
  background-attachment:fixed !important;
}

body::before{
  content:"";
  position:fixed;
  inset:0;
  pointer-events:none;
  z-index:-1;
  background:linear-gradient(180deg,rgba(7,10,16,.04),rgba(7,10,16,.18));
}

.wrap{
  background:transparent !important;
}

/* Card chiare e trasparenti */
.stat,.panel,.item,.type-card,.type-row,.dialog{
  background:var(--inv-card) !important;
  border:1px solid var(--inv-border) !important;
  box-shadow:0 8px 24px rgba(0,0,0,.16) !important;
  backdrop-filter:blur(12px) saturate(125%);
  -webkit-backdrop-filter:blur(12px) saturate(125%);
}

/* Sezioni annidate leggermente più chiare per distinguersi */
.item .item,.panel .item,.fieldrow,.photo{
  background:var(--inv-card-strong) !important;
  border-color:var(--inv-border) !important;
}

button.secondary,.tabbtn{
  background:var(--inv-card-soft) !important;
  color:var(--inv-text) !important;
  border:1px solid var(--inv-border) !important;
  backdrop-filter:blur(10px);
  -webkit-backdrop-filter:blur(10px);
}

.tabbtn.active,
button.primary{
  border-color:rgba(120,189,255,.82) !important;
}

/* I campi restano scuri per avere contrasto netto con le card */
input,select,textarea{
  background:var(--inv-field) !important;
  color:var(--inv-text) !important;
  border:1px solid var(--inv-border-strong) !important;
  box-shadow:inset 0 1px 0 rgba(255,255,255,.03) !important;
}

input::placeholder,textarea::placeholder{
  color:#b7c0cb !important;
  opacity:1 !important;
}

input:focus,select:focus,textarea:focus{
  border-color:var(--inv-focus) !important;
  box-shadow:
    0 0 0 2px rgba(120,189,255,.22),
    inset 0 1px 0 rgba(255,255,255,.03) !important;
  outline:none !important;
}

.muted,.sub,.hint{
  color:var(--inv-muted) !important;
}

@media(max-width:700px){
  html,body{
    background:
      radial-gradient(circle at 8% 5%, rgba(32,120,157,.82) 0%, rgba(32,120,157,0) 34%),
      radial-gradient(circle at 94% 8%, rgba(170,57,79,.82) 0%, rgba(170,57,79,0) 36%),
      linear-gradient(155deg,#123f58 0%,#24204c 50%,#8e3348 100%) !important;
    background-attachment:fixed !important;
  }

  .stat,.panel,.item,.type-card,.type-row,.dialog{
    background:rgba(255,255,255,.13) !important;
    border-color:rgba(255,255,255,.28) !important;
    backdrop-filter:blur(12px) saturate(125%);
    -webkit-backdrop-filter:blur(12px) saturate(125%);
  }

  .item .item,.panel .item,.fieldrow,.photo{
    background:rgba(255,255,255,.18) !important;
  }

  input,select,textarea{
    background:rgba(9,13,18,.86) !important;
    border-color:rgba(255,255,255,.42) !important;
  }
}


/* v0.1.17 - aggiungi tipologia nel titolo */
.types-header-row{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
}
.types-header-row > :first-child{
  margin:0 !important;
}
.types-add-top{
  flex:0 0 auto;
  display:inline-flex;
  align-items:center;
  gap:6px;
  min-height:40px;
  padding:8px 12px;
  border-radius:12px;
  background:rgba(255,255,255,.12) !important;
  color:#f7f9fb !important;
  border:1px solid rgba(255,255,255,.28) !important;
  cursor:pointer;
  font-weight:700;
  backdrop-filter:blur(10px);
  -webkit-backdrop-filter:blur(10px);
}
.types-add-top:hover{
  background:rgba(255,255,255,.18) !important;
}
.types-add-icon{
  font-size:20px;
  line-height:1;
}
.old-type-add-hidden{
  display:none !important;
}
@media(max-width:700px){
  .types-header-row{
    gap:8px;
  }
  .types-add-top{
    min-height:38px;
    padding:7px 10px;
  }
  .types-add-label{
    display:none;
  }
  .types-add-icon{
    font-size:22px;
  }
}


/* v0.1.18 - accenti colore stile dashboard Home Assistant */
:root{
  --accent-blue:#45a7ff;
  --accent-cyan:#36d4e5;
  --accent-green:#4bd37b;
  --accent-yellow:#ffc928;
  --accent-orange:#ff9b3d;
  --accent-pink:#ff4fb3;
  --accent-purple:#9b6cff;
  --accent-red:#ff5c67;
}

/* Pulsanti principali */
button.primary,
.types-add-top{
  border:1px solid var(--accent-blue) !important;
  box-shadow:0 0 0 1px rgba(69,167,255,.10), 0 0 10px rgba(69,167,255,.12) !important;
}
button.primary:hover,
.types-add-top:hover{
  box-shadow:0 0 0 1px rgba(69,167,255,.18), 0 0 14px rgba(69,167,255,.18) !important;
}

/* Tab: colori alternati per ravvivare la GUI */
.tabbtn:nth-child(1){border-color:var(--accent-blue) !important;}
.tabbtn:nth-child(2){border-color:var(--accent-cyan) !important;}
.tabbtn:nth-child(3){border-color:var(--accent-green) !important;}
.tabbtn:nth-child(4){border-color:var(--accent-orange) !important;}
.tabbtn:nth-child(5){border-color:var(--accent-purple) !important;}

.tabbtn.active{
  box-shadow:0 0 10px rgba(69,167,255,.18) !important;
}

/* Card statistiche: un colore per riquadro */
.stat:nth-of-type(1){
  border-color:var(--accent-blue) !important;
  box-shadow:0 0 12px rgba(69,167,255,.10) !important;
}
.stat:nth-of-type(2){
  border-color:var(--accent-green) !important;
  box-shadow:0 0 12px rgba(75,211,123,.10) !important;
}
.stat:nth-of-type(3){
  border-color:var(--accent-pink) !important;
  box-shadow:0 0 12px rgba(255,79,179,.10) !important;
}

/* Azioni sugli elementi */
.item button{
  border:1px solid rgba(255,255,255,.24) !important;
}
.item button:nth-of-type(1){
  border-color:var(--accent-cyan) !important;
}
.item button:nth-of-type(2){
  border-color:var(--accent-yellow) !important;
}
.item button:nth-of-type(3){
  border-color:var(--accent-red) !important;
}

/* Tipologie: bordo colorato leggero a rotazione */
.type-row:nth-child(7n+1){border-color:var(--accent-blue) !important;}
.type-row:nth-child(7n+2){border-color:var(--accent-cyan) !important;}
.type-row:nth-child(7n+3){border-color:var(--accent-green) !important;}
.type-row:nth-child(7n+4){border-color:var(--accent-yellow) !important;}
.type-row:nth-child(7n+5){border-color:var(--accent-pink) !important;}
.type-row:nth-child(7n+6){border-color:var(--accent-purple) !important;}
.type-row:nth-child(7n+7){border-color:var(--accent-orange) !important;}

/* Sezioni principali con accento tenue */
.panel{
  border-color:rgba(255,255,255,.24) !important;
}
.panel:nth-of-type(1){
  box-shadow:0 0 0 1px rgba(69,167,255,.06) inset !important;
}
.panel:nth-of-type(2){
  box-shadow:0 0 0 1px rgba(75,211,123,.06) inset !important;
}

/* Focus coerente */
input:focus,select:focus,textarea:focus{
  border-color:var(--accent-blue) !important;
}

/* Mobile: colori visibili ma non troppo accesi */
@media(max-width:700px){
  .tabbtn,
  .types-add-top,
  button.primary{
    box-shadow:none !important;
  }
  .stat,
  .type-row,
  .item button{
    border-width:1px !important;
  }
}


/* v0.1.19 - campi personalizzati a fisarmonica */
.customgrid{
  display:block !important;
}
.custom-field-accordion{
  width:100%;
  margin-bottom:7px;
  border:1px solid rgba(255,255,255,.22);
  border-radius:10px;
  background:rgba(255,255,255,.07);
  overflow:hidden;
}
.custom-field-title{
  width:100%;
  min-height:38px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  padding:8px 11px;
  border:0 !important;
  border-radius:0 !important;
  background:transparent !important;
  color:#f7f9fb !important;
  font-weight:700;
  text-align:left;
  box-shadow:none !important;
  cursor:pointer;
}
.custom-field-title-right{
  display:flex;
  align-items:center;
  gap:8px;
  flex:0 0 auto;
}
.custom-field-filled{
  color:#63d887;
  font-weight:900;
}
.custom-field-arrow{
  display:inline-block;
  font-size:17px;
  opacity:.82;
  transition:transform .16s ease;
}
.custom-field-accordion.open .custom-field-arrow{
  transform:rotate(180deg);
}
.custom-field-body{
  display:none;
  padding:0 10px 10px;
}
.custom-field-accordion.open .custom-field-body{
  display:block;
}
.custom-field-body input,
.custom-field-body select,
.custom-field-body textarea{
  width:100%;
}
.custom-field-body .hint{
  display:block;
  margin-top:5px;
}
.custom-field-accordion.open{
  border-color:#45a7ff;
  background:rgba(255,255,255,.10);
}
@media(max-width:700px){
  .custom-field-title{
    min-height:44px;
    padding:10px 12px;
    font-size:.95rem;
  }
  .custom-field-accordion{
    margin-bottom:8px;
  }
}


/* v0.1.20 - spazio di sicurezza per tastiera mobile */
@media(max-width:700px){
  body{
    padding-bottom:34vh;
  }
  input:focus,
  textarea:focus,
  select:focus{
    scroll-margin-top:110px;
    scroll-margin-bottom:38vh;
  }
}


/* v0.1.21 - dashboard compatta: nuovo elemento a scomparsa + lista limitata */
.new-item-panel{
  padding:0 !important;
  overflow:hidden;
}
.new-item-head{
  width:100%;
  min-height:48px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  padding:12px 14px;
  background:transparent !important;
  color:#f7f9fb !important;
  border:0 !important;
  box-shadow:none !important;
  font-size:1.05rem;
  font-weight:800;
  text-align:left;
  cursor:pointer;
}
.new-item-head:hover{
  background:rgba(255,255,255,.06) !important;
}
.new-item-chevron{
  font-size:18px;
  opacity:.85;
}
.new-item-body{
  padding:0 12px 12px;
}
.new-item-panel.collapsed .new-item-body{
  display:none;
}
.new-item-panel.collapsed .new-item-head{
  border-radius:inherit;
}

.items-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:12px;
  margin-bottom:4px;
}
.items-head h2{
  margin:0 !important;
}
.items-limit-wrap{
  display:flex;
  align-items:center;
  gap:7px;
  color:#d1d7df;
  font-size:.82rem;
  white-space:nowrap;
}
.items-limit-wrap select{
  width:auto !important;
  min-width:66px;
  padding:6px 26px 6px 9px !important;
  min-height:34px;
}
.items-list-info{
  min-height:18px;
  margin:2px 0 8px;
  color:#cbd3dc;
  font-size:.78rem;
}

@media(max-width:700px){
  .new-item-head{
    min-height:52px;
    padding:13px 14px;
    font-size:1rem;
  }
  .items-head{
    align-items:center;
  }
  .items-limit-wrap span{
    display:none;
  }
  .items-limit-wrap select{
    min-width:62px;
    min-height:38px;
  }
}


/* v0.1.22 - contorni colore più evidenti */
:root{
  --accent-blue:#4fb0ff;
  --accent-cyan:#37e0ef;
  --accent-green:#58e28a;
  --accent-yellow:#ffd23a;
  --accent-orange:#ffad4a;
  --accent-pink:#ff63c3;
  --accent-purple:#aa7cff;
  --accent-red:#ff6673;
}
.tabbtn:nth-child(1){border:1.5px solid var(--accent-blue)!important;box-shadow:0 0 9px rgba(79,176,255,.20)!important}
.tabbtn:nth-child(2){border:1.5px solid var(--accent-cyan)!important;box-shadow:0 0 9px rgba(55,224,239,.18)!important}
.tabbtn:nth-child(3){border:1.5px solid var(--accent-green)!important;box-shadow:0 0 9px rgba(88,226,138,.18)!important}
.tabbtn:nth-child(4){border:1.5px solid var(--accent-orange)!important;box-shadow:0 0 9px rgba(255,173,74,.18)!important}
.tabbtn:nth-child(5){border:1.5px solid var(--accent-purple)!important;box-shadow:0 0 9px rgba(170,124,255,.18)!important}
.stat:nth-of-type(1){border:1.5px solid var(--accent-blue)!important;box-shadow:0 0 12px rgba(79,176,255,.17)!important}
.stat:nth-of-type(2){border:1.5px solid var(--accent-green)!important;box-shadow:0 0 12px rgba(88,226,138,.17)!important}
.stat:nth-of-type(3){border:1.5px solid var(--accent-pink)!important;box-shadow:0 0 12px rgba(255,99,195,.17)!important}
.types-add-top,button.primary{border:1.5px solid var(--accent-blue)!important;box-shadow:0 0 12px rgba(79,176,255,.20)!important}
.item button:nth-of-type(1){border:1.5px solid var(--accent-cyan)!important;box-shadow:0 0 8px rgba(55,224,239,.16)!important}
.item button:nth-of-type(2){border:1.5px solid var(--accent-yellow)!important;box-shadow:0 0 8px rgba(255,210,58,.16)!important}
.item button:nth-of-type(3){border:1.5px solid var(--accent-red)!important;box-shadow:0 0 8px rgba(255,102,115,.18)!important}
.type-row:nth-child(7n+1){border:1.5px solid var(--accent-blue)!important}
.type-row:nth-child(7n+2){border:1.5px solid var(--accent-cyan)!important}
.type-row:nth-child(7n+3){border:1.5px solid var(--accent-green)!important}
.type-row:nth-child(7n+4){border:1.5px solid var(--accent-yellow)!important}
.type-row:nth-child(7n+5){border:1.5px solid var(--accent-pink)!important}
.type-row:nth-child(7n+6){border:1.5px solid var(--accent-purple)!important}
.type-row:nth-child(7n+7){border:1.5px solid var(--accent-orange)!important}
.panel,.item,.dialog{border-color:rgba(255,255,255,.32)!important}
.custom-field-accordion{border-color:rgba(255,255,255,.30)!important}
.custom-field-accordion.open{border:1.5px solid var(--accent-blue)!important;box-shadow:0 0 10px rgba(79,176,255,.14)!important}


/* v0.1.23 - correzione disposizione editor tipologie su mobile */
@media(max-width:640px){

  /* Il wrapper del microfono deve occupare tutta la riga del campo nome */
  #typeDlg .fieldrow > .voicewrap{
    grid-column:1 / -1 !important;
    width:100% !important;
    min-width:0 !important;
  }

  #typeDlg .fieldrow > .voicewrap .flabel{
    width:100% !important;
    min-width:0 !important;
  }

  /* Struttura più ordinata del singolo campo personalizzato */
  #typeDlg .fieldrow{
    grid-template-columns:1fr 1fr !important;
    gap:8px !important;
    padding:10px !important;
  }

  #typeDlg .fieldrow .ftype,
  #typeDlg .fieldrow .options,
  #typeDlg .fieldrow > .voicewrap{
    grid-column:1 / -1 !important;
  }

  #typeDlg .fieldrow .check{
    grid-column:1 / -1 !important;
    margin:2px 0 !important;
  }

  #typeDlg .fieldrow button{
    min-height:42px !important;
  }

  /* I pulsanti Salva/Annulla/Elimina non coprono più i campi sottostanti */
  #typeDlg .savebar{
    position:static !important;
    margin:16px 0 0 !important;
    padding:12px 0 0 !important;
    background:transparent !important;
    border-top:1px solid rgba(255,255,255,.22) !important;
    grid-template-columns:1fr 1fr !important;
  }

  #typeDlg .savebar .dialog-danger{
    grid-column:1 / 2 !important;
  }

  #typeDlg .savebar button:last-child{
    grid-column:1 / -1 !important;
  }

  /* Niente spazio artificiale enorme in fondo al dialog */
  #typeDlg .dialog{
    padding-bottom:14px !important;
  }

  /* Migliore separazione visiva tra i campi */
  #typeDlg .fieldrow{
    background:rgba(255,255,255,.14) !important;
    border-color:rgba(255,255,255,.32) !important;
  }
}

@media(max-width:380px){
  #typeDlg .savebar{
    grid-template-columns:1fr !important;
  }
  #typeDlg .savebar .dialog-danger,
  #typeDlg .savebar button:last-child{
    grid-column:1 !important;
  }
}


/* v0.1.25 - Step 2 ISBN: ricerca manuale on-demand */
.book-lookup-row{display:flex;gap:8px;align-items:center;margin-top:8px;flex-wrap:wrap}
.book-lookup-row button{min-height:40px}
.book-lookup-status{font-size:.84rem;opacity:.88}
@media(max-width:640px){.book-lookup-row button{width:100%}.book-lookup-status{width:100%}}


/* v0.1.26 - Step 3: scansione ISBN/EAN da fotocamera mobile */
.book-lookup-row .scan-code-btn{border:1.5px solid var(--accent-green)!important;box-shadow:0 0 9px rgba(88,226,138,.17)!important}
.barcode-dialog{max-width:620px!important}
.barcode-reader{
  position:relative;
  width:100%;
  overflow:hidden;
  border-radius:16px;
  background:#05070a;
  border:1.5px solid rgba(79,176,255,.72);
  box-shadow:0 0 16px rgba(79,176,255,.16);
}
.barcode-reader video{display:block;width:100%;max-height:58vh;object-fit:cover;background:#000}
.barcode-guide{
  position:absolute;left:7%;right:7%;top:50%;height:92px;transform:translateY(-50%);
  border:2px solid rgba(88,226,138,.92);border-radius:12px;
  box-shadow:0 0 0 9999px rgba(0,0,0,.22),0 0 14px rgba(88,226,138,.32);
  pointer-events:none;
}
.barcode-guide:after{content:'EAN / ISBN';position:absolute;right:8px;bottom:5px;font-size:.72rem;font-weight:700;color:#b9ffd0}
.barcode-status{margin:10px 0 0;font-size:.9rem;min-height:1.3em}
.barcode-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
.barcode-actions button{flex:1;min-width:140px}
@media(max-width:640px){
  .book-lookup-row{display:grid!important;grid-template-columns:1fr 1fr!important}
  .book-lookup-row button{width:auto!important}
  .book-lookup-status{grid-column:1/-1;width:100%!important}
  .barcode-dialog{width:100%!important;height:100%!important;max-height:none!important;border-radius:0!important}
  .barcode-reader video{max-height:56vh}
}
@media(max-width:390px){.book-lookup-row{grid-template-columns:1fr!important}.book-lookup-status{grid-column:1!important}}


/* v0.1.32 - ottimizzazione intestazione inventario su smartphone */
@media(max-width:640px){
  .items-head{
    display:block !important;
    width:100% !important;
    margin-bottom:8px !important;
  }

  .items-head h2{
    display:block !important;
    width:100% !important;
    margin:0 0 10px 0 !important;
    font-size:1.08rem !important;
    line-height:1.2 !important;
    white-space:nowrap !important;
  }

  .items-head-controls{
    display:grid !important;
    grid-template-columns:minmax(0,1fr) 92px !important;
    gap:8px !important;
    width:100% !important;
    align-items:end !important;
  }

  .items-group-wrap,
  .items-limit-wrap{
    display:grid !important;
    grid-template-columns:1fr !important;
    gap:4px !important;
    width:100% !important;
    min-width:0 !important;
    font-size:.72rem !important;
    color:#d7dbe2 !important;
  }

  .items-group-wrap span,
  .items-limit-wrap span{
    display:block !important;
    padding-left:2px !important;
  }

  .items-group-wrap select,
  .items-limit-wrap select{
    width:100% !important;
    min-width:0 !important;
    min-height:42px !important;
    padding:8px 30px 8px 10px !important;
    font-size:16px !important;
  }

  .items-list-info{
    margin:4px 0 8px !important;
  }

  .item-group-head{
    padding:10px 2px !important;
    gap:8px !important;
  }

  .item-group-title{
    min-width:0 !important;
    overflow:hidden !important;
  }

  .item-group-title span:last-child{
    min-width:0 !important;
    overflow:hidden !important;
    text-overflow:ellipsis !important;
    white-space:nowrap !important;
  }

  .item-group-count{
    font-size:.78rem !important;
  }
}


/* v0.1.33 - bordi più leggibili e sezioni più riconoscibili */
:root{
  --border-strong:rgba(255,255,255,.56);
  --border-field:rgba(255,255,255,.48);
  --surface-line:rgba(255,255,255,.08);
}

/* Sezioni principali */
.panel,
.dialog,
.new-item-head{
  border:1.6px solid var(--border-strong) !important;
  box-shadow:
    inset 0 0 0 1px var(--surface-line),
    0 0 0 1px rgba(0,0,0,.08) !important;
}

/* Campi e selettori */
input,
select,
textarea{
  border:1.5px solid var(--border-field) !important;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.025) !important;
}

input:focus,
select:focus,
textarea:focus{
  border-color:var(--accent-blue) !important;
  box-shadow:
    0 0 0 1px rgba(79,176,255,.34),
    0 0 10px rgba(79,176,255,.13) !important;
  outline:none !important;
}

/* Elenco raggruppato */
.item-group{
  border:1.5px solid rgba(255,255,255,.34) !important;
  border-radius:12px !important;
  overflow:hidden !important;
  background:rgba(255,255,255,.035) !important;
  margin-bottom:8px !important;
}

.item-group-head{
  border:0 !important;
  border-bottom:1px solid rgba(255,255,255,.24) !important;
  padding:10px 11px !important;
  background:rgba(255,255,255,.045) !important;
}

.item-group.collapsed .item-group-head{
  border-bottom:0 !important;
}

.item-group-body{
  padding:7px !important;
}

/* Singoli elementi */
.item-row{
  border:1.5px solid rgba(255,255,255,.38) !important;
  background:rgba(18,20,28,.52) !important;
}

.item-row + .item-row{
  margin-top:6px !important;
}

/* Tipologie: più riconoscibili e distinte */
.typecard{
  border:1.6px solid rgba(255,255,255,.42) !important;
  background:rgba(255,255,255,.055) !important;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.025) !important;
}

.typecard:nth-child(7n+1){border-color:rgba(79,176,255,.82)!important}
.typecard:nth-child(7n+2){border-color:rgba(55,224,239,.78)!important}
.typecard:nth-child(7n+3){border-color:rgba(88,226,138,.78)!important}
.typecard:nth-child(7n+4){border-color:rgba(255,210,58,.78)!important}
.typecard:nth-child(7n+5){border-color:rgba(255,99,195,.78)!important}
.typecard:nth-child(7n+6){border-color:rgba(170,124,255,.80)!important}
.typecard:nth-child(7n+7){border-color:rgba(255,173,74,.80)!important}

.typecard:focus-visible,
.typecard:hover{
  box-shadow:0 0 10px rgba(255,255,255,.08) !important;
}

/* Campi personalizzati */
.custom-field-accordion{
  border:1.5px solid rgba(255,255,255,.40) !important;
  background:rgba(255,255,255,.045) !important;
}

.custom-field-accordion.open{
  border-color:var(--accent-blue) !important;
  box-shadow:0 0 10px rgba(79,176,255,.14) !important;
}

/* Pulsanti secondari/azioni e tab */
.tabbtn,
.secondary,
.types-add-top,
.type-add{
  border-width:1.5px !important;
}

/* Ricerca principale */
.search input,
.search > button{
  border:1.5px solid rgba(255,255,255,.48) !important;
}

@media(max-width:640px){
  .panel{
    border-width:1.6px !important;
  }

  .item-group{
    border-color:rgba(255,255,255,.40) !important;
  }

  .item-group-head{
    min-height:48px !important;
  }

  .typecard{
    min-height:48px !important;
  }

  input,
  select,
  textarea{
    border-width:1.5px !important;
  }
}


/* v2.1.0 - inventari grandi: gruppi paginati */
.items-page-size{
  display:flex;align-items:center;justify-content:center;
  min-height:38px;padding:7px 10px;border:1.5px solid rgba(255,255,255,.38);
  border-radius:10px;color:var(--muted);font-size:.78rem;background:rgba(18,20,28,.36)
}
.item-group-side{display:flex;align-items:center;gap:9px;flex:0 0 auto}
.inventory-loader{padding:12px;text-align:center;color:var(--muted);font-size:.84rem}
.load-more-btn{
  width:100%;margin-top:7px;display:flex;justify-content:space-between;align-items:center;gap:8px;
  border:1.5px dashed rgba(79,176,255,.62)!important;background:rgba(79,176,255,.07)!important
}
.load-more-btn span{font-size:.76rem;color:var(--muted);font-weight:500}
.flat-items-body{padding-top:4px}
@media(max-width:640px){
  .items-head-controls{grid-template-columns:minmax(0,1fr) auto!important}
  .items-page-size{min-height:42px;white-space:nowrap;padding:8px 9px}
  .load-more-btn{min-height:46px!important}
}


/* v2.1.0 - sottogruppi configurabili */
.item-subgroup{margin:7px 5px 9px 18px;border:1.5px solid rgba(255,255,255,.34);border-radius:11px;background:rgba(0,0,0,.10);overflow:hidden;transition:border-color .18s ease,box-shadow .18s ease,background .18s ease}
.item-subgroup-head{width:100%;display:flex;align-items:center;justify-content:space-between;gap:10px;border:0;border-bottom:1px solid rgba(255,255,255,.20);background:rgba(255,255,255,.045);color:var(--text);padding:9px 11px;font:inherit;cursor:pointer;transition:background .18s ease,color .18s ease}
.item-subgroup-title{font-weight:750;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.item-subgroup-body{padding:8px 8px 9px 12px;border-left:3px solid transparent}.item-subgroup.collapsed .item-subgroup-body{display:none}.item-subgroup.collapsed .item-subgroup-head{border-bottom:0}.item-subgroup.collapsed .item-subgroup-arrow{transform:rotate(-90deg)}
.item-subgroup-arrow{display:inline-block;color:var(--muted);font-size:1.05rem;transition:transform .18s ease,color .18s ease}
/* v2.1.3 - sottogruppo aperto evidenziato e distinto dai suoi elementi */
.item-subgroup:not(.collapsed){border-color:var(--accent-cyan);background:rgba(55,224,239,.055);box-shadow:0 0 0 1px rgba(55,224,239,.16),0 0 14px rgba(55,224,239,.12)}
.item-subgroup:not(.collapsed)>.item-subgroup-head{background:linear-gradient(90deg,rgba(55,224,239,.22),rgba(79,176,255,.10));border-bottom-color:rgba(55,224,239,.50);color:#fff}
.item-subgroup:not(.collapsed)>.item-subgroup-head .item-subgroup-title{font-weight:850;text-shadow:0 0 10px rgba(55,224,239,.22)}
.item-subgroup:not(.collapsed)>.item-subgroup-head .item-group-count{color:#fff;font-weight:800}
.item-subgroup:not(.collapsed)>.item-subgroup-head .item-subgroup-arrow{color:var(--accent-cyan)}
.item-subgroup:not(.collapsed)>.item-subgroup-body{border-left-color:rgba(55,224,239,.58);background:rgba(5,12,22,.16)}
@media(max-width:640px){.item-subgroup{margin-left:10px;margin-right:2px}.item-subgroup-head{min-height:46px}.item-subgroup:not(.collapsed)>.item-subgroup-body{padding-left:10px}}

.item-preview-dialog{max-width:640px}
.item-preview-photos{margin:10px 0 12px}
.item-preview-photo-title{font-weight:800;color:var(--muted);margin-bottom:7px}
.item-preview-photo-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.item-preview-photo{position:relative;border:1.5px solid var(--border-field);border-radius:11px;padding:5px;background:rgba(0,0,0,.18);overflow:hidden}
.item-preview-photo button{display:block;width:100%;padding:0;border:0;background:transparent;cursor:pointer}
.item-preview-photo img{display:block;width:100%;aspect-ratio:1/1;object-fit:cover;border-radius:8px}
.item-preview-photo-label{padding:5px 3px 1px;font-size:.76rem;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item-preview-photo-more{margin-top:7px;color:var(--muted);font-size:.78rem;text-align:right}
.item-preview-no-photo{width:100%;min-height:72px;display:flex;align-items:center;justify-content:center;gap:8px;border:1.5px dashed rgba(79,176,255,.62)!important;border-radius:11px;background:rgba(79,176,255,.07)!important;color:var(--text);font:inherit;font-weight:750;cursor:pointer}
.item-preview-list{display:grid;gap:8px;margin:12px 0 4px}
.item-preview-row{display:grid;grid-template-columns:minmax(120px,180px) 1fr;gap:10px;padding:8px 10px;border:1.5px solid var(--border-field);border-radius:10px;background:rgba(0,0,0,.16)}
.item-preview-label{font-weight:800;color:var(--muted)}
.item-preview-value{white-space:pre-wrap;word-break:break-word}
@media(max-width:640px){.item-preview-row{grid-template-columns:1fr;gap:3px}.item-preview-dialog{width:100%}.item-preview-photo-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}

.inventory-pager{
  display:flex;
  align-items:center;
  justify-content:center;
  flex-wrap:wrap;
  gap:7px;
  margin-top:10px;
}

.inventory-pager button{
  width:auto;
  min-width:0;
  padding:7px 10px;
}

.inventory-pager .hint{
  padding:0 5px;
  white-space:nowrap;
}


/* v2.2.1 - tema Home Assistant + cancellazione ricerca */
.search-input-wrap{
  position:relative;
  min-width:0;
  width:100%;
}

.search-input-wrap input{
  padding-right:44px !important;
}

.search-clear{
  display:none;
  position:absolute;
  right:9px;
  top:50%;
  transform:translateY(-50%);
  z-index:3;
  width:26px;
  min-width:26px;
  height:30px;
  min-height:30px;
  padding:0 !important;
  border:0 !important;
  border-radius:0 !important;
  background:transparent !important;
  color:var(--inv-muted) !important;
  box-shadow:none !important;
  font-family:Arial,sans-serif;
  font-size:22px;
  line-height:30px;
  font-weight:400;
  text-align:center;
}

.search-clear.show{
  display:block;
}

.search-clear:hover,
.search-clear:focus-visible{
  color:var(--inv-text) !important;
  background:transparent !important;
  outline:none;
}

/*
 * Quando Inventario Casa gira dentro Home Assistant Ingress,
 * JavaScript copia sul documento dell'app i colori del tema HA.
 * Se non sono disponibili, resta esattamente il tema Inventario
 * blu/viola/rosso usato fino alla 2.2.0.
 */
html.ha-theme-linked,
html.ha-theme-linked body{
  color:var(--primary-text-color,var(--inv-text)) !important;
  background:var(
    --lovelace-background,
    var(--primary-background-color,var(--inv-bg-2))
  ) !important;
  background-attachment:fixed !important;
  background-size:cover !important;
  background-position:center !important;
}

html.ha-theme-linked body::before{
  background:transparent !important;
}

html.ha-theme-linked .stat,
html.ha-theme-linked .panel,
html.ha-theme-linked .item,
html.ha-theme-linked .type-card,
html.ha-theme-linked .type-row,
html.ha-theme-linked .dialog{
  background:
    color-mix(
      in srgb,
      var(--card-background-color,var(--secondary-background-color,#1a1f27)) 88%,
      transparent
    ) !important;
}

html.ha-theme-linked .item .item,
html.ha-theme-linked .panel .item,
html.ha-theme-linked .fieldrow,
html.ha-theme-linked .photo{
  background:
    color-mix(
      in srgb,
      var(--secondary-background-color,#222936) 88%,
      transparent
    ) !important;
}

html.ha-theme-linked input,
html.ha-theme-linked select,
html.ha-theme-linked textarea{
  background:var(--input-fill-color,var(--secondary-background-color,#0f1318)) !important;
  color:var(--primary-text-color,var(--inv-text)) !important;
}

html.ha-theme-linked input::placeholder,
html.ha-theme-linked textarea::placeholder{
  color:var(--secondary-text-color,var(--inv-muted)) !important;
}

html.ha-theme-linked .sub,
html.ha-theme-linked .meta,
html.ha-theme-linked .hint,
html.ha-theme-linked .muted{
  color:var(--secondary-text-color,var(--inv-muted)) !important;
}

html.ha-theme-linked button.primary,
html.ha-theme-linked .types-add-top,
html.ha-theme-linked input:focus,
html.ha-theme-linked select:focus,
html.ha-theme-linked textarea:focus{
  border-color:var(--primary-color,var(--accent-blue)) !important;
}

html.ha-theme-linked .search-clear{
  color:var(--secondary-text-color,var(--inv-muted)) !important;
}

@media(max-width:640px){
  .search{
    grid-template-columns:minmax(0,1fr) 48px !important;
  }

  .search-clear{
    width:28px;
    height:32px;
    min-width:28px;
    min-height:32px;
    right:8px;
    font-size:22px;
    line-height:32px;
  }

  html.ha-theme-linked,
  html.ha-theme-linked body{
    background:var(
      --lovelace-background,
      var(--primary-background-color,var(--inv-bg-2))
    ) !important;
    background-size:cover !important;
    background-position:center !important;
  }
}


/* v2.2.2 - fix editor tipologie mobile e chiusura dialog */
.dialog{
  position:relative;
}

.dialog-close-btn{
  position:absolute;
  top:10px;
  right:10px;
  z-index:20;
  width:42px !important;
  min-width:42px !important;
  max-width:42px !important;
  height:42px;
  min-height:42px !important;
  padding:0 !important;
  display:flex;
  align-items:center;
  justify-content:center;
  border-radius:50% !important;
  border:1.5px solid rgba(255,255,255,.42) !important;
  background:rgba(20,24,30,.88) !important;
  color:#fff !important;
  box-shadow:0 2px 12px rgba(0,0,0,.25) !important;
  font-size:27px !important;
  font-family:Arial,sans-serif !important;
  font-weight:400 !important;
  line-height:1 !important;
}

.dialog-close-btn:hover,
.dialog-close-btn:focus-visible{
  border-color:var(--accent-blue) !important;
  background:rgba(35,43,53,.96) !important;
  outline:none;
}

.dialog > h2{
  padding-right:58px !important;
}

@media(max-width:640px){

  /* Il nome del campo occupa tutta la riga */
  #typeDlg .fieldrow > .voicewrap{
    grid-column:1 / -1 !important;
    width:100% !important;
    min-width:0 !important;
  }

  #typeDlg .fieldrow > .voicewrap .flabel{
    width:100% !important;
    min-width:0 !important;
    padding-right:56px !important;
  }

  /* Il microfono resta un piccolo pulsante a destra:
     non eredita width:100% dai pulsanti della fieldrow. */
  #typeDlg .fieldrow .micbtn{
    width:40px !important;
    min-width:40px !important;
    max-width:40px !important;
    height:40px !important;
    min-height:40px !important;
    padding:0 !important;
    right:6px !important;
  }

  /* X sempre raggiungibile anche scorrendo una dialog full-screen */
  .dialog-close-btn{
    position:fixed;
    top:max(8px, env(safe-area-inset-top));
    right:10px;
    width:42px !important;
    min-width:42px !important;
    max-width:42px !important;
  }

  .dialog > h2{
    padding-right:58px !important;
  }
}

/* v2.3.1 - Backup UI polish */
#backupDlg .dialog{
  width:min(760px,calc(100vw - 24px));
  max-height:88vh;
  overflow:auto;
}
#backupDlg h2{
  margin:0 44px 14px 0;
}
#backupDlg .backup-info{
  display:flex;
  align-items:flex-start;
  gap:12px;
  margin:0 0 14px;
  padding:12px 14px;
  border:1.5px solid rgba(79,176,255,.42);
  border-radius:14px;
  background:rgba(79,176,255,.08);
}
#backupDlg .backup-info-icon{
  flex:0 0 auto;
  width:30px;
  height:30px;
  border-radius:50%;
  display:grid;
  place-items:center;
  background:rgba(79,176,255,.18);
  border:1px solid rgba(79,176,255,.42);
  font-weight:900;
}
#backupDlg .backup-info code{
  display:inline-block;
  margin-top:4px;
  padding:2px 6px;
  border-radius:7px;
  background:rgba(0,0,0,.22);
  color:#d8ecff;
  overflow-wrap:anywhere;
}
#backupDlg .backup-create-btn{
  width:100%;
  display:flex;
  align-items:center;
  gap:12px;
  text-align:left;
  padding:13px 14px;
  border-radius:14px;
  margin-bottom:16px;
}
#backupDlg .backup-create-icon{
  font-size:1.45rem;
  line-height:1;
}
#backupDlg .backup-create-btn span:last-child{
  display:flex;
  flex-direction:column;
}
#backupDlg .backup-create-btn small{
  margin-top:2px;
  opacity:.76;
  font-weight:500;
}
#backupDlg .backup-list-head{
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:10px;
  margin:4px 0 9px;
}
#backupDlg .backup-count{
  min-width:28px;
  height:28px;
  padding:0 8px;
  border-radius:999px;
  display:grid;
  place-items:center;
  background:rgba(255,255,255,.10);
  border:1px solid rgba(255,255,255,.24);
  font-size:.78rem;
  font-weight:800;
}
#backupDlg .backup-row{
  position:relative;
  padding:14px;
  border:1.5px solid rgba(255,255,255,.30);
  border-radius:15px;
  background:rgba(255,255,255,.045);
  box-shadow:0 8px 24px rgba(0,0,0,.14);
}
#backupDlg .backup-row-name{
  font-size:.92rem;
  line-height:1.3;
  font-weight:800;
  color:#f4f7fb;
  overflow-wrap:anywhere;
}
#backupDlg .backup-row-meta{
  display:flex;
  gap:6px;
  flex-wrap:wrap;
  margin-top:9px;
  font-size:.76rem;
  color:var(--inv-muted,var(--muted));
}
#backupDlg .backup-row-meta span{
  padding:4px 7px;
  border-radius:999px;
  background:rgba(255,255,255,.07);
  border:1px solid rgba(255,255,255,.14);
}
#backupDlg .backup-row-status{
  display:inline-flex;
  align-items:center;
  gap:5px;
  margin-top:9px;
  padding:5px 8px;
  border-radius:999px;
  font-size:.78rem;
  font-weight:800;
}
#backupDlg .backup-row-status.ok{
  color:#7ce6a4;
  background:rgba(89,210,137,.10);
  border:1px solid rgba(89,210,137,.28);
}
#backupDlg .backup-row-status.bad{
  color:#ff9b9b;
  background:rgba(255,95,95,.09);
  border:1px solid rgba(255,95,95,.25);
}
#backupDlg .backup-row-actions{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:8px;
  margin-top:12px;
}
#backupDlg .backup-row-actions a,
#backupDlg .backup-row-actions button{
  min-width:0;
  width:100%;
  min-height:40px;
  border-radius:11px;
}
#backupDlg .backup-download{
  display:flex;
  align-items:center;
  justify-content:center;
  text-decoration:none;
  padding:8px 10px;
  background:rgba(79,176,255,.14);
  color:#9fd2ff;
  border:1px solid rgba(79,176,255,.34);
  font-weight:700;
}
#backupDlg .backup-restore{
  background:rgba(255,173,66,.14);
  color:#ffd59a;
  border:1px solid rgba(255,173,66,.34);
}
@media(max-width:640px){
  #backupDlg .dialog{
    width:calc(100vw - 14px);
    max-height:94vh;
    border-radius:16px;
    padding:16px 14px;
  }
  #backupDlg .backup-row-actions{
    grid-template-columns:1fr;
  }
  #backupDlg .backup-info{
    padding:11px 12px;
  }
}

</style>
</head>
<body>
<div class="wrap">
<header>
  <div><h1>🏠 Inventario Casa</h1><div class="sub">Trova cosa possiedi e dove si trova.</div></div>
  <div class="search">
    <div class="search-input-wrap">
      <input id="search" placeholder="Cerca qualsiasi cosa…" oninput="updateSearchClear()">
      <button id="searchClear"
              type="button"
              class="search-clear"
              onclick="clearSearch()"
              aria-label="Cancella ricerca"
              title="Cancella ricerca">×</button>
    </div>
    <button type="button" class="secondary" onclick="load()">🔎</button>
  </div>
</header>

<div class="stats">
  <div class="stat"><b id="countItems">0</b><span class="sub">elementi</span></div>
  <div class="stat"><b id="countEnv">0</b><span class="sub">ambienti</span></div>
  <div class="stat"><b id="countTypes">0</b><span class="sub">tipologie</span></div>
</div>

<div class="layout">
<main>
  <div id="newItemPanel" class="panel new-item-panel collapsed">
    <button type="button" class="new-item-head" onclick="toggleNewItemPanel()" aria-expanded="false">
      <span>➕ Nuovo elemento</span>
      <span id="newItemChevron" class="new-item-chevron">▾</span>
    </button>
    <div class="new-item-body">
    <div class="tabs">
      <button class="tabbtn active" onclick="showTab('add','general',this)">Generale</button>
      <button class="tabbtn" onclick="showTab('add','details',this)">Dettagli</button>
      <button class="tabbtn" onclick="showTab('add','position',this)">Posizione</button>
      <button class="tabbtn" onclick="showTab('add','photos',this)">Foto</button>
      <button class="tabbtn" onclick="showTab('add','notes',this)">Note</button>
    </div>

    <div id="add-general" class="tab active">
      <div class="form">
        <input id="aName" class="full" placeholder="Nome elemento">
        <select id="aType" onchange="renderCustom('add')"></select>
        <input id="aQty" type="number" min="1" value="1" placeholder="Quantità">
      </div>
    </div>

    <div id="add-details" class="tab">
      <div id="customAdd" class="customgrid"></div>
    </div>

    <div id="add-position" class="tab">
      <div class="form">
        <input id="aEnv" list="envs" placeholder="Ambiente, es. Cantina">
        <input id="aFurn" list="furns" placeholder="Mobile/Scaffale">
        <input id="aShelf" list="shelves" placeholder="Ripiano/Cassetto">
        <input id="aCont" list="containers" placeholder="Contenitore">
        <input id="aCode" class="full" placeholder="Codice contenitore, es. C12">
      </div>
    </div>

    <div id="add-photos" class="tab">
      <div class="notice">Le foto si possono caricare subito dopo aver salvato l'elemento. Il programma aprirà automaticamente la scheda completa.</div>
    </div>

    <div id="add-notes" class="tab">
      <div class="form">
        <textarea id="aDesc" class="full" placeholder="Descrizione"></textarea>
        <textarea id="aNotes" class="full" placeholder="Note"></textarea>
        <input id="aTags" class="full" placeholder="Tag, separati da virgola">
      </div>
    </div>

    <div class="savebar"><button onclick="createItem()">Salva elemento</button></div>
    </div>
  </div>

  <div class="panel">
    <div class="items-head">
      <h2 id="itemsTitle">📦 Elementi</h2>
      <div class="items-head-controls">
        <label class="items-group-wrap" title="Come raggruppare l'elenco">
          <span>Raggruppa</span>
          <select id="itemsGroupBy" onchange="changeItemsGrouping(this.value)">
            <option value="type">Tipologia</option>
            <option value="environment">Ambiente</option>
            <option value="none">Nessuno</option>
          </select>
        </label>
        <div class="items-page-size" title="Caricamento progressivo">50 per volta</div>
      </div>
    </div>
    <div id="itemsListInfo" class="items-list-info"></div>
    <div id="items"></div>
  </div>
</main>

<aside>
  <div id="typePanel" class="panel type-panel">
    <div class="type-panel-head">
      <div class="types-header-row">
  <h2>🏷️ Tipologie</h2>
  <button type="button" class="types-add-top" onclick="openTypeDialog()" title="Nuova tipologia">
    <span class="types-add-icon">＋</span>
    <span class="types-add-label">Aggiungi</span>
  </button>
</div>
      <button id="typeCollapseBtn" class="secondary small" onclick="toggleTypePanel()" title="Riduci/espandi tipologie">▾</button>
    </div>
    <div class="type-panel-body">
      <div class="type-tools">
        <input id="typeSearch" placeholder="Cerca tipologia…" oninput="renderTypes()">
      </div>
      <div id="typeList"></div>
      <button class="type-add" onclick="openTypeDialog()">➕ Nuova tipologia</button>
    </div>
  </div>

  <div class="panel">
    <div class="backup-panel-head">
      <h2>🛟 Backup database</h2>
      <button type="button"
              class="secondary small"
              onclick="openBackupDialog()">Gestisci</button>
    </div>
    <div class="hint" style="margin-top:8px">
      Backup e ripristino dell'archivio Inventario Casa.
    </div>
  </div>
</aside>
</div>
</div>

<datalist id="envs"></datalist>
<datalist id="furns"></datalist>
<datalist id="shelves"></datalist>
<datalist id="containers"></datalist>

<div id="backupDlg"
     class="dialogbg"
     onclick="if(event.target===this) closeBackupDialog()">
  <div class="dialog">
    <button type="button"
            class="dialog-close-btn"
            onclick="closeBackupDialog()"
            aria-label="Chiudi"
            title="Chiudi">×</button>

    <h2>🛟 Backup database</h2>

    <div class="backup-info">
      <div class="backup-info-icon">ℹ️</div>
      <div>
        <strong>Backup sicuri e persistenti</strong><br>
        I file vengono conservati in
        <code>/media/inventario_casa/db_backups/</code>
        e restano disponibili anche dopo la disinstallazione dell'App.
      </div>
    </div>

    <button type="button"
            class="backup-create-btn"
            onclick="createManualBackup()">
      <span class="backup-create-icon">＋</span>
      <span>
        <strong>Crea backup adesso</strong>
        <small>Salva una copia del database corrente</small>
      </span>
    </button>

    <div class="backup-list-head">
      <strong>🗄️ Backup disponibili</strong>
      <span id="backupCount" class="backup-count"></span>
    </div>

    <div id="backupList"
         class="backup-list">
      Caricamento…
    </div>

    <div class="savebar">
      <button class="secondary"
              onclick="closeBackupDialog()">Chiudi</button>
    </div>
  </div>
</div>



<div id="typeDlg" class="dialogbg">
  <div class="dialog">
    <button type="button" class="dialog-close-btn" onclick="closeTypeDialog()" aria-label="Chiudi" title="Chiudi">×</button>
    <h2 id="typeDlgTitle">🏷️ Tipologia</h2>
    <div class="form">
      <select id="tIcon">
        <option>📦</option><option>📚</option><option>💬</option><option>📰</option>
        <option>💿</option><option>🎮</option><option>🔌</option><option>🛠️</option>
        <option>🧰</option><option>👕</option><option>🧸</option><option>📷</option><option>🏷️</option>
      </select>
      <input id="tIconCustom" placeholder="Oppure incolla un'emoji">
      <input id="tName" class="full" placeholder="Nome tipologia">
      <label class="full">Sottogruppo nell’elenco
        <select id="tSubgroupField"><option value="">Nessuno</option></select>
        <span class="hint">Esempio: per Fumetto scegli Serie. Verrà mostrato Fumetti → Serie → elementi.</span>
      </label>
    </div>
    <br>
    <b>Campi personalizzati</b>
    <div class="hint">Puoi aggiungere, rinominare, ordinare, nascondere e riattivare campi senza perdere i dati esistenti.</div>
    <br>
    <div id="typeFields"></div>
    <button class="secondary" onclick="addFieldRow()">＋ Aggiungi campo</button>
    <div class="savebar">
      <button id="deleteTypeBtn" class="danger dialog-danger" onclick="deleteType()" style="display:none">🗑️ Elimina</button>
      <button class="secondary" onclick="closeTypeDialog()">Annulla</button>
      <button onclick="saveType()">Salva tipologia</button>
    </div>
  </div>
</div>


<div id="viewDlg" class="dialogbg" onclick="if(event.target===this) closeItemPreview()">
  <div class="dialog item-preview-dialog">
    <button type="button" class="dialog-close-btn" onclick="closeItemPreview()" aria-label="Chiudi" title="Chiudi">×</button>
    <h2 id="viewTitle">📦 Dettagli elemento</h2>
    <div id="viewPhotos" class="item-preview-photos"></div>
    <div id="viewDetails" class="item-preview-list"></div>
    <div class="savebar">
      <button class="secondary" onclick="closeItemPreview()">Chiudi</button>
      <button onclick="modifyPreviewItem()">✏️ Modifica</button>
    </div>
  </div>
</div>

<div id="editDlg" class="dialogbg">
  <div class="dialog">
    <button type="button" class="dialog-close-btn" onclick="closeEdit()" aria-label="Chiudi" title="Chiudi">×</button>
    <h2>✏️ Scheda elemento</h2>
    <div class="tabs">
      <button class="tabbtn active" onclick="showTab('edit','general',this)">Generale</button>
      <button class="tabbtn" onclick="showTab('edit','details',this)">Dettagli</button>
      <button class="tabbtn" onclick="showTab('edit','position',this)">Posizione</button>
      <button class="tabbtn" onclick="showTab('edit','photos',this)">Foto</button>
      <button class="tabbtn" onclick="showTab('edit','notes',this)">Note</button>
    </div>

    <div id="edit-general" class="tab active">
      <div class="form">
        <input id="eName" class="full">
        <select id="eType" onchange="renderCustom('edit')"></select>
        <input id="eQty" type="number" min="1">
      </div>
    </div>

    <div id="edit-details" class="tab">
      <div id="customEdit" class="customgrid"></div>
    </div>

    <div id="edit-position" class="tab">
      <div class="form">
        <input id="eEnv" list="envs" placeholder="Ambiente">
        <input id="eFurn" list="furns" placeholder="Mobile/Scaffale">
        <input id="eShelf" list="shelves" placeholder="Ripiano/Cassetto">
        <input id="eCont" list="containers" placeholder="Contenitore">
        <input id="eCode" class="full" placeholder="Codice contenitore">
      </div>
    </div>

    <div id="edit-photos" class="tab">
      <div class="form">
        <input id="photoFile" type="file" accept="image/*">
        <select id="photoProfile">
          <option value="auto">Automatico</option>
          <option value="standard">Standard</option>
          <option value="collectible">Fumetti/collezionabili</option>
        </select>
        <input id="photoLabel" class="full" placeholder="Etichetta foto, es. Fronte, Retro, Costa, Difetto">
        <button onclick="uploadPhoto()">Carica foto</button>
      </div>
      <br>
      <div id="photoGrid" class="photo-grid"></div>
    </div>

    <div id="edit-notes" class="tab">
      <div class="form">
        <textarea id="eDesc" class="full" placeholder="Descrizione"></textarea>
        <textarea id="eNotes" class="full" placeholder="Note"></textarea>
        <input id="eTags" class="full" placeholder="Tag">
      </div>
    </div>

    <div class="savebar">
      <button class="danger dialog-danger" onclick="deleteEditingItem()">🗑️ Elimina</button>
      <button class="secondary" onclick="closeEdit()">Chiudi</button>
      <button onclick="saveItem()">Salva modifiche</button>
    </div>
  </div>
</div>



<div id="barcodeDlg" class="dialogbg" onclick="if(event.target===this) stopBarcodeScan()">
  <div class="dialog barcode-dialog">
    <button type="button" class="dialog-close-btn" onclick="stopBarcodeScan()" aria-label="Chiudi" title="Chiudi">×</button>
    <h2>📷 Scansiona ISBN / EAN</h2>
    <div class="hint">La scansione con fotocamera richiede una connessione HTTPS. Se la scansione live non è disponibile, puoi scattare una foto del codice oppure inserirlo manualmente.</div>
    <br>
    <div class="barcode-reader">
      <video id="barcodeVideo" playsinline muted></video>
      <div class="barcode-guide"></div>
    </div>
    <div id="barcodeStatus" class="barcode-status">Avvio fotocamera…</div>
    <div class="barcode-actions">
      <button id="barcodePhotoBtn" type="button" class="secondary" onclick="chooseBarcodePhoto()">📸 Scatta foto del codice</button>
      <button type="button" class="secondary" onclick="stopBarcodeScan()">Chiudi</button>
    </div>
    <input id="barcodePhotoInput" type="file" accept="image/*" capture="environment" hidden onchange="scanBarcodePhoto(this)">
  </div>
</div>

<div id="photoLightbox" class="photo-lightbox"
     onclick="if(event.target===this) closePhoto()"
     role="dialog" aria-modal="true" aria-label="Anteprima foto">
  <button class="photo-lightbox-close" type="button" onclick="closePhoto()" aria-label="Chiudi">×</button>
  <img id="photoLightboxImg" alt="Foto elemento">
</div>

<script>
let S={types:[],items:[],suggestions:{},counts:{},groups:[],groupItems:{},groupHasMore:{},groupOffsets:{},subgroups:{},subgroupItems:{},subgroupHasMore:{},subgroupOffsets:{},matched_count:0,page_size:50};
let editingItem=null, editingType=null, viewingItem=null;

const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));

async function api(path,opts={}){
  const r=await fetch(path,{headers:{'Content-Type':'application/json'},...opts});
  const d=await r.json().catch(()=>({}));
  if(!r.ok) throw new Error(d.error||'Errore');
  return d;
}


/* v2.2.1 - sincronizzazione colori dal tema Home Assistant.
   Nessun polling: viene eseguita al caricamento e quando la pagina
   torna visibile/in primo piano. */
const homeAssistantThemeVars=[
  '--primary-background-color',
  '--secondary-background-color',
  '--card-background-color',
  '--primary-text-color',
  '--secondary-text-color',
  '--primary-color',
  '--accent-color',
  '--divider-color',
  '--input-fill-color',
  '--lovelace-background',
  '--app-header-background-color',
  '--sidebar-background-color',
  '--ha-font-family-body',
  '--ha-font-family-heading',
  '--paper-font-common-base_-_font-family'
];

function syncHomeAssistantTheme(){
  const root=document.documentElement;
  let found=0;

  try{
    if(window.parent===window){
      root.classList.remove('ha-theme-linked');
      return false;
    }

    const parentRoot=window.parent.document.documentElement;
    const parentStyle=window.parent.getComputedStyle(parentRoot);

    for(const name of homeAssistantThemeVars){
      const value=parentStyle.getPropertyValue(name).trim();
      if(value){
        root.style.setProperty(name,value);
        found++;
      }
    }

    root.classList.toggle('ha-theme-linked',found>=3);
    return found>=3;
  }catch(e){
    root.classList.remove('ha-theme-linked');
    return false;
  }
}

function updateSearchClear(){
  const input=$('search');
  const clear=$('searchClear');
  if(!input || !clear)return;
  clear.classList.toggle('show',input.value.length>0);
}

async function clearSearch(){
  const input=$('search');
  if(!input)return;
  input.value='';
  updateSearchClear();
  input.focus();
  await load();
}


function supportsSpeech(){
  return !!(window.SpeechRecognition || window.webkitSpeechRecognition);
}

function attachVoiceButton(input){
  if(!input || input.dataset.voiceReady==='1') return;
  input.dataset.voiceReady='1';

  const wrap=document.createElement('div');
  wrap.className='voicewrap'+(input.tagName==='TEXTAREA'?' textarea':'');
  input.parentNode.insertBefore(wrap,input);
  wrap.appendChild(input);

  const btn=document.createElement('button');
  btn.type='button';
  btn.className='micbtn';
  btn.textContent='🎤';
  btn.title='Dettatura vocale';
  wrap.appendChild(btn);

  if(!supportsSpeech()){
    btn.disabled=true;
    btn.title='Dettatura vocale non supportata da questo browser';
    return;
  }

  btn.onclick=()=>{
    const SR=window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec=new SR();
    rec.lang='it-IT';
    rec.interimResults=false;
    rec.continuous=false;

    btn.classList.add('listening');
    btn.textContent='🔴';

    rec.onresult=(e)=>{
      const spoken=e.results?.[0]?.[0]?.transcript || '';
      if(!spoken) return;
      const start=input.selectionStart ?? input.value.length;
      const end=input.selectionEnd ?? input.value.length;
      const before=input.value.slice(0,start);
      const after=input.value.slice(end);
      const join=(before && !/\s$/.test(before))?' ':'';
      input.value=before+join+spoken+after;
      input.dispatchEvent(new Event('input',{bubbles:true}));
      input.focus();
    };
    rec.onerror=()=>{};
    rec.onend=()=>{
      btn.classList.remove('listening');
      btn.textContent='🎤';
    };
    rec.start();
  };
}

function enableVoiceInputs(scope=document){
  const selectors=[
    'input[type="text"]',
    'input:not([type])',
    'textarea'
  ];
  scope.querySelectorAll(selectors.join(',')).forEach(el=>{
    const allowedStatic=['aName','aDesc','aNotes','aTags','eName','eDesc','eNotes','eTags'];
    const isCustom=!!el.dataset.cfid;
    const isTypeEditor=!!el.closest('.fieldrow') && el.classList.contains('flabel');
    if(!(allowedStatic.includes(el.id) || isCustom || isTypeEditor)) return;
    if(el.closest('.fieldrow') && (el.classList.contains('fopts') || el.classList.contains('fplaceholder'))) return;
    attachVoiceButton(el);
  });
}

function currentItemsGrouping(){
  const saved=localStorage.getItem('inventario_items_group_by')||'type';
  return ['type','environment','none'].includes(saved)?saved:'type';
}

async function changeItemsGrouping(value){
  const grouping=['type','environment','none'].includes(value)?value:'type';
  localStorage.setItem('inventario_items_group_by',grouping);
  await loadInventoryGroups();
  renderInventory();
}

function groupStorageKey(grouping,key){
  return 'inventario_group_collapsed_'+grouping+'_'+String(key||'').toLowerCase();
}

function isGroupCollapsed(grouping,key){
  const saved=localStorage.getItem(groupStorageKey(grouping,key));
  // v2: i gruppi nuovi partono chiusi, così non carichiamo centinaia di righe inutilmente.
  return saved===null ? true : saved==='1';
}

async function toggleItemGroup(btn){
  const group=btn.closest('.item-group');
  if(!group)return;
  const grouping=group.dataset.grouping;
  const key=group.dataset.groupKey;
  const collapsed=group.classList.toggle('collapsed');
  localStorage.setItem(groupStorageKey(grouping,key),collapsed?'1':'0');
  if(!collapsed){
    if(grouping==='type'){
      await loadSubgroups(key);
      if(S.subgroups[key]===null && !(S.groupItems[key]||[]).length) await loadGroupPage(key,true);
    }else if(!(S.groupItems[key]||[]).length){
      await loadGroupPage(key,true);
    }
  }
}

function setNewItemCollapsed(collapsed){
  const panel=$('newItemPanel');
  const chevron=$('newItemChevron');
  if(!panel)return;
  panel.classList.toggle('collapsed',collapsed);
  const head=panel.querySelector('.new-item-head');
  if(head) head.setAttribute('aria-expanded',collapsed?'false':'true');
  if(chevron) chevron.textContent=collapsed?'▾':'▴';
}

function toggleNewItemPanel(){
  const panel=$('newItemPanel');
  if(!panel)return;
  setNewItemCollapsed(!panel.classList.contains('collapsed'));
}

async function loadInventoryGroups(){
  const q=$('search').value.trim();
  const grouping=currentItemsGrouping();
  const params=new URLSearchParams({group_by:grouping});
  if(q)params.set('q',q);
  const data=await api('api/inventory-groups?'+params.toString());
  S.groups=data.groups||[];
  S.matched_count=Number(data.matched_count||0);
  S.page_size=Number(data.page_size||50);
  S.groupItems={};
  S.groupHasMore={};
  S.groupOffsets={};
  S.subgroups={};
  S.subgroupItems={};
  S.subgroupHasMore={};
  S.subgroupOffsets={};
  S.items=[];
}

function mergeLoadedItems(items){
  const byId=new Map((S.items||[]).map(i=>[i.id,i]));
  for(const item of (items||[]))byId.set(item.id,item);
  S.items=[...byId.values()];
}

function rebuildVisibleItems(){
  const byId=new Map();

  for(const rows of Object.values(S.groupItems||{})){
    for(const item of (rows||[])) byId.set(item.id,item);
  }

  for(const rows of Object.values(S.subgroupItems||{})){
    for(const item of (rows||[])) byId.set(item.id,item);
  }

  S.items=[...byId.values()];
}

async function loadGroupPage(key,reset=false,requestedOffset=null){
  const grouping=currentItemsGrouping();
  const pageSize=S.page_size||50;
  const current=Number(S.groupOffsets?.[key]||0);

  const offset=requestedOffset===null
    ? (reset ? 0 : current+pageSize)
    : Math.max(0,Number(requestedOffset)||0);

  const q=$('search').value.trim();

  const params=new URLSearchParams({
    group_by:grouping,
    group_key:key,
    offset:String(offset)
  });

  if(q)params.set('q',q);

  const data=await api('api/inventory-items?'+params.toString());

  S.groupItems[key]=data.items||[];
  S.groupOffsets[key]=Number(data.offset??offset);
  S.groupHasMore[key]=!!data.has_more;

  rebuildVisibleItems();
  renderInventory();
}

async function loadMoreGroup(key,event){
  event?.stopPropagation?.();
  await loadGroupPage(key,false);
}

async function loadPreviousGroup(key,event){
  event?.stopPropagation?.();
  const pageSize=S.page_size||50;
  const current=Number(S.groupOffsets?.[key]||0);
  await loadGroupPage(key,false,Math.max(0,current-pageSize));
}

async function loadFirstGroup(key,event){
  event?.stopPropagation?.();
  await loadGroupPage(key,false,0);
}

async function loadLastGroup(key,total,event){
  event?.stopPropagation?.();
  const pageSize=S.page_size||50;
  const offset=Math.floor(Math.max(0,Number(total||0)-1)/pageSize)*pageSize;
  await loadGroupPage(key,false,offset);
}

async function load(){
  const q=$('search').value.trim();
  const params=new URLSearchParams();
  if(q)params.set('q',q);
  S=await api('api/bootstrap?'+params.toString());
  S.groups=[];
  S.groupItems={};
  S.groupHasMore={};
  S.groupOffsets={};
  S.subgroups={};
  S.subgroupItems={};
  S.subgroupHasMore={};
  S.subgroupOffsets={};
  S.items=[];
  S.page_size=50;
  await loadInventoryGroups();
  render();
}

function showTab(prefix,name,btn){
  document.querySelectorAll(`[id^="${prefix}-"]`).forEach(x=>x.classList.remove('active'));
  $(prefix+'-'+name).classList.add('active');
  btn.parentElement.querySelectorAll('.tabbtn').forEach(x=>x.classList.remove('active'));
  btn.classList.add('active');
}

function typeById(id){return S.types.find(t=>String(t.id)===String(id));}
function dl(id,arr){$(id).innerHTML=(arr||[]).map(x=>`<option value="${esc(x)}">`).join('');}

function renderTypes(){
  const box=$('typeList');
  if(!box)return;
  const q=($('typeSearch')?.value||'').trim().toLowerCase();
  const rows=S.types.filter(t=>!q || t.name.toLowerCase().includes(q));
  box.innerHTML=rows.length ? rows.map(t=>{
    const count=(t.fields||[]).filter(f=>f.active).length;
    return `<div class="typecard" onclick="editType(${t.id})" title="Apri ${esc(t.name)}">
      <div class="typecard-main">
        <span class="typeicon">${esc(t.icon)}</span>
        <span class="typename">${esc(t.name)}</span>
      </div>
      <span class="typecount">${count} ${count===1?'campo':'campi'}</span>
    </div>`;
  }).join('') : '<div class="empty">Nessuna tipologia trovata.</div>';
}

function setTypePanelCollapsed(collapsed){
  const p=$('typePanel');
  const b=$('typeCollapseBtn');
  if(!p||!b)return;
  p.classList.toggle('collapsed',collapsed);
  b.textContent=collapsed?'▸':'▾';
  b.title=collapsed?'Espandi tipologie':'Riduci tipologie';
  localStorage.setItem('inventario_type_panel_collapsed',collapsed?'1':'0');
}
function toggleTypePanel(){
  setTypePanelCollapsed(!$('typePanel').classList.contains('collapsed'));
}

function render(){
  $('countItems').textContent=S.counts.items;
  $('countEnv').textContent=S.counts.environments;
  $('countTypes').textContent=S.counts.types;

  const grouping=currentItemsGrouping();
  if($('itemsGroupBy')) $('itemsGroupBy').value=grouping;
  const matched=Number(S.matched_count||0);
  if($('itemsListInfo')){
    $('itemsListInfo').textContent=matched ? `${matched} ${matched===1?'elemento':'elementi'} totali` : '';
  }

  const typeOpts=S.types.map(t=>`<option value="${t.id}">${esc(t.icon)} ${esc(t.name)}</option>`).join('');
  $('aType').innerHTML=typeOpts;
  $('eType').innerHTML=typeOpts;

  dl('envs',S.suggestions.environment);
  dl('furns',S.suggestions.furniture);
  dl('shelves',S.suggestions.shelf);
  dl('containers',S.suggestions.container);

  renderCustom('add');
  enableVoiceInputs(document);

  renderTypes();

  renderInventory();

  $('itemsTitle').textContent=$('search').value.trim()?'🔎 Risultati':'📦 Cosa possiedo';
}


function renderItemRow(i){
  return `<button type="button" class="item item-row" onclick="showItemPreview(${i.id})" aria-label="Apri ${esc(i.name)}">
    <span class="itemname">${esc(i.type_icon||'📦')} ${esc(i.name)}${i.quantity>1?' × '+i.quantity:''}</span>
    <span class="item-chevron">›</span>
  </button>`;
}

function renderLoadMore(key,loaded,total){
  if(!loaded)return '';

  const offset=Number(S.groupOffsets?.[key]||0);
  const first=offset+1;
  const last=Math.min(offset+loaded,total);

  const hasPrev=offset>0;
  const hasNext=!!S.groupHasMore[key];

  return `<div class="inventory-pager">
    ${hasPrev ? `
      <button type="button" class="secondary" onclick="loadFirstGroup('${esc(key)}',event)">⏮ Primi</button>
      <button type="button" class="secondary" onclick="loadPreviousGroup('${esc(key)}',event)">‹ Precedenti</button>
    ` : ''}

    <span class="hint"><strong>${first}–${last}</strong> di ${total}</span>

    ${hasNext ? `
      <button type="button" class="secondary" onclick="loadMoreGroup('${esc(key)}',event)">Successivi ›</button>
      <button type="button" class="secondary" onclick="loadLastGroup('${esc(key)}',${total},event)">Ultimi ⏭</button>
    ` : ''}
  </div>`;
}

function subgroupCacheKey(typeKey,subKey){return String(typeKey)+'::'+String(subKey);}
function subgroupStorageKey(typeKey,subKey){return 'inventario_subgroup_collapsed_'+typeKey+'_'+String(subKey).toLowerCase();}
function isSubgroupCollapsed(typeKey,subKey){const v=localStorage.getItem(subgroupStorageKey(typeKey,subKey));return v===null?true:v==='1';}
async function loadSubgroups(typeKey){
  if(S.subgroups[typeKey])return;
  const q=$('search').value.trim(); const p=new URLSearchParams({type_id:String(typeKey)}); if(q)p.set('q',q);
  const d=await api('api/inventory-subgroups?'+p.toString());
  S.subgroups[typeKey]=d.enabled?(d.subgroups||[]):null;
  renderInventory();
}
async function toggleSubgroup(btn){
  const el=btn.closest('.item-subgroup'); if(!el)return;
  const tk=el.dataset.typeKey, sk=el.dataset.subgroupKey, collapsed=el.classList.toggle('collapsed');
  localStorage.setItem(subgroupStorageKey(tk,sk),collapsed?'1':'0');
  const ck=subgroupCacheKey(tk,sk);
  if(!collapsed && !(S.subgroupItems[ck]||[]).length) await loadSubgroupPage(tk,sk,true);
}
async function loadSubgroupPage(typeKey,subKey,reset=false,requestedOffset=null){
  const ck=subgroupCacheKey(typeKey,subKey);
  const pageSize=S.page_size||50;
  const current=Number(S.subgroupOffsets?.[ck]||0);

  const offset=requestedOffset===null
    ? (reset ? 0 : current+pageSize)
    : Math.max(0,Number(requestedOffset)||0);

  const q=$('search').value.trim();

  const p=new URLSearchParams({
    type_id:String(typeKey),
    subgroup_key:String(subKey),
    offset:String(offset)
  });

  if(q)p.set('q',q);

  const d=await api('api/inventory-subgroup-items?'+p.toString());

  S.subgroupItems[ck]=d.items||[];
  S.subgroupOffsets[ck]=Number(d.offset??offset);
  S.subgroupHasMore[ck]=!!d.has_more;

  rebuildVisibleItems();
  renderInventory();
}

async function loadMoreSubgroup(typeKey,subKey,event){
  event?.stopPropagation?.();
  await loadSubgroupPage(typeKey,subKey,false);
}

async function loadPreviousSubgroup(typeKey,subKey,event){
  event?.stopPropagation?.();

  const ck=subgroupCacheKey(typeKey,subKey);
  const pageSize=S.page_size||50;
  const current=Number(S.subgroupOffsets?.[ck]||0);

  await loadSubgroupPage(
    typeKey,
    subKey,
    false,
    Math.max(0,current-pageSize)
  );
}

async function loadFirstSubgroup(typeKey,subKey,event){
  event?.stopPropagation?.();
  await loadSubgroupPage(typeKey,subKey,false,0);
}

async function loadLastSubgroup(typeKey,subKey,total,event){
  event?.stopPropagation?.();

  const pageSize=S.page_size||50;
  const offset=Math.floor(
    Math.max(0,Number(total||0)-1)/pageSize
  )*pageSize;

  await loadSubgroupPage(typeKey,subKey,false,offset);
}

function renderSubgroupLoadMore(typeKey,subKey,loaded,total){
  if(!loaded)return '';

  const ck=subgroupCacheKey(typeKey,subKey);
  const offset=Number(S.subgroupOffsets?.[ck]||0);

  const first=offset+1;
  const last=Math.min(offset+loaded,total);

  const hasPrev=offset>0;
  const hasNext=!!S.subgroupHasMore[ck];

  return `<div class="inventory-pager">
    ${hasPrev ? `
      <button type="button" class="secondary" onclick="loadFirstSubgroup('${esc(typeKey)}','${esc(subKey)}',event)">⏮ Primi</button>
      <button type="button" class="secondary" onclick="loadPreviousSubgroup('${esc(typeKey)}','${esc(subKey)}',event)">‹ Precedenti</button>
    ` : ''}

    <span class="hint"><strong>${first}–${last}</strong> di ${total}</span>

    ${hasNext ? `
      <button type="button" class="secondary" onclick="loadMoreSubgroup('${esc(typeKey)}','${esc(subKey)}',event)">Successivi ›</button>
      <button type="button" class="secondary" onclick="loadLastSubgroup('${esc(typeKey)}','${esc(subKey)}',${total},event)">Ultimi ⏭</button>
    ` : ''}
  </div>`;
}

function renderTypeSubgroups(typeKey){
  const subs=S.subgroups[typeKey];
  if(subs===undefined){setTimeout(()=>loadSubgroups(typeKey),0);return '<div class="inventory-loader">Carico i sottogruppi…</div>';}
  if(subs===null)return null;
  if(!subs.length)return '<div class="empty">Nessun elemento trovato.</div>';
  return subs.map(g=>{const sk=String(g.subgroup_key),ck=subgroupCacheKey(typeKey,sk),items=S.subgroupItems[ck]||[],total=Number(g.item_count||0),collapsed=isSubgroupCollapsed(typeKey,sk);
    const body=items.length?items.map(renderItemRow).join('')+renderSubgroupLoadMore(typeKey,sk,items.length,total):'<div class="inventory-loader">Apri il sottogruppo per caricare gli elementi.</div>';
    if(!collapsed && !items.length)setTimeout(()=>loadSubgroupPage(typeKey,sk,true),0);
    return `<section class="item-subgroup${collapsed?' collapsed':''}" data-type-key="${esc(typeKey)}" data-subgroup-key="${esc(sk)}"><button type="button" class="item-subgroup-head" onclick="toggleSubgroup(this)"><span class="item-subgroup-title">↳ ${esc(g.label)}</span><span class="item-group-side"><span class="item-group-count">${total}</span><span class="item-subgroup-arrow">⌄</span></span></button><div class="item-subgroup-body">${body}</div></section>`;
  }).join('');
}

function renderInventory(){
  const box=$('items');
  if(!box)return;
  const grouping=currentItemsGrouping();
  const groups=S.groups||[];

  if(!groups.length){
    box.innerHTML='<div class="empty">Nessun elemento trovato.</div>';
    return;
  }

  if(grouping==='none'){
    const g=groups[0];
    const key=String(g.group_key||'all');
    const items=S.groupItems[key]||[];
    box.innerHTML=`
      <div class="flat-items-body">
        ${items.length?items.map(renderItemRow).join(''):'<div class="inventory-loader">Caricamento elementi…</div>'}
        ${renderLoadMore(key,items.length,Number(g.item_count||0))}
      </div>`;
    if(!items.length)loadGroupPage(key,true);
    return;
  }

  box.innerHTML=groups.map(g=>{
    const key=String(g.group_key);
    const collapsed=isGroupCollapsed(grouping,key);
    const items=S.groupItems[key]||[];
    const total=Number(g.item_count||0);
    let body;
    if(grouping==='type'){
      const subhtml=renderTypeSubgroups(key);
      if(subhtml!==null) body=subhtml;
      else body=items.length ? `${items.map(renderItemRow).join('')}${renderLoadMore(key,items.length,total)}` : '<div class="inventory-loader">Apri il gruppo per caricare gli elementi.</div>';
    }else{
      body=items.length ? `${items.map(renderItemRow).join('')}${renderLoadMore(key,items.length,total)}` : '<div class="inventory-loader">Apri il gruppo per caricare gli elementi.</div>';
    }
    return `
      <section class="item-group${collapsed?' collapsed':''}" data-grouping="${grouping}" data-group-key="${esc(key)}">
        <button type="button" class="item-group-head" onclick="toggleItemGroup(this)">
          <span class="item-group-title"><span>${esc(g.icon||'📦')}</span><span>${esc(g.label||'Gruppo')}</span></span>
          <span class="item-group-side">
            <span class="item-group-count">${total}</span>
            <span class="item-group-arrow">⌄</span>
          </span>
        </button>
        <div class="item-group-body">${body}</div>
      </section>`;
  }).join('');

  // Ripristina solo i gruppi che l'utente aveva lasciato aperti, 50 righe per gruppo.
  for(const g of groups){
    const key=String(g.group_key);
    if(!isGroupCollapsed(grouping,key) && grouping!=='type' && !(S.groupItems[key]||[]).length){
      loadGroupPage(key,true);
    }
  }
}

function renderCustom(mode,values={}){
  const typeId=$(mode==='add'?'aType':'eType').value;
  const t=typeById(typeId);
  const box=$(mode==='add'?'customAdd':'customEdit');
  if(!t){box.innerHTML='<div class="empty">Nessun campo.</div>';return;}

  const fields=(t.fields||[]).filter(f=>f.active);
  if(!fields.length){box.innerHTML='<div class="empty">Questa tipologia non ha campi personalizzati.</div>';return;}

  box.innerHTML=fields.map(f=>{
    const v=values[String(f.id)]??'';
    const req=f.required?' *':'';
    const ph=esc(f.placeholder||'');
    let control='';

    if(f.field_type==='textarea'){
      control=`<textarea data-cfid="${f.id}" placeholder="${ph}">${esc(v)}</textarea>`;
    }else if(f.field_type==='select'){
      const opts=(f.options||'').split(',').map(x=>x.trim()).filter(Boolean);
      control=`<select data-cfid="${f.id}"><option value=""></option>${opts.map(o=>`<option value="${esc(o)}"${String(v)===o?' selected':''}>${esc(o)}</option>`).join('')}</select>${ph?`<span class="hint">${ph}</span>`:''}`;
    }else if(f.field_type==='checkbox'){
      control=`<select data-cfid="${f.id}"><option value=""></option><option value="1"${String(v)==='1'?' selected':''}>Sì</option><option value="0"${String(v)==='0'?' selected':''}>No</option></select>`;
    }else{
      const typ=f.field_type==='number'?'number':f.field_type==='date'?'date':'text';
      control=`<input type="${typ}" data-cfid="${f.id}" value="${esc(v)}" placeholder="${ph}">`;
    }

    const filled=String(v).trim()!=='' ? '<span class="custom-field-filled">✓</span>' : '';
    const normalizedLabel=String(f.label||'').toLowerCase().replace(/\s+/g,' ').trim();
    const isBookCode=normalizedLabel==='isbn' || normalizedLabel==='isbn / ean' || normalizedLabel==='isbn/ean';
    const lookup=isBookCode ? `
      <div class="book-lookup-row">
        <button type="button" class="secondary small scan-code-btn" onclick="startBarcodeScan('${mode}',${f.id},this)">📷 Scansiona codice</button>
        <button type="button" class="secondary small" onclick="lookupBookData('${mode}',${f.id},this)">🔎 Cerca dati</button>
        <span class="book-lookup-status"></span>
      </div>` : '';
    return `
      <div class="custom-field-accordion">
        <button type="button" class="custom-field-title" onclick="toggleCustomField(this)">
          <span>${esc(f.label)+req}</span>
          <span class="custom-field-title-right">${filled}<span class="custom-field-arrow">⌄</span></span>
        </button>
        <div class="custom-field-body">
          ${control}
          ${lookup}
        </div>
      </div>`;
  }).join('');

  enableVoiceInputs(box);
  updateCameraAvailability();
}

function toggleCustomField(btn){
  const row=btn.closest('.custom-field-accordion');
  if(!row)return;
  const box=row.parentElement;
  const already=row.classList.contains('open');

  box.querySelectorAll('.custom-field-accordion.open').forEach(x=>{
    if(x!==row)x.classList.remove('open');
  });

  row.classList.toggle('open',!already);

  if(!already){
    const el=row.querySelector('input,select,textarea');
    if(el)setTimeout(()=>el.focus(),60);
  }
}


function findCustomInputByLabel(mode,labelNames){
  const typeId=$(mode==='add'?'aType':'eType').value;
  const t=typeById(typeId);
  if(!t)return null;
  const wanted=labelNames.map(x=>x.toLowerCase());
  const f=(t.fields||[]).find(x=>wanted.includes(String(x.label||'').toLowerCase()));
  if(!f)return null;
  return document.querySelector(`#${mode==='add'?'customAdd':'customEdit'} [data-cfid="${f.id}"]`);
}

function setIfEmpty(el,value){
  if(!el || !value || String(el.value||'').trim()!=='')return false;
  el.value=value;
  el.dispatchEvent(new Event('input',{bubbles:true}));
  el.dispatchEvent(new Event('change',{bubbles:true}));
  return true;
}


let barcodeStream=null;
let barcodeDetector=null;
let barcodeScanTimer=null;
let barcodeTarget=null;
let barcodeBusy=false;
let barcodeFallbackMode=false;

function cameraSecureContextAvailable(){
  return !!(window.isSecureContext &&
            navigator.mediaDevices?.getUserMedia);
}

function updateCameraAvailability(){
  const available=cameraSecureContextAvailable();

  document.querySelectorAll('.scan-code-btn').forEach(btn=>{
    btn.disabled=!available;
    btn.title=available
      ? 'Scansiona codice con la fotocamera'
      : 'Fotocamera non disponibile: è richiesta una connessione HTTPS';
  });
}

function normalizeBarcodeValue(raw){
  return String(raw||'').trim().replace(/[^0-9Xx]/g,'').toUpperCase();
}

function barcodeValueLooksUseful(code){
  return [8,10,12,13].includes(code.length);
}

async function makeBarcodeDetector(){
  if(!('BarcodeDetector' in window))return null;
  let formats=['ean_13','ean_8','upc_a','upc_e','code_128'];
  try{
    if(typeof BarcodeDetector.getSupportedFormats==='function'){
      const supported=await BarcodeDetector.getSupportedFormats();
      const filtered=formats.filter(x=>supported.includes(x));
      if(filtered.length)formats=filtered;
    }
    return new BarcodeDetector({formats});
  }catch(e){
    return null;
  }
}

function applyScannedBarcode(raw){
  if(!barcodeTarget)return false;
  const code=normalizeBarcodeValue(raw);
  if(!barcodeValueLooksUseful(code))return false;
  const {mode,fieldId}=barcodeTarget;
  const box=$(mode==='add'?'customAdd':'customEdit');
  const input=box?.querySelector(`[data-cfid="${fieldId}"]`);
  if(!input)return false;
  input.value=code;
  input.dispatchEvent(new Event('input',{bubbles:true}));
  input.dispatchEvent(new Event('change',{bubbles:true}));
  const status=barcodeTarget.statusEl;
  if(status)status.textContent='✓ Codice rilevato: '+code+' — ora puoi premere Cerca dati.';
  stopBarcodeScan(false);
  return true;
}

async function decodeBarcodeOnServer(blob, filename='frame.jpg'){
  const fd=new FormData();
  fd.append('image',blob,filename);
  const resp=await fetch('api/decode-barcode',{method:'POST',body:fd});
  let data={};
  try{data=await resp.json();}catch(e){}
  if(!resp.ok)throw new Error(data.error||'Errore durante la lettura del barcode.');
  for(const b of (data.barcodes||[])){
    if(applyScannedBarcode(b.code||b.raw))return true;
  }
  return false;
}

async function startBarcodeScan(mode,fieldId,btn){
  barcodeTarget={mode,fieldId,statusEl:btn.parentElement.querySelector('.book-lookup-status')};

  // v2.3.5 - la fotocamera viene usata solo in un contesto sicuro.
  // In HTTP l'inserimento manuale e il caricamento di file restano disponibili.
  const canLiveCamera=cameraSecureContextAvailable();
  if(!canLiveCamera){
    const targetStatus=barcodeTarget.statusEl;
    if(targetStatus){
      targetStatus.textContent='🔒 Fotocamera non disponibile: è richiesta una connessione HTTPS. Inserisci il codice manualmente.';
    }
    barcodeTarget=null;
    return;
  }

  const dlg=$('barcodeDlg'), video=$('barcodeVideo'), status=$('barcodeStatus');
  dlg.classList.add('show');
  status.textContent='Avvio fotocamera…';
  try{
    barcodeDetector=await makeBarcodeDetector();
    barcodeFallbackMode=!barcodeDetector;
    barcodeStream=await navigator.mediaDevices.getUserMedia({
      video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}},audio:false
    });
    video.srcObject=barcodeStream;
    await video.play();
    status.textContent=barcodeFallbackMode
      ? 'Inquadra il codice nel riquadro verde. Modalità compatibile attiva.'
      : 'Inquadra il codice a barre dentro il riquadro verde.';
    barcodeScanLoop();
  }catch(e){
    // Se il browser espone getUserMedia ma poi lo blocca (Ingress/WebView,
    // permessi o policy), manteniamo il fallback foto sempre disponibile.
    status.textContent='La fotocamera live non è disponibile. Premi “📸 Scatta foto del codice” oppure inserisci il codice manualmente.';
    const photoBtn=$('barcodePhotoBtn');
    if(photoBtn) photoBtn.focus();
  }
}

async function decodeCurrentVideoFrame(){
  const video=$('barcodeVideo');
  if(!video || video.readyState<2 || !video.videoWidth || !video.videoHeight)return false;
  const maxW=960;
  const scale=Math.min(1,maxW/video.videoWidth);
  const canvas=document.createElement('canvas');
  canvas.width=Math.max(1,Math.round(video.videoWidth*scale));
  canvas.height=Math.max(1,Math.round(video.videoHeight*scale));
  const ctx=canvas.getContext('2d',{alpha:false});
  ctx.drawImage(video,0,0,canvas.width,canvas.height);
  const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',0.72));
  if(!blob)return false;
  return decodeBarcodeOnServer(blob,'camera.jpg');
}

async function barcodeScanLoop(){
  if(!barcodeStream)return;
  const video=$('barcodeVideo');
  if(!barcodeBusy && video.readyState>=2){
    barcodeBusy=true;
    try{
      if(barcodeDetector){
        const found=await barcodeDetector.detect(video);
        if(found?.length){
          for(const b of found){if(applyScannedBarcode(b.rawValue))return;}
        }
      }else{
        if(await decodeCurrentVideoFrame())return;
      }
    }catch(e){}
    finally{barcodeBusy=false;}
  }
  barcodeScanTimer=setTimeout(barcodeScanLoop,barcodeDetector?180:500);
}

function stopBarcodeScan(clearTarget=true){
  if(barcodeScanTimer){clearTimeout(barcodeScanTimer);barcodeScanTimer=null;}
  if(barcodeStream){barcodeStream.getTracks().forEach(t=>t.stop());barcodeStream=null;}
  const video=$('barcodeVideo');
  if(video){video.pause();video.srcObject=null;}
  $('barcodeDlg')?.classList.remove('show');
  barcodeBusy=false;
  barcodeFallbackMode=false;
  if(clearTarget)barcodeTarget=null;
}

function chooseBarcodePhoto(){
  if(!cameraSecureContextAvailable()){
    const status=$('barcodeStatus');
    if(status){
      status.textContent='🔒 Fotocamera non disponibile: è richiesta una connessione HTTPS.';
    }
    return;
  }

  if(barcodeStream){barcodeStream.getTracks().forEach(t=>t.stop());barcodeStream=null;}
  const inp=$('barcodePhotoInput');
  if(inp){inp.value='';inp.click();}
}

async function scanBarcodePhoto(input){
  const status=$('barcodeStatus');
  const targetStatus=barcodeTarget?.statusEl;
  const file=input.files?.[0];
  if(!file){
    if(targetStatus) targetStatus.textContent='Scansione annullata. Puoi inserire il codice manualmente.';
    return;
  }
  if(!$('barcodeDlg').classList.contains('show')) $('barcodeDlg').classList.add('show');
  status.textContent='Analizzo la foto del codice…';
  try{
    const detector=await makeBarcodeDetector();
    if(detector && 'createImageBitmap' in window){
      try{
        const bitmap=await createImageBitmap(file);
        const found=await detector.detect(bitmap);
        bitmap.close?.();
        for(const b of (found||[])){if(applyScannedBarcode(b.rawValue))return;}
      }catch(e){}
    }
    if(await decodeBarcodeOnServer(file,file.name||'barcode.jpg'))return;
    status.textContent='Nessun ISBN/EAN rilevato nella foto. Riprova avvicinandoti al codice oppure inseriscilo manualmente.';
  }catch(e){
    status.textContent=e.message||'Impossibile leggere il codice dalla foto.';
  }
}

async function lookupBookData(mode,fieldId,btn){
  const box=$(mode==='add'?'customAdd':'customEdit');
  const codeEl=box.querySelector(`[data-cfid="${fieldId}"]`);
  const status=btn.parentElement.querySelector('.book-lookup-status');
  const code=(codeEl?.value||'').trim();
  if(!code){alert('Inserisci prima il codice ISBN / EAN.');codeEl?.focus();return;}

  const oldText=btn.textContent;
  btn.disabled=true;
  btn.textContent='⏳ Ricerca...';
  status.textContent='';
  try{
    const data=await api('api/lookup-book?code='+encodeURIComponent(code));
    const lines=[];
    if(data.title)lines.push('Titolo: '+data.title);
    if((data.authors||[]).length)lines.push('Autore: '+data.authors.join(', '));
    if(data.publisher)lines.push('Editore: '+data.publisher);
    if(data.publish_date)lines.push('Data: '+data.publish_date);
    if(data.year)lines.push('Anno: '+data.year);
    lines.push('Codice: '+data.code);

    const ok=confirm('Dati trovati su '+data.source+':\n\n'+lines.join('\n')+'\n\nCompilare i campi attualmente vuoti?\nI campi già compilati NON verranno sovrascritti.');
    if(!ok){status.textContent='Dati trovati, non applicati.';return;}

    let applied=0;
    const nameEl=$(mode==='add'?'aName':'eName');
    if(setIfEmpty(nameEl,data.title))applied++;
    if(setIfEmpty(findCustomInputByLabel(mode,['Autore']), (data.authors||[]).join(', ')))applied++;
    if(setIfEmpty(findCustomInputByLabel(mode,['Editore']),data.publisher))applied++;
    if(setIfEmpty(findCustomInputByLabel(mode,['Anno']),data.year))applied++;
    if(setIfEmpty(codeEl,data.code))applied++;

    status.textContent=applied ? `✓ Compilati ${applied} campi vuoti` : 'Nessun campo vuoto da compilare.';
  }catch(e){
    alert(e.message);
    status.textContent='Ricerca non riuscita.';
  }finally{
    btn.disabled=false;
    btn.textContent=oldText;
  }
}


function collectCustom(boxId){
  const out={};
  document.querySelectorAll('#'+boxId+' [data-cfid]').forEach(el=>out[String(el.dataset.cfid)]=el.value);
  return out;
}

async function createItem(){
  try{
    const data=await api('api/items',{method:'POST',body:JSON.stringify({
      name:$('aName').value,
      item_type_id:$('aType').value||null,
      quantity:$('aQty').value,
      environment:$('aEnv').value,
      furniture:$('aFurn').value,
      shelf:$('aShelf').value,
      container_name:$('aCont').value,
      container_code:$('aCode').value,
      description:$('aDesc').value,
      notes:$('aNotes').value,
      tags:$('aTags').value,
      custom_values:collectCustom('customAdd')
    })});
    ['aName','aEnv','aFurn','aShelf','aCont','aCode','aDesc','aNotes','aTags'].forEach(id=>$(id).value='');
    $('aQty').value=1;
    await load();
  setNewItemCollapsed(true);
    editItem(data.id);
    const photoBtn=[...document.querySelectorAll('#editDlg .tabbtn')].find(b=>b.textContent.trim()==='Foto');
    if(photoBtn) photoBtn.click();
  }catch(e){alert(e.message);}
}

function addPreviewRow(rows,label,value){
  if(value===null || value===undefined || String(value).trim()==='') return;
  rows.push(`<div class="item-preview-row"><div class="item-preview-label">${esc(label)}</div><div class="item-preview-value">${esc(value)}</div></div>`);
}

async function showItemPreview(id){
  let i=S.items.find(x=>x.id===id);
  if(!i){
    try{i=await api('api/items/'+id); mergeLoadedItems([i]);}
    catch(e){alert(e.message);return;}
  }
  viewingItem=id;
  const t=typeById(i.item_type_id);
  const rows=[];
  addPreviewRow(rows,'Tipologia',`${t?.icon||i.type_icon||'📦'} ${t?.name||''}`.trim());
  if(Number(i.quantity||1)>1) addPreviewRow(rows,'Quantità',i.quantity);
  const values=i.custom_values||{};
  for(const f of (t?.fields||[])){
    if(!f.active) continue;
    const v=values[String(f.id)] ?? values[f.id];
    addPreviewRow(rows,f.label,v);
  }
  addPreviewRow(rows,'Ambiente',i.environment);
  addPreviewRow(rows,'Mobile / Scaffale',i.furniture);
  addPreviewRow(rows,'Ripiano / Cassetto',i.shelf);
  addPreviewRow(rows,'Contenitore',i.container_name);
  addPreviewRow(rows,'Codice contenitore',i.container_code);
  addPreviewRow(rows,'Descrizione',i.description);
  addPreviewRow(rows,'Tag',i.tags);
  addPreviewRow(rows,'Note',i.notes);
  $('viewTitle').textContent=`${i.type_icon||t?.icon||'📦'} ${i.name||'Dettagli elemento'}`;
  const photos=i.photos||[];
  if(photos.length){
    const visible=photos.slice(0,3);
    $('viewPhotos').innerHTML=`<div class="item-preview-photo-title">📷 Foto</div>
      <div class="item-preview-photo-grid">${visible.map(p=>`
        <div class="item-preview-photo">
          <button type="button" onclick="openPhoto('${p.filename}')" aria-label="Apri foto">
            <img src="files/${encodeURIComponent(p.thumb_filename)}" alt="${esc(p.label||i.name||'Foto elemento')}">
          </button>
          ${p.label?`<div class="item-preview-photo-label">${esc(p.label)}</div>`:''}
        </div>`).join('')}</div>
      ${photos.length>3?`<div class="item-preview-photo-more">+ altre ${photos.length-3} foto nella scheda Modifica</div>`:''}`;
  }else{
    $('viewPhotos').innerHTML=`<button type="button" class="item-preview-no-photo" onclick="openPreviewPhotosEditor()">📷 Nessuna foto · Aggiungi</button>`;
  }
  $('viewDetails').innerHTML=rows.length?rows.join(''):'<div class="empty">Nessun dettaglio aggiuntivo.</div>';
  $('viewDlg').classList.add('show');
}
function closeItemPreview(){$('viewDlg').classList.remove('show');viewingItem=null;}
function modifyPreviewItem(){const id=viewingItem;if(!id)return;closeItemPreview();editItem(id);}
async function openPreviewPhotosEditor(){
  const id=viewingItem;if(!id)return;
  closeItemPreview();
  await editItem(id);
  const photoBtn=[...document.querySelectorAll('#editDlg .tabbtn')].find(b=>b.textContent.trim()==='Foto');
  if(photoBtn) photoBtn.click();
}

async function editItem(id){
  let i=S.items.find(x=>x.id===id);
  if(!i){
    try{
      i=await api('api/items/'+id);
      mergeLoadedItems([i]);
    }catch(e){alert(e.message);return;}
  }
  editingItem=id;
  $('eName').value=i.name||'';
  $('eType').value=i.item_type_id||'';
  $('eQty').value=i.quantity||1;
  $('eEnv').value=i.environment||'';
  $('eFurn').value=i.furniture||'';
  $('eShelf').value=i.shelf||'';
  $('eCont').value=i.container_name||'';
  $('eCode').value=i.container_code||'';
  $('eDesc').value=i.description||'';
  $('eNotes').value=i.notes||'';
  $('eTags').value=i.tags||'';
  $('photoProfile').value='auto';
  $('photoFile').value='';
  $('photoLabel').value='';
  renderCustom('edit',i.custom_values||{});
  renderPhotos(i);
  document.querySelectorAll('#editDlg .tab').forEach(x=>x.classList.remove('active'));
  $('edit-general').classList.add('active');
  document.querySelectorAll('#editDlg .tabbtn').forEach(x=>x.classList.remove('active'));
  document.querySelector('#editDlg .tabbtn').classList.add('active');
  $('editDlg').classList.add('show');
  enableVoiceInputs($('editDlg'));
}

function closeEdit(){$('editDlg').classList.remove('show');editingItem=null;}

async function saveItem(){
  if(!editingItem)return;
  try{
    await api('api/items/'+editingItem,{method:'PUT',body:JSON.stringify({
      name:$('eName').value,
      item_type_id:$('eType').value||null,
      quantity:$('eQty').value,
      environment:$('eEnv').value,
      furniture:$('eFurn').value,
      shelf:$('eShelf').value,
      container_name:$('eCont').value,
      container_code:$('eCode').value,
      description:$('eDesc').value,
      notes:$('eNotes').value,
      tags:$('eTags').value,
      custom_values:collectCustom('customEdit')
    })});
    await load();
    closeEdit();
  }catch(e){alert(e.message);}
}

async function deleteItem(id){
  if(!confirm('Eliminare questo elemento?'))return;
  try{await api('api/items/'+id,{method:'DELETE'});await load();}catch(e){alert(e.message);}
}

async function deleteEditingItem(){
  if(!editingItem)return;
  const id=editingItem;
  const item=S.items.find(x=>x.id===id);
  const label=item?.name ? ` “${item.name}”` : '';
  if(!confirm('Eliminare definitivamente'+label+'?'))return;
  try{
    await api('api/items/'+id,{method:'DELETE'});
    closeEdit();
    await load();
  }catch(e){alert(e.message);}
}

function renderPhotos(i){
  const photos=i.photos||[];
  $('photoGrid').innerHTML=photos.length?photos.map(p=>`
    <div class="photo">
      <img src="files/${encodeURIComponent(p.thumb_filename)}" onclick="openPhoto('${p.filename}')">
      <div class="meta">${esc(p.label||'')}</div>
      <button class="danger small" onclick="deletePhoto(${p.id})">Elimina</button>
    </div>`).join(''):'<div class="empty">Nessuna foto.</div>';
}

function openPhoto(filename){
  const box=$('photoLightbox');
  const img=$('photoLightboxImg');
  img.src='files/'+encodeURIComponent(filename);
  box.classList.add('open');
  document.body.style.overflow='hidden';
}
function closePhoto(){
  const box=$('photoLightbox');
  const img=$('photoLightboxImg');
  box.classList.remove('open');
  img.removeAttribute('src');
  document.body.style.overflow='';
}
document.addEventListener('keydown',e=>{
  if(e.key==='Escape' && $('photoLightbox')?.classList.contains('open')) closePhoto();
});

async function uploadPhoto(){
  if(!editingItem)return;
  const file=$('photoFile').files[0];
  if(!file){alert('Scegli una foto');return;}
  const fd=new FormData();
  fd.append('file',file);
  fd.append('profile',$('photoProfile').value);
  fd.append('label',$('photoLabel').value);
  const r=await fetch('api/items/'+editingItem+'/photos',{method:'POST',body:fd});
  const d=await r.json().catch(()=>({}));
  if(!r.ok){alert(d.error||'Errore caricamento foto');return;}
  await load();
  const item=S.items.find(x=>x.id===editingItem);
  if(item)renderPhotos(item);
  $('photoFile').value='';$('photoLabel').value='';
}

async function deletePhoto(id){
  if(!confirm('Eliminare questa foto?'))return;
  try{
    await api('api/photos/'+id,{method:'DELETE'});
    await load();
    const item=S.items.find(x=>x.id===editingItem);
    if(item)renderPhotos(item);
  }catch(e){alert(e.message);}
}

function refreshSubgroupFieldOptions(selected=''){
  const sel=$('tSubgroupField'); if(!sel)return;
  const rows=[...document.querySelectorAll('#typeFields .fieldrow')].filter(r=>r.dataset.active!=='0' && r.dataset.id);
  sel.innerHTML='<option value="">Nessuno</option>'+rows.map(r=>`<option value="${esc(r.dataset.id)}">${esc(r.querySelector('.flabel').value||'Campo')}</option>`).join('');
  sel.value=String(selected||'');
}

function openTypeDialog(){
  editingType=null;
  $('deleteTypeBtn').style.display='none';
  $('typeDlgTitle').textContent='🏷️ Nuova tipologia';
  $('tName').value='';
  $('tIconCustom').value='';
  $('tIcon').value='📦';
  $('typeFields').innerHTML='';
  addFieldRow();
  refreshSubgroupFieldOptions('');
  $('typeDlg').classList.add('show');
  enableVoiceInputs($('typeDlg'));
  enableVoiceInputs($('typeDlg'));
}

function closeTypeDialog(){$('typeDlg').classList.remove('show');editingType=null;}

function addFieldRow(field={}){
  const row=document.createElement('div');
  row.className='fieldrow'+(field.active===0?' inactive':'');
  row.dataset.id=field.id||'';
  row.dataset.active=field.active===0?'0':'1';
  row.innerHTML=`
    <input class="flabel" placeholder="Nome campo" value="${esc(field.label||'')}">
    <select class="ftype">
      <option value="text">Testo</option>
      <option value="number">Numero</option>
      <option value="date">Data</option>
      <option value="textarea">Testo lungo</option>
      <option value="select">Elenco</option>
      <option value="checkbox">Sì/No</option>
    </select>
    <label class="check"><input class="freq" type="checkbox"${field.required?' checked':''}> obbl.</label>
    <button class="secondary small" onclick="moveField(this,-1)">↑</button>
    <button class="secondary small" onclick="moveField(this,1)">↓</button>
    <button class="secondary small" onclick="toggleField(this)">${field.active===0?'Riattiva':'Nascondi'}</button>
    <input class="fopts options" placeholder="Opzioni separate da virgola (solo per Elenco)" value="${esc(field.options||'')}">
    <input class="fplaceholder options" placeholder="Testo di esempio, es. HDMI, USB, Ethernet..." value="${esc(field.placeholder||'')}">
  `;
  row.querySelector('.ftype').value=field.field_type||'text';
  $('typeFields').appendChild(row);
  enableVoiceInputs(row);
  row.querySelector('.flabel').addEventListener('input',()=>refreshSubgroupFieldOptions($('tSubgroupField').value));
  refreshSubgroupFieldOptions($('tSubgroupField')?.value||'');
}

function moveField(btn,dir){
  const row=btn.parentElement, parent=row.parentElement;
  if(dir<0 && row.previousElementSibling) parent.insertBefore(row,row.previousElementSibling);
  if(dir>0 && row.nextElementSibling) parent.insertBefore(row.nextElementSibling,row);
}

function toggleField(btn){
  const row=btn.parentElement;
  const active=row.dataset.active!=='0';
  row.dataset.active=active?'0':'1';
  row.classList.toggle('inactive',active);
  btn.textContent=active?'Riattiva':'Nascondi';
  refreshSubgroupFieldOptions($('tSubgroupField')?.value||'');
}

function editType(id){
  const t=typeById(id);
  if(!t)return;
  editingType=id;
  $('typeDlgTitle').textContent='✏️ Modifica tipologia';
  $('deleteTypeBtn').style.display='inline-block';
  $('tName').value=t.name;
  $('tIconCustom').value=t.icon;
  $('typeFields').innerHTML='';
  (t.fields||[]).forEach(addFieldRow);
  refreshSubgroupFieldOptions(t.subgroup_field_id||'');
  $('typeDlg').classList.add('show');
}

async function deleteType(){
  if(!editingType)return;
  const t=typeById(editingType);
  const name=t?t.name:'questa tipologia';
  if(!confirm(`Eliminare definitivamente la tipologia "${name}"?\n\nL'operazione è consentita solo se nessun elemento la sta usando.`))return;
  try{
    await api('api/types/'+editingType,{method:'DELETE'});
    closeTypeDialog();
    await load();
  }catch(e){alert(e.message);}
}

async function saveType(){
  const fields=[...document.querySelectorAll('#typeFields .fieldrow')].map(row=>({
    id:row.dataset.id?Number(row.dataset.id):null,
    label:row.querySelector('.flabel').value,
    field_type:row.querySelector('.ftype').value,
    required:row.querySelector('.freq').checked,
    options:row.querySelector('.fopts').value,
    placeholder:row.querySelector('.fplaceholder').value,
    active:row.dataset.active!=='0'
  })).filter(f=>f.label.trim());

  const payload={
    name:$('tName').value,
    icon:$('tIconCustom').value.trim()||$('tIcon').value,
    subgroup_field_id:$('tSubgroupField').value||null,
    fields
  };

  try{
    if(editingType){
      await api('api/types/'+editingType,{method:'PUT',body:JSON.stringify(payload)});
    }else{
      await api('api/types',{method:'POST',body:JSON.stringify(payload)});
    }
    closeTypeDialog();
    await load();
  }catch(e){alert(e.message);}
}


function backupBytes(n){
  n=Number(n||0);
  if(n<1024)return n+' B';
  if(n<1024*1024)return (n/1024).toFixed(1)+' KB';
  return (n/1024/1024).toFixed(1)+' MB';
}

async function openBackupDialog(){
  $('backupDlg').classList.add('show');
  await loadBackupList();
}

function closeBackupDialog(){
  $('backupDlg').classList.remove('show');
}

function backupDate(value){
  if(!value) return "";
  const m=String(value).match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/);
  if(!m) return value;
  return `${m[3]}/${m[2]}/${m[1]} · ${m[4]}:${m[5]}:${m[6]}`;
}

async function loadBackupList(){
  const box=$('backupList');
  box.innerHTML='<div class="hint">Caricamento backup…</div>';

  try{
    const data=await api('api/backups');
    const rows=data.backups||[];

    const count=$('backupCount');
    if(count) count.textContent=rows.length;

    box.innerHTML=rows.length
      ? rows.map(b=>`
        <div class="backup-row">
          <div class="backup-row-name">${esc(b.filename)}</div>

          <div class="backup-row-meta">
            <span>🕒 ${esc(backupDate(b.modified))}</span>
            <span>💾 ${backupBytes(b.size)}</span>
            ${b.schema_version!==null && b.schema_version!==undefined
              ? `<span>Schema ${esc(b.schema_version)}</span>`
              : ''}
          </div>

          <div class="backup-row-status ${b.valid?'ok':'bad'}">
            ${b.valid
              ? `✓ Integro${b.items!==null?` · ${b.items} elementi`:''}`
              : `⚠ ${esc(b.integrity||'Backup non valido')}`}
          </div>

          <div class="backup-row-actions">
            <a class="secondary backup-download"
               style="display:flex;align-items:center;justify-content:center;text-decoration:none;border-radius:10px;padding:8px"
               href="api/backups/download/${encodeURIComponent(b.filename)}">
              ⬇ Scarica
            </a>

            ${b.valid?`
              <button type="button"
                      class="backup-restore"
                      onclick="restoreBackupFromUi('${esc(b.filename)}')">
                ↩ Ripristina
              </button>
            `:''}
          </div>
        </div>
      `).join('')
      : '<div class="empty">Nessun backup disponibile.</div>';

  }catch(e){
    box.innerHTML=`<div class="notice">Errore: ${esc(e.message)}</div>`;
  }
}

async function createManualBackup(){
  if(!confirm(
    'Creare adesso una copia di sicurezza del database?'
  ))return;

  try{
    const data=await api('api/backups/create',{
      method:'POST',
      body:JSON.stringify({})
    });

    alert(
      'Backup creato correttamente:\\n\\n'+data.filename
    );

    await loadBackupList();

  }catch(e){
    alert(e.message);
  }
}

async function restoreBackupFromUi(filename){
  if(!confirm(
    'Ripristinare questo backup?\\n\\n'+filename+
    '\\n\\nIl database attuale verrà sostituito. '+
    'Prima del ripristino Inventario Casa proverà a crearne '+
    'un ulteriore backup di sicurezza.'
  ))return;

  const confirmation=prompt(
    'Per confermare scrivi esattamente:\\n\\nRIPRISTINA'
  );

  if(confirmation!=='RIPRISTINA'){
    alert('Ripristino annullato.');
    return;
  }

  try{
    const data=await api('api/backups/restore',{
      method:'POST',
      body:JSON.stringify({filename})
    });

    let message=
      'Database ripristinato correttamente.\\n\\n'+
      'Elementi: '+(data.database?.items??'?')+'\\n'+
      'Tipologie: '+(data.database?.types??'?')+'\\n'+
      'Foto: '+(data.database?.photos??'?')+'\\n'+
      'Integrity check: '+(data.database?.integrity??'?');

    if(data.safety_backup){
      message+='\\n\\nBackup del DB precedente:\\n'+
        data.safety_backup;
    }

    if(data.safety_warning){
      message+='\\n\\nNota: non è stato possibile verificare '+
        'il DB precedente:\\n'+data.safety_warning;
    }

    alert(message);

    closeBackupDialog();
    await load();

  }catch(e){
    alert(
      'Ripristino non riuscito:\\n\\n'+e.message+
      '\\n\\nIl backup selezionato non viene eliminato.'
    );
    await loadBackupList();
  }
}


$('search').addEventListener('keydown',e=>{if(e.key==='Enter')load();});

syncHomeAssistantTheme();
updateSearchClear();

window.addEventListener('focus',syncHomeAssistantTheme);
document.addEventListener('visibilitychange',()=>{
  if(!document.hidden)syncHomeAssistantTheme();
});

setTypePanelCollapsed(localStorage.getItem('inventario_type_panel_collapsed')==='1');
load();

// v0.1.20 - porta automaticamente il campo attivo nella zona visibile su smartphone
let mobileFocusTimer=null;

function ensureFocusedFieldVisible(el){
  if(!el || !window.matchMedia('(max-width: 700px)').matches) return;

  clearTimeout(mobileFocusTimer);
  mobileFocusTimer=setTimeout(()=>{
    try{
      el.scrollIntoView({
        behavior:'smooth',
        block:'center',
        inline:'nearest'
      });
    }catch(e){
      el.scrollIntoView();
    }
  },220);
}

document.addEventListener('focusin',e=>{
  const el=e.target;
  if(!el.matches('input,select,textarea')) return;
  ensureFocusedFieldVisible(el);
});

if(window.visualViewport){
  let lastViewportHeight=window.visualViewport.height;

  window.visualViewport.addEventListener('resize',()=>{
    const active=document.activeElement;
    if(!active || !active.matches?.('input,select,textarea')) return;

    const current=window.visualViewport.height;
    const keyboardLikelyOpen=current < lastViewportHeight - 80 || current < window.innerHeight * .82;

    if(keyboardLikelyOpen){
      ensureFocusedFieldVisible(active);
    }

    lastViewportHeight=current;
  });

  window.visualViewport.addEventListener('scroll',()=>{
    const active=document.activeElement;
    if(active && active.matches?.('input,textarea')){
      ensureFocusedFieldVisible(active);
    }
  });
}

</script>
</body>
</html>
"""


@app.get("/")
def index():
    if STARTUP_DB_ERROR:
        return render_template_string(
            RECOVERY_PAGE,
            startup_error=STARTUP_DB_ERROR,
        )
    return render_template_string(PAGE)

