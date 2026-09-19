import sqlite3
from datetime import datetime
from pathlib import Path


def create_pre_migration_backup(db_path, backup_dir, from_version, to_version):
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / (
        f"inventario_pre_schema_{from_version}_to_{to_version}_{stamp}.db"
    )

    source = sqlite3.connect(db_path)
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


def backup_path_from_name(backup_dir, filename):
    """Accetta esclusivamente file .db presenti nella cartella backup."""
    filename = Path(str(filename or "")).name

    if not filename or not filename.endswith(".db"):
        raise ValueError("Nome backup non valido")

    path = backup_dir / filename

    try:
        path.resolve().relative_to(backup_dir.resolve())
    except ValueError:
        raise ValueError("Percorso backup non valido")

    if not path.exists() or not path.is_file():
        raise FileNotFoundError("Backup non trovato")

    return path


def create_database_backup(db_path, backup_dir, prefix="inventario_manuale", verify=True):
    """Crea una copia SQLite consistente del database corrente."""
    if not db_path.exists():
        raise FileNotFoundError("Database principale non trovato")

    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{prefix}_{stamp}.db"

    source = sqlite3.connect(db_path)
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


def list_database_backups(backup_dir):
    backup_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    for path in sorted(
        backup_dir.glob("*.db"),
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
