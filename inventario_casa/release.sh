#!/usr/bin/env sh
set -eu

REPO="gimalugi/inventario-casa"
EXPECTED_BRANCH="main"

echo "=========================================="
echo " Inventario Casa - GitHub Release"
echo "=========================================="
echo

# ---------------------------------------------------------
# Controlli preliminari
# ---------------------------------------------------------

if ! command -v git >/dev/null 2>&1; then
    echo "ERRORE: git non trovato."
    exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
    echo "ERRORE: GitHub CLI (gh) non trovato."
    exit 1
fi

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "ERRORE: questa directory non è un repository Git."
    exit 1
fi

BRANCH="$(git branch --show-current)"

if [ "$BRANCH" != "$EXPECTED_BRANCH" ]; then
    echo "ERRORE: branch corrente '$BRANCH'."
    echo "Per una release devi essere su '$EXPECTED_BRANCH'."
    exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
    echo "ERRORE: GitHub CLI non autenticato."
    echo "Esegui: gh auth login"
    exit 1
fi

# ---------------------------------------------------------
# Versione da config.yaml
# ---------------------------------------------------------

VERSION="$(sed -n 's/^version:[[:space:]]*["'\'']\{0,1\}\([^"'\'']*\)["'\'']\{0,1\}[[:space:]]*$/\1/p' config.yaml | head -1)"

if [ -z "$VERSION" ]; then
    echo "ERRORE: impossibile leggere la versione da config.yaml."
    exit 1
fi

TAG="v$VERSION"

echo "Repository : $REPO"
echo "Branch     : $BRANCH"
echo "Versione   : $VERSION"
echo "Tag        : $TAG"
echo

# ---------------------------------------------------------
# Working tree
# ---------------------------------------------------------

if [ -n "$(git status --porcelain)" ]; then
    echo "ATTENZIONE: ci sono modifiche non committate:"
    echo
    git status --short
    echo
    echo "La release viene interrotta."
    echo "Esegui prima commit delle modifiche."
    exit 1
fi

# ---------------------------------------------------------
# Sincronizzazione remota
# ---------------------------------------------------------

echo "Controllo repository remoto..."
git fetch origin --tags

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse origin/$EXPECTED_BRANCH)"

if [ "$LOCAL" != "$REMOTE" ]; then
    echo
    echo "ATTENZIONE: main locale e origin/main non coincidono."
    echo
    echo "Locale : $LOCAL"
    echo "Remoto : $REMOTE"
    echo
    echo "Esegui git push o git pull prima della release."
    exit 1
fi

# ---------------------------------------------------------
# Controllo tag/release
# ---------------------------------------------------------

if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "ERRORE: il tag $TAG esiste già."
    exit 1
fi

if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
    echo "ERRORE: la release $TAG esiste già su GitHub."
    exit 1
fi

echo
echo "Ultimo commit:"
git log -1 --oneline

echo
printf "Creare e pubblicare la release %s? [y/N] " "$TAG"
read ANSWER

case "$ANSWER" in
    y|Y|yes|YES)
        ;;
    *)
        echo "Operazione annullata."
        exit 0
        ;;
esac

# ---------------------------------------------------------
# Note release
# ---------------------------------------------------------

NOTES_FILE="$(mktemp)"
trap 'rm -f "$NOTES_FILE"' EXIT

if [ -f CHANGELOG.md ]; then
    awk -v ver="$VERSION" '
        $0 ~ "^##[[:space:]]+" ver "[[:space:]]*$" {
            found=1
            next
        }
        found && /^##[[:space:]]+/ {
            exit
        }
        found {
            print
        }
    ' CHANGELOG.md > "$NOTES_FILE"
fi

if [ ! -s "$NOTES_FILE" ]; then
    echo "Release Inventario Casa $TAG" > "$NOTES_FILE"
fi

echo
echo "Note release:"
echo "------------------------------------------"
cat "$NOTES_FILE"
echo "------------------------------------------"

echo
printf "Confermi definitivamente la pubblicazione? [y/N] "
read ANSWER

case "$ANSWER" in
    y|Y|yes|YES)
        ;;
    *)
        echo "Operazione annullata."
        exit 0
        ;;
esac

# ---------------------------------------------------------
# Pubblicazione
# ---------------------------------------------------------

echo
echo "[1/3] Creazione tag $TAG..."
git tag -a "$TAG" -m "Inventario Casa $TAG"

echo "[2/3] Pubblicazione tag..."
if ! git push origin "$TAG"; then
    echo "ERRORE durante il push del tag."
    echo "Il tag locale è stato mantenuto per verifica."
    exit 1
fi

echo "[3/3] Creazione GitHub Release..."
if ! gh release create "$TAG" \
    --repo "$REPO" \
    --title "Inventario Casa $TAG" \
    --latest \
    --notes-file "$NOTES_FILE"
then
    echo
    echo "ERRORE durante la creazione della GitHub Release."
    echo "Il tag $TAG è comunque già stato pubblicato."
    exit 1
fi

echo
echo "=========================================="
echo " RELEASE COMPLETATA"
echo "=========================================="
echo
gh release view "$TAG" \
    --repo "$REPO" \
    --json name,tagName,url \
    --template '{{.name}}{{"\n"}}Tag: {{.tagName}}{{"\n"}}{{.url}}{{"\n"}}'
