#!/usr/bin/env bash
set -euo pipefail

REPO="gimalugi/inventario-casa"
CONFIG="inventario_casa/config.yaml"
API="https://api.github.com"

die() {
  echo "ERRORE: $*" >&2
  exit 1
}

[ $# -eq 1 ] || die "Uso: ./release.sh VERSIONE  (esempio: ./release.sh 2.3.5)"

VERSION="${1#v}"
TAG="v${VERSION}"

[ -n "${GITHUB_TOKEN:-}" ] || die "GITHUB_TOKEN non impostato."

BRANCH="$(git branch --show-current)"
[ "$BRANCH" = "main" ] || die "Devi essere sul branch main. Branch attuale: $BRANCH"

[ -z "$(git status --porcelain)" ] || die "Repository non pulito."

[ -f "$CONFIG" ] || die "$CONFIG non trovato."

CONFIG_VERSION="$(sed -n 's/^version:[[:space:]]*["'\'']\?\([^"'\'']*\)["'\'']\?.*/\1/p' "$CONFIG" | head -1)"

[ "$CONFIG_VERSION" = "$VERSION" ] || die "config.yaml contiene $CONFIG_VERSION, richiesta $VERSION."

git fetch origin main --tags

[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || \
  die "main locale diverso da origin/main."

if git rev-parse "$TAG" >/dev/null 2>&1; then
  die "Il tag $TAG esiste già."
fi

echo
echo "Controlli superati"
echo "Versione: $VERSION"
echo "Tag:      $TAG"
echo "Commit:   $(git rev-parse --short HEAD)"
echo

read -r -p "Creare la release $TAG? [y/N] " ANSWER

case "$ANSWER" in
  y|Y) ;;
  *) echo "Annullato."; exit 0 ;;
esac

git tag -a "$TAG" -m "Inventario Casa $TAG"
git push origin "$TAG"

NOTES="## Inventario Casa $TAG

Release di Inventario Casa versione $VERSION.

### Compatibilità

- Nessuna modifica al database o al relativo schema.
- Inventario, fotografie, backup e dati esistenti rimangono invariati."

python3 - "$TAG" "$NOTES" > /tmp/release.json <<'PY'
import json, sys
tag, notes = sys.argv[1], sys.argv[2]
print(json.dumps({
    "tag_name": tag,
    "target_commitish": "main",
    "name": f"Inventario Casa {tag}",
    "body": notes,
    "draft": False,
    "prerelease": False,
    "make_latest": "true"
}))
PY

CODE="$(curl -sS -o /tmp/release-result.json -w '%{http_code}' \
  -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "$API/repos/$REPO/releases" \
  -d @/tmp/release.json)"

if [ "$CODE" != "201" ]; then
  cat /tmp/release-result.json
  die "GitHub Release non creata. HTTP $CODE"
fi

echo
echo "OK: release $TAG creata."
