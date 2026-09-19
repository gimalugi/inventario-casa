import sqlite3


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
