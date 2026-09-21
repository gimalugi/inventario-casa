from datetime import datetime

from flask import Blueprint, jsonify, request


def item_payload(data):
    return (
        (data.get("name") or "").strip(),
        (data.get("description") or "").strip(),
        max(1, int(data.get("quantity") or 1)),
        data.get("item_type_id") or None,
        (data.get("environment") or "").strip(),
        data.get("environment_id") or None,
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
                """INSERT INTO item_custom_values(item_id,field_id,value)
                   VALUES(?,?,?)""",
                (item_id, int(fid), value),
            )


def create_item_blueprint(*, db, media_dir):
    bp = Blueprint("items", __name__)

    @bp.post("/api/items")
    def api_create_item():
        data = request.get_json(force=True)
        values = item_payload(data)

        if not values[0]:
            return jsonify(
                error="Il nome dell'elemento è obbligatorio"
            ), 400

        now = datetime.now().isoformat(timespec="seconds")

        try:
            with db() as conn:
                cur = conn.execute(
                    """INSERT INTO items(
                        name,description,quantity,item_type_id,
                        environment,environment_id,furniture,shelf,
                        container_name,container_code,tags,notes,
                        created_at,updated_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    values + (now, now),
                )

                save_custom_values(
                    conn,
                    cur.lastrowid,
                    values[3],
                    data.get("custom_values"),
                )

                return jsonify(id=cur.lastrowid), 201

        except ValueError as exc:
            return jsonify(error=str(exc)), 400

    @bp.put("/api/items/<int:item_id>")
    def api_update_item(item_id):
        data = request.get_json(force=True)
        values = item_payload(data)

        if not values[0]:
            return jsonify(
                error="Il nome dell'elemento è obbligatorio"
            ), 400

        try:
            with db() as conn:
                if not conn.execute(
                    "SELECT id FROM items WHERE id=?",
                    (item_id,),
                ).fetchone():
                    return jsonify(error="Elemento non trovato"), 404

                conn.execute(
                    """UPDATE items SET
                        name=?,description=?,quantity=?,item_type_id=?,
                        environment=?,environment_id=?,furniture=?,shelf=?,
                        container_name=?,container_code=?,tags=?,notes=?,
                        updated_at=?
                       WHERE id=?""",
                    values + (
                        datetime.now().isoformat(timespec="seconds"),
                        item_id,
                    ),
                )

                save_custom_values(
                    conn,
                    item_id,
                    values[3],
                    data.get("custom_values"),
                )

                return jsonify(ok=True)

        except ValueError as exc:
            return jsonify(error=str(exc)), 400

    @bp.delete("/api/items/<int:item_id>")
    def api_delete_item(item_id):
        with db() as conn:
            photos = list(
                conn.execute(
                    """SELECT filename,thumb_filename
                       FROM item_photos
                       WHERE item_id=?""",
                    (item_id,),
                )
            )

            for photo in photos:
                for filename in (
                    photo["filename"],
                    photo["thumb_filename"],
                ):
                    try:
                        (media_dir / filename).unlink(missing_ok=True)
                    except Exception:
                        pass

            conn.execute(
                "DELETE FROM items WHERE id=?",
                (item_id,),
            )

        return jsonify(ok=True)

    return bp
