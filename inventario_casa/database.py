import sqlite3
from datetime import datetime

from backup import create_pre_migration_backup


def db(db_path, data_dir, media_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    media_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def table_columns(conn, table):
    return {
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})")
    }


def read_schema_version(db_path):
    if not db_path.exists():
        return 0

    conn = sqlite3.connect(db_path)

    try:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type='table' AND name='app_meta'"
        ).fetchone()

        if not exists:
            return 0

        row = conn.execute(
            "SELECT value FROM app_meta "
            "WHERE key='schema_version'"
        ).fetchone()

        if not row:
            return 0

        try:
            return int(row[0])
        except (TypeError, ValueError):
            return 0
    finally:
        conn.close()


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
        conn.execute(
            f"ALTER TABLE {table} ADD COLUMN {col} {declaration}"
        )


def ensure_type_field(
    conn,
    type_name,
    label,
    field_type="text",
    required=0,
    options="",
    sort_order=0,
):
    row = conn.execute(
        "SELECT id FROM item_types WHERE name=?",
        (type_name,),
    ).fetchone()

    if not row:
        return

    exists = conn.execute(
        """
        SELECT id
        FROM type_fields
        WHERE type_id=? AND lower(label)=lower(?)
        """,
        (row["id"], label),
    ).fetchone()

    if not exists:
        conn.execute(
            """
            INSERT INTO type_fields(
                type_id,
                label,
                field_type,
                required,
                options,
                sort_order,
                active
            )
            VALUES(?,?,?,?,?,?,1)
            """,
            (
                row["id"],
                label,
                field_type,
                required,
                options,
                sort_order,
            ),
        )


def init_db(
    db_path,
    data_dir,
    media_dir,
    backup_dir,
    current_schema_version,
):
    # Le tipologie standard vengono create esclusivamente quando il database
    # viene creato per la prima volta. Dopo l'inizializzazione, tipologie e
    # campi appartengono all'utente e non devono essere ricreati al riavvio.
    new_database = not db_path.exists()

    previous_schema_version = read_schema_version(db_path)

    if (
        db_path.exists()
        and previous_schema_version < current_schema_version
    ):
        print(
            "[Inventario Casa] Migrazione schema richiesta: "
            f"{previous_schema_version} -> {current_schema_version}"
        )

        create_pre_migration_backup(
            db_path,
            backup_dir,
            previous_schema_version,
            current_schema_version,
        )

    with db(db_path, data_dir, media_dir) as conn:
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

        write_schema_version(conn, current_schema_version)

        print(
            "[Inventario Casa] Schema database verificato: "
            f"versione {current_schema_version}"
        )
