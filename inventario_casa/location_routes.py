from datetime import datetime

from flask import Blueprint, jsonify, request


def create_location_blueprint(*, db):
    bp = Blueprint("locations", __name__)

    @bp.get("/api/properties")
    def get_properties():
        with db() as conn:
            properties = conn.execute(
                """
                SELECT id, name, is_default
                FROM properties
                ORDER BY is_default DESC, name COLLATE NOCASE
                """
            ).fetchall()

            result = []

            for prop in properties:
                environments = conn.execute(
                    """
                    SELECT id, name, sort_order, active
                    FROM environments
                    WHERE property_id=?
                    ORDER BY sort_order, name COLLATE NOCASE
                    """,
                    (prop["id"],),
                ).fetchall()

                result.append({
                    "id": prop["id"],
                    "name": prop["name"],
                    "is_default": bool(prop["is_default"]),
                    "environments": [
                        {
                            "id": env["id"],
                            "name": env["name"],
                            "sort_order": env["sort_order"],
                            "active": bool(env["active"]),
                        }
                        for env in environments
                    ],
                })

        return jsonify({"properties": result})

    @bp.post("/api/properties")
    def create_property():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()

        if not name:
            return jsonify({"error": "property_name_required"}), 400

        now = datetime.now().isoformat(timespec="seconds")

        try:
            with db() as conn:
                cur = conn.execute(
                    "INSERT INTO properties(name,is_default,created_at) "
                    "VALUES(?,?,?)",
                    (name, 0, now),
                )
                property_id = cur.lastrowid
        except Exception as exc:
            if "UNIQUE constraint failed" in str(exc):
                return jsonify({"error": "property_already_exists"}), 409
            raise

        return jsonify({
            "ok": True,
            "property": {
                "id": property_id,
                "name": name,
                "is_default": False,
                "environments": [],
            }
        }), 201

    @bp.post("/api/environments")
    def create_environment():
        data = request.get_json(silent=True) or {}

        name = (data.get("name") or "").strip()
        property_id = data.get("property_id")

        if not name:
            return jsonify({"error": "environment_name_required"}), 400

        if not property_id:
            return jsonify({"error": "property_required"}), 400

        with db() as conn:
            prop = conn.execute(
                "SELECT id FROM properties WHERE id=?",
                (property_id,),
            ).fetchone()

            if prop is None:
                return jsonify({"error": "property_not_found"}), 404

            try:
                cur = conn.execute(
                    "INSERT INTO environments"
                    "(property_id,name,sort_order,active,created_at) "
                    "VALUES(?,?,?,?,?)",
                    (
                        property_id,
                        name,
                        0,
                        1,
                        datetime.now().isoformat(timespec="seconds"),
                    ),
                )
                environment_id = cur.lastrowid
            except Exception as exc:
                if "UNIQUE constraint failed" in str(exc):
                    return jsonify({"error": "environment_already_exists"}), 409
                raise

        return jsonify({
            "ok": True,
            "environment": {
                "id": environment_id,
                "property_id": property_id,
                "name": name,
                "sort_order": 0,
                "active": True,
            }
        }), 201

    @bp.put("/api/properties/<int:property_id>")
    def update_property(property_id):
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()

        if not name:
            return jsonify({"error": "property_name_required"}), 400

        with db() as conn:
            prop = conn.execute(
                "SELECT id FROM properties WHERE id=?",
                (property_id,),
            ).fetchone()

            if prop is None:
                return jsonify({"error": "property_not_found"}), 404

            try:
                conn.execute(
                    "UPDATE properties SET name=? WHERE id=?",
                    (name, property_id),
                )
            except Exception as exc:
                if "UNIQUE constraint failed" in str(exc):
                    return jsonify({"error": "property_already_exists"}), 409
                raise

        return jsonify({"ok": True})


    @bp.put("/api/environments/<int:environment_id>")
    def update_environment(environment_id):
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()

        if not name:
            return jsonify({"error": "environment_name_required"}), 400

        with db() as conn:
            env = conn.execute(
                "SELECT id FROM environments WHERE id=?",
                (environment_id,),
            ).fetchone()

            if env is None:
                return jsonify({"error": "environment_not_found"}), 404

            try:
                conn.execute(
                    "UPDATE environments SET name=? WHERE id=?",
                    (name, environment_id),
                )
            except Exception as exc:
                if "UNIQUE constraint failed" in str(exc):
                    return jsonify({"error": "environment_already_exists"}), 409
                raise

        return jsonify({"ok": True})


    @bp.delete("/api/properties/<int:property_id>")
    def delete_property(property_id):
        with db() as conn:
            prop = conn.execute(
                "SELECT id, is_default FROM properties WHERE id=?",
                (property_id,),
            ).fetchone()

            if prop is None:
                return jsonify({"error": "property_not_found"}), 404

            count = conn.execute(
                "SELECT COUNT(*) FROM properties"
            ).fetchone()[0]

            if count <= 1:
                return jsonify({"error": "cannot_delete_only_property"}), 409

            env_count = conn.execute(
                "SELECT COUNT(*) FROM environments WHERE property_id=?",
                (property_id,),
            ).fetchone()[0]

            if env_count:
                return jsonify({"error": "property_has_environments"}), 409

            conn.execute(
                "DELETE FROM properties WHERE id=?",
                (property_id,),
            )

            if prop["is_default"]:
                new_default = conn.execute(
                    "SELECT id FROM properties ORDER BY id LIMIT 1"
                ).fetchone()

                if new_default:
                    conn.execute(
                        "UPDATE properties SET is_default=1 WHERE id=?",
                        (new_default["id"],),
                    )

        return jsonify({"ok": True})


    @bp.delete("/api/environments/<int:environment_id>")
    def delete_environment(environment_id):
        with db() as conn:
            env = conn.execute(
                "SELECT id FROM environments WHERE id=?",
                (environment_id,),
            ).fetchone()

            if env is None:
                return jsonify({"error": "environment_not_found"}), 404

            conn.execute(
                "DELETE FROM environments WHERE id=?",
                (environment_id,),
            )

        return jsonify({"ok": True})


    @bp.put("/api/properties/<int:property_id>/default")
    def set_default_property(property_id):
        with db() as conn:
            prop = conn.execute(
                "SELECT id FROM properties WHERE id=?",
                (property_id,),
            ).fetchone()

            if prop is None:
                return jsonify({"error": "property_not_found"}), 404

            conn.execute("UPDATE properties SET is_default=0")
            conn.execute(
                "UPDATE properties SET is_default=1 WHERE id=?",
                (property_id,),
            )

        return jsonify({"ok": True})


    return bp
