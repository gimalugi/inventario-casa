import sqlite3
from datetime import datetime

from flask import Blueprint, jsonify, request


def normalize_field_type(value):
    allowed = {"text", "number", "date", "textarea", "select", "checkbox"}
    return value if value in allowed else "text"


def create_type_blueprint(*, db):
    bp = Blueprint("types", __name__)

    @bp.post("/api/types")
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
                        """INSERT INTO type_fields(
                               type_id,label,field_type,required,
                               options,sort_order,active,placeholder
                           )
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
            return jsonify(
                error="Esiste già una tipologia con questo nome"
            ), 409

    @bp.put("/api/types/<int:type_id>")
    def api_update_type(type_id):
        data = request.get_json(force=True)
        name = (data.get("name") or "").strip()
        icon = (data.get("icon") or "📦").strip() or "📦"

        if not name:
            return jsonify(error="Il nome della tipologia è obbligatorio"), 400

        try:
            with db() as conn:
                if not conn.execute(
                    "SELECT id FROM item_types WHERE id=?",
                    (type_id,),
                ).fetchone():
                    return jsonify(error="Tipologia non trovata"), 404

                conn.execute(
                    "UPDATE item_types SET name=?,icon=? WHERE id=?",
                    (name, icon, type_id),
                )

                existing = {
                    r["id"]
                    for r in conn.execute(
                        "SELECT id FROM type_fields WHERE type_id=?",
                        (type_id,),
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
                               SET label=?,field_type=?,required=?,
                                   options=?,sort_order=?,active=?,placeholder=?
                               WHERE id=? AND type_id=?""",
                            values + (fid, type_id),
                        )
                    else:
                        cur = conn.execute(
                            """INSERT INTO type_fields(
                                   type_id,label,field_type,required,
                                   options,sort_order,active,placeholder
                               )
                               VALUES(?,?,?,?,?,?,?,?)""",
                            (type_id,) + values,
                        )
                        incoming.add(cur.lastrowid)

                # Mai cancellare automaticamente un campo:
                # se sparisce dal form viene disattivato.
                for fid in existing - incoming:
                    conn.execute(
                        """UPDATE type_fields
                           SET active=0
                           WHERE id=? AND type_id=?""",
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
                        """SELECT 1
                           FROM type_fields
                           WHERE id=? AND type_id=? AND active=1""",
                        (subgroup_field_id, type_id),
                    ).fetchone():
                        subgroup_field_id = None

                conn.execute(
                    """UPDATE item_types
                       SET subgroup_field_id=?
                       WHERE id=?""",
                    (subgroup_field_id, type_id),
                )

                return jsonify(ok=True)

        except sqlite3.IntegrityError:
            return jsonify(
                error="Esiste già una tipologia con questo nome"
            ), 409

    @bp.delete("/api/types/<int:type_id>")
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
                    error=(
                        "Impossibile eliminare la tipologia: "
                        f"è usata da {used} elemento/i. "
                        "Cambia prima la tipologia di questi elementi."
                    )
                ), 409

            conn.execute(
                "DELETE FROM item_types WHERE id=?",
                (type_id,),
            )

            return jsonify(ok=True)

    return bp
