import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Blueprint, current_app, jsonify, request
from PIL import Image, ImageOps
from pyzbar.pyzbar import decode as zbar_decode


def create_lookup_blueprint():
    bp = Blueprint("lookup", __name__)

    @bp.get("/api/lookup-book")
    def api_lookup_book():
        raw = request.args.get("code", "").strip()
        code = re.sub(r"[^0-9Xx]", "", raw).upper()

        if len(code) not in {10, 13}:
            return jsonify(
                error="Inserisci un ISBN di 10 o 13 caratteri."
            ), 400

        if len(code) == 13 and not code.startswith(("978", "979")):
            return jsonify(
                error=(
                    "Questo EAN non sembra un ISBN. "
                    "Per ora la ricerca automatica gestisce ISBN 10/13."
                )
            ), 400

        def fetch_json(url):
            req = Request(
                url,
                headers={
                    "User-Agent": (
                        "InventarioCasa/2.0.0 "
                        "(Home Assistant local app)"
                    ),
                    "Accept": "application/json",
                },
            )
            with urlopen(req, timeout=8) as resp:
                return json.loads(
                    resp.read().decode("utf-8")
                )

        # Fonte primaria: Google Books
        google_error = None

        try:
            data = fetch_json(
                "https://www.googleapis.com/books/v1/volumes"
                f"?q=isbn:{code}&maxResults=5&printType=books"
            )

            items = data.get("items") or []
            selected = None

            for item in items:
                info = item.get("volumeInfo") or {}
                ids = info.get("industryIdentifiers") or []

                values = {
                    re.sub(
                        r"[^0-9Xx]",
                        "",
                        str(x.get("identifier") or ""),
                    ).upper()
                    for x in ids
                    if isinstance(x, dict)
                }

                if code in values:
                    selected = item
                    break

            if selected is None and items:
                selected = items[0]

            if selected:
                info = selected.get("volumeInfo") or {}
                publish_date = str(
                    info.get("publishedDate") or ""
                ).strip()

                ym = re.search(
                    r"(?:18|19|20)\d{2}",
                    publish_date,
                )
                year = ym.group(0) if ym else ""

                return jsonify(
                    source="Google Books",
                    code=code,
                    title=str(
                        info.get("title") or ""
                    ).strip(),
                    authors=[
                        str(a).strip()
                        for a in (info.get("authors") or [])
                        if str(a).strip()
                    ],
                    publisher=str(
                        info.get("publisher") or ""
                    ).strip(),
                    publish_date=publish_date,
                    year=year,
                )

        except HTTPError as exc:
            google_error = f"HTTP {exc.code}"

        except (URLError, TimeoutError, ValueError) as exc:
            google_error = (
                str(exc) or "errore di connessione"
            )

        # Fallback: Open Library
        try:
            book = fetch_json(
                f"https://openlibrary.org/isbn/{code}.json"
            )

        except HTTPError as exc:
            if exc.code == 404:
                msg = (
                    "Codice non trovato né su Google Books "
                    "né su Open Library."
                )

                if google_error:
                    msg += (
                        " Google Books non era disponibile "
                        f"({google_error})."
                    )

                return jsonify(error=msg), 404

            return jsonify(
                error=(
                    "Open Library ha risposto con errore "
                    f"HTTP {exc.code}."
                )
            ), 502

        except (URLError, TimeoutError, ValueError):
            if google_error:
                return jsonify(
                    error=(
                        "Impossibile contattare sia Google Books "
                        "sia Open Library. Controlla la connessione "
                        "Internet e riprova."
                    )
                ), 502

            return jsonify(
                error=(
                    "Impossibile contattare Open Library. "
                    "Controlla la connessione Internet e riprova."
                )
            ), 502

        authors = []

        for ref in (book.get("authors") or [])[:5]:
            key = (
                ref.get("key")
                if isinstance(ref, dict)
                else None
            )

            if not key:
                continue

            try:
                author = fetch_json(
                    f"https://openlibrary.org{key}.json"
                )
                if author.get("name"):
                    authors.append(author["name"])
            except Exception:
                pass

        publishers = book.get("publishers") or []
        publish_date = str(
            book.get("publish_date") or ""
        ).strip()

        ym = re.search(
            r"(?:18|19|20)\d{2}",
            publish_date,
        )
        year = ym.group(0) if ym else ""

        return jsonify(
            source="Open Library",
            code=code,
            title=str(
                book.get("title") or ""
            ).strip(),
            authors=authors,
            publisher=str(
                publishers[0] if publishers else ""
            ).strip(),
            publish_date=publish_date,
            year=year,
        )

    @bp.post("/api/decode-barcode")
    def api_decode_barcode():
        """Decodifica un barcode da una singola immagine."""
        upload = request.files.get("image")

        if not upload or not upload.filename:
            return jsonify(error="Immagine mancante."), 400

        try:
            image = Image.open(upload.stream)
            image = ImageOps.exif_transpose(
                image
            ).convert("RGB")

            if max(image.size) > 1800:
                image.thumbnail(
                    (1800, 1800),
                    Image.Resampling.LANCZOS,
                )

            found = []

            for result in zbar_decode(image):
                try:
                    raw = result.data.decode(
                        "utf-8",
                        errors="ignore",
                    )
                except Exception:
                    raw = str(result.data or "")

                code = re.sub(
                    r"[^0-9Xx]",
                    "",
                    raw,
                ).upper()

                if len(code) in {8, 10, 12, 13}:
                    found.append({
                        "raw": raw,
                        "code": code,
                        "format": str(
                            getattr(result, "type", "") or ""
                        ),
                    })

            if not found:
                return jsonify(
                    found=False,
                    barcodes=[],
                )

            return jsonify(
                found=True,
                barcodes=found,
            )

        except Exception as exc:
            current_app.logger.warning(
                "Errore decodifica barcode: %s",
                exc,
            )
            return jsonify(
                error=(
                    "Non sono riuscito a leggere il codice "
                    "da questa immagine."
                )
            ), 422

    return bp
