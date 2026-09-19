import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, send_from_directory
from PIL import Image, ImageOps


def create_media_blueprint(*, db, media_dir):
    bp = Blueprint("media", __name__)

    @bp.post("/api/items/<int:item_id>/photos")
    def api_upload_photo(item_id):
        if "file" not in request.files:
            return jsonify(error="Nessun file selezionato"), 400

        with db() as conn:
            item = conn.execute(
                """SELECT i.id,t.name AS type_name
                   FROM items i LEFT JOIN item_types t
                   ON t.id=i.item_type_id
                   WHERE i.id=?""",
                (item_id,),
            ).fetchone()

            if not item:
                return jsonify(error="Elemento non trovato"), 404

        profile = request.form.get("profile", "auto")

        if profile == "auto":
            profile = (
                "collectible"
                if (item["type_name"] or "").lower() == "fumetto"
                else "standard"
            )

        max_px, quality = (
            (2400, 90)
            if profile == "collectible"
            else (1600, 84)
        )

        upload = request.files["file"]
        uid = uuid.uuid4().hex
        full_name = f"{item_id}_{uid}.webp"
        thumb_name = f"{item_id}_{uid}_thumb.webp"

        try:
            image = Image.open(upload.stream)
            image = ImageOps.exif_transpose(image).convert("RGB")
            image.thumbnail((max_px, max_px))
            image.save(
                media_dir / full_name,
                "WEBP",
                quality=quality,
                method=6,
            )

            thumb = image.copy()
            thumb.thumbnail((360, 360))
            thumb.save(
                media_dir / thumb_name,
                "WEBP",
                quality=80,
                method=6,
            )

            with db() as conn:
                cur = conn.execute(
                    """INSERT INTO item_photos(
                           item_id,
                           filename,
                           thumb_filename,
                           label,
                           created_at
                       )
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
                    (media_dir / filename).unlink(missing_ok=True)
                except Exception:
                    pass

            return jsonify(
                error=f"Immagine non valida: {exc}"
            ), 400

    @bp.delete("/api/photos/<int:photo_id>")
    def api_delete_photo(photo_id):
        with db() as conn:
            photo = conn.execute(
                """SELECT filename,thumb_filename
                   FROM item_photos
                   WHERE id=?""",
                (photo_id,),
            ).fetchone()

            if not photo:
                return jsonify(error="Foto non trovata"), 404

            for filename in (
                photo["filename"],
                photo["thumb_filename"],
            ):
                try:
                    (media_dir / filename).unlink(missing_ok=True)
                except Exception:
                    pass

            conn.execute(
                "DELETE FROM item_photos WHERE id=?",
                (photo_id,),
            )

        return jsonify(ok=True)

    @bp.get("/files/<path:filename>")
    def media_file(filename):
        return send_from_directory(media_dir, filename)

    return bp
