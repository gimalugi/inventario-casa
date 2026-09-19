import hashlib
import json
from pathlib import Path


FRONTEND_ASSETS = (
    "css/app.css",
    "js/app.js",
    "translations/it.json",
    "translations/en.json",
)


def asset_version(static_folder):
    static_dir = Path(static_folder)
    digest = hashlib.sha256()

    for filename in FRONTEND_ASSETS:
        digest.update((static_dir / filename).read_bytes())

    return digest.hexdigest()[:12]


def load_translations(static_folder):
    translations_dir = Path(static_folder) / "translations"

    return {
        "it": json.loads(
            (translations_dir / "it.json").read_text(encoding="utf-8")
        ),
        "en": json.loads(
            (translations_dir / "en.json").read_text(encoding="utf-8")
        ),
    }
