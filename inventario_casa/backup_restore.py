import sqlite3
from datetime import datetime
from pathlib import Path

from backup import (
    apply_backup_retention,
    backup_path_from_name as resolve_backup_path,
    create_database_backup as backup_create,
    inspect_database_file,
)


def restore_database_backup(
    filename,
    *,
    db_path,
    data_dir,
    backup_dir,
    maintenance_lock,
    backup_keep_pre_restore,
    init_db,
    set_startup_error,
):
    """
    Ripristina un backup verificato.

    Il backup viene prima copiato in un database SQLite temporaneo,
    verificato e solo dopo sostituisce atomicamente il database corrente.
    Questo permette il recovery anche quando il DB corrente è corrotto.
    """

    with maintenance_lock:
        backup_path = resolve_backup_path(backup_dir, filename)

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
        if db_path.exists():
            try:
                safety_backup = backup_create(
                    db_path,
                    backup_dir,
                    prefix="inventory_pre_restore",
                    verify=True,
                )
                apply_backup_retention(
                    backup_dir,
                    "pre_restore",
                    backup_keep_pre_restore,
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

        data_dir.mkdir(parents=True, exist_ok=True)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        restore_tmp = data_dir / f".inventario_restore_{stamp}.db"

        source = None
        target = None

        try:
            # 3. Ricostruisce il backup in un NUOVO DB.
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
                sidecar = Path(str(db_path) + suffix)
                try:
                    sidecar.unlink()
                except FileNotFoundError:
                    pass

            # 6. Sostituzione atomica del database corrente.
            restore_tmp.replace(db_path)

            # 7. Esegue eventuali migrazioni necessarie.
            init_db()

            # 8. Verifica finale dopo init/migrazioni.
            final_info = inspect_database_file(db_path)

            if final_info.get("integrity") != "ok":
                raise RuntimeError(
                    "Il database non supera il controllo "
                    "di integrità dopo il ripristino"
                )

            set_startup_error(None)

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
            error = f"{type(exc).__name__}: {exc}"
            set_startup_error(error)

            print(
                "[Inventario Casa] ERRORE ripristino database: "
                + error
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
