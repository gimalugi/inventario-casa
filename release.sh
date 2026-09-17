#!/usr/bin/env bash
set -euo pipefail

REPO="gimalugi/inventario-casa"
CONFIG="inventario_casa/config.yaml"
README_IT="README.md"
README_EN="README_EN.md"
API="https://api.github.com"
NOTES_FILE="RELEASE_NOTES.md"

die() {
  echo "ERRORE: $*" >&2
  exit 1
}

[ $# -eq 1 ] || die "Uso: ./release.sh VERSIONE  (esempio: ./release.sh 2.3.6)"

VERSION="${1#v}"
TAG="v${VERSION}"

[ -n "${GITHUB_TOKEN:-}" ] || die "GITHUB_TOKEN non impostato."

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || \
  die "Non sei dentro un repository Git."

BRANCH="$(git branch --show-current)"
[ "$BRANCH" = "main" ] || \
  die "Devi essere sul branch main. Branch attuale: $BRANCH"

[ -z "$(git status --porcelain)" ] || \
  die "Repository non pulito. Fai commit o annulla le modifiche prima della release."

[ -f "$CONFIG" ] || die "$CONFIG non trovato."

CONFIG_VERSION="$(sed -n 's/^version:[[:space:]]*["'\'']\?\([^"'\'']*\)["'\'']\?.*/\1/p' "$CONFIG" | head -1)"

[ "$CONFIG_VERSION" = "$VERSION" ] || \
  die "config.yaml contiene versione $CONFIG_VERSION, richiesta $VERSION."

# Controlla che anche la documentazione riporti la versione da pubblicare.
for README_FILE in "$README_IT" "$README_EN"; do
  [ -f "$README_FILE" ] || die "$README_FILE non trovato."

  README_VERSION="$(sed -n 's/^# Inventario Casa v\([^[:space:]]*\).*/\1/p' "$README_FILE" | head -1)"

  [ -n "$README_VERSION" ] || \
    die "Impossibile rilevare la versione in $README_FILE."

  [ "$README_VERSION" = "$VERSION" ] || \
    die "$README_FILE contiene versione $README_VERSION, richiesta $VERSION."
done

echo "Aggiorno i riferimenti remoti..."
git fetch origin main --tags

LOCAL_SHA="$(git rev-parse HEAD)"
REMOTE_SHA="$(git rev-parse origin/main)"

[ "$LOCAL_SHA" = "$REMOTE_SHA" ] || \
  die "main locale non coincide con origin/main. Esegui: git pull --ff-only origin main"

TAG_EXISTS=0

if git rev-parse "$TAG" >/dev/null 2>&1; then
  TAG_EXISTS=1

  TAG_SHA="$(git rev-list -n 1 "$TAG")"

  [ "$TAG_SHA" = "$LOCAL_SHA" ] || \
    die "Il tag $TAG esiste ma punta a un commit diverso da main."

  echo "Il tag $TAG esiste già e punta al commit corretto."
fi

HTTP_CODE="$(curl -sS \
  -o /tmp/inventario-release-check.json \
  -w '%{http_code}' \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "$API/repos/$REPO/releases/tags/$TAG")"

if [ "$HTTP_CODE" = "200" ]; then
  echo
  echo "La GitHub Release $TAG esiste già."
  echo "Nessuna operazione necessaria."
  exit 0
elif [ "$HTTP_CODE" != "404" ]; then
  cat /tmp/inventario-release-check.json
  die "Errore durante la verifica della release. HTTP $HTTP_CODE"
fi

if [ -f "$NOTES_FILE" ]; then
  NOTES="$(cat "$NOTES_FILE")"
else
  NOTES="## Inventario Casa $TAG

Release di Inventario Casa versione $VERSION.

### Compatibilità

- Nessuna modifica automatica al database durante la pubblicazione della release.
- Inventario, fotografie, backup e dati esistenti rimangono invariati."
fi

echo
echo "Controlli superati"
echo "Repository : $REPO"
echo "Branch     : $BRANCH"
echo "Versione   : $VERSION"
echo "Tag        : $TAG"
echo "Commit     : $(git rev-parse --short HEAD)"

if [ "$TAG_EXISTS" -eq 1 ]; then
  echo "Azione     : crea solo la GitHub Release"
else
  echo "Azione     : crea tag e GitHub Release"
fi

echo
echo "Note release:"
echo "----------------------------------------"
echo "$NOTES"
echo "----------------------------------------"
echo

if [ "$TAG_EXISTS" -eq 1 ]; then
  PROMPT="Creare la GitHub Release $TAG usando il tag esistente? [y/N] "
else
  PROMPT="Creare tag e GitHub Release $TAG? [y/N] "
fi

read -r -p "$PROMPT" ANSWER

case "$ANSWER" in
  y|Y|yes|YES) ;;
  *)
    echo "Operazione annullata."
    exit 0
    ;;
esac

if [ "$TAG_EXISTS" -eq 0 ]; then
  echo
  echo "Creo tag $TAG..."
  git tag -a "$TAG" -m "Inventario Casa $TAG"

  echo "Pubblico tag..."
  git push origin "$TAG"
else
  echo
  echo "Uso il tag $TAG già esistente."
fi

python3 - "$TAG" "$NOTES" > /tmp/inventario-release.json <<'PY'
import json
import sys

tag = sys.argv[1]
notes = sys.argv[2]

print(json.dumps({
    "tag_name": tag,
    "name": f"Inventario Casa {tag}",
    "body": notes,
    "draft": False,
    "prerelease": False,
    "make_latest": "true"
}))
PY

echo "Creo GitHub Release..."

HTTP_CODE="$(curl -sS \
  -o /tmp/inventario-release-result.json \
  -w '%{http_code}' \
  -X POST \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "$API/repos/$REPO/releases" \
  -d @/tmp/inventario-release.json)"

if [ "$HTTP_CODE" != "201" ]; then
  echo
  echo "ATTENZIONE: il tag $TAG è stato pubblicato, ma la GitHub Release non è stata creata."
  cat /tmp/inventario-release-result.json
  exit 1
fi

RELEASE_URL="$(python3 - <<'PY'
import json
with open("/tmp/inventario-release-result.json", "r", encoding="utf-8") as f:
    data = json.load(f)
print(data.get("html_url", ""))
PY
)"

echo
echo "========================================"
echo "Release pubblicata correttamente"
echo "Versione : $VERSION"
echo "Tag      : $TAG"
echo "Commit   : $(git rev-parse --short HEAD)"
[ -n "$RELEASE_URL" ] && echo "URL      : $RELEASE_URL"
echo "========================================"
