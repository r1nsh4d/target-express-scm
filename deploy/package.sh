#!/usr/bin/env bash
#
# Build one archive to upload to the server.
#
#   bash deploy/package.sh
#
# Produces target-express-update.zip in the folder above the project, holding
# exactly the source the server needs and nothing it must not receive.
#
# Deliberately EXCLUDED, because each would do damage:
#   .env.prod                   the server's generated secrets
#   backend/alembic/versions/   the migration history, which lives on the server
#   node_modules, .venv, dist   350 MB, and the venv is Windows-only anyway
#
# The selection comes from git rather than a hand-written list, so it cannot
# drift out of date as files are added.

set -euo pipefail
cd "$(dirname "$0")/.."

NAME="target-express-update"
OUT="../${NAME}.zip"

command -v git >/dev/null || { echo "git is required (it selects the files)" >&2; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "Not a git repository" >&2; exit 1; }

# Pick up anything added since the last packaging run.
git add -A >/dev/null 2>&1 || true

FILES=$(git ls-files)
if [ -z "$FILES" ]; then
  echo "Nothing to package - git has no tracked files" >&2
  exit 1
fi

COUNT=$(printf '%s\n' "$FILES" | wc -l | tr -d ' ')

# ---------------------------------------------------------------------------
# Line endings — refuse to ship CRLF.
#
# This repository is edited on Windows, where git's core.autocrlf=true rewrites
# LF to CRLF on checkout. The archive is unpacked on Linux, where a trailing \r
# is not whitespace, it is a character:
#
#   bash  reads `#!/usr/bin/env bash\r`  -> "$'\r': command not found"
#   dotenv reads `TX_HTTP_PORT=18080\r`  -> a port literally named "18080\r"
#
# .gitattributes pins the working tree to LF, which is the real fix. This is the
# backstop: a developer with an older checkout, or one file that slipped through,
# must not reach the server. It fails the packaging rather than fixing silently,
# because silently rewriting someone's files is its own surprise.
# ---------------------------------------------------------------------------
CRLF_FILES=""
while IFS= read -r f; do
  case "$f" in
    *.png|*.jpg|*.jpeg|*.gif|*.ico|*.webp|*.pdf|*.woff|*.woff2|*.ttf|*.otf) continue ;;
    # A .bat or .ps1 is only ever run by Windows, and wants CRLF.
    *.bat|*.ps1) continue ;;
  esac
  [ -f "$f" ] || continue
  if grep -qU $'\r' "$f" 2>/dev/null; then
    CRLF_FILES="${CRLF_FILES}  $f"$'\n'
  fi
done <<< "$FILES"

if [ -n "$CRLF_FILES" ]; then
  cat >&2 <<EOF

  REFUSING TO PACKAGE - these files have Windows line endings:

$CRLF_FILES
  On Linux a trailing carriage return breaks shell scripts and .env files.
  Fix the whole tree with:

    bash deploy/fix-line-endings.sh

EOF
  exit 1
fi

EXTRACT="tar -xzf"

rm -f "$OUT"
if command -v zip >/dev/null 2>&1; then
  EXTRACT="unzip -o"
  printf '%s\n' "$FILES" | zip -q "$OUT" -@
else
  # Git Bash on Windows often has no zip; tar is always there.
  OUT="../${NAME}.tar.gz"
  rm -f "$OUT"
  git ls-files -z | tar --null -T - -czf "$OUT"
fi

SIZE=$(du -h "$OUT" | cut -f1)
FULL=$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")

cat <<EOF

  Packaged $COUNT files  ($SIZE)
  $FULL

  On the server:

    cd /opt/target-express
    # upload the archive here, then:
    $EXTRACT $(basename "$OUT")
    rm $(basename "$OUT")
    bash deploy.sh

  Extracting over the top replaces source files and leaves .env.prod,
  backend/alembic/versions/ and the database untouched.

EOF
