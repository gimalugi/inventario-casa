from flask import Blueprint, jsonify, request, send_from_directory

from backup import (
    apply_backup_retention,
    backup_path_from_name as resolve_backup_path,
    create_database_backup as backup_create,
    inspect_database_file,
    list_database_backups as backup_list,
)


def create_backup_blueprint(
    *,
    db_path,
    backup_dir,
    maintenance_lock,
    backup_keep_manual,
    get_startup_error,
    restore_database_backup,
):
    bp = Blueprint("backups", __name__)

    @bp.get("/api/backups")
    def api_backups():
        return jsonify(
            backups=backup_list(backup_dir),
            startup_error=get_startup_error(),
            current_database=inspect_database_file(db_path),
        )

    @bp.post("/api/backups/create")
    def api_create_backup():
        try:
            with maintenance_lock:
                path = backup_create(
                    db_path,
                    backup_dir,
                    prefix="inventory_manual",
                )
                apply_backup_retention(
                    backup_dir,
                    "manual",
                    backup_keep_manual,
                )

            return jsonify(
                ok=True,
                filename=path.name,
                database=inspect_database_file(path),
            ), 201

        except Exception as exc:
            return jsonify(error=str(exc)), 500

    @bp.post("/api/backups/restore")
    def api_restore_backup():
        data = request.get_json(silent=True) or {}
        filename = data.get("filename")

        try:
            result = restore_database_backup(filename)
            return jsonify(**result)

        except FileNotFoundError as exc:
            return jsonify(error=str(exc)), 404

        except ValueError as exc:
            return jsonify(error=str(exc)), 400

        except Exception as exc:
            return jsonify(
                error=str(exc),
                startup_error=get_startup_error(),
            ), 500

    @bp.get("/api/backups/download/<path:filename>")
    def api_download_backup(filename):
        try:
            path = resolve_backup_path(backup_dir, filename)
        except (ValueError, FileNotFoundError):
            return jsonify(error="Backup non trovato"), 404

        return send_from_directory(
            backup_dir,
            path.name,
            as_attachment=True,
        )

    return bp
