#!/usr/bin/env bash
#
# Rebuild .env.prod from the running containers.
#
#   bash deploy/recover-env.sh            write .env.prod
#   bash deploy/recover-env.sh --show     print it, write nothing
#
# .env.prod holds secrets that were GENERATED on this server and exist nowhere
# else: the database password, the JWT signing key, the object storage keys. It
# is deliberately not in the repository and not in the deployment archive.
#
# Which means deleting the project directory destroys them — and without
# POSTGRES_PASSWORD the application cannot open the database volume that still
# holds every freight, invoice and settlement.
#
# The one saving grace is that a running container keeps its environment. This
# reads it back out of the live processes and reconstructs the file.
#
# It only works WHILE THE CONTAINERS ARE STILL UP. Recreating them without
# .env.prod starts them with empty values and the real ones are gone, so run
# this before any compose command.

set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE=".env.prod"
SHOW_ONLY=false
[ "${1:-}" = "--show" ] && SHOW_ONLY=true

red()  { printf '\033[31m  %s\033[0m\n' "$*" >&2; }
ok()   { printf '\033[32m  ✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[33m  ! %s\033[0m\n' "$*"; }
die()  { red "$*"; exit 1; }

command -v docker >/dev/null || die "docker is not available"

for c in tx-api tx-db; do
  docker inspect "$c" >/dev/null 2>&1 \
    || die "$c does not exist. The environment cannot be recovered from a container that is gone."
  [ "$(docker inspect -f '{{.State.Running}}' "$c")" = "true" ] \
    || warn "$c is not running — values may still be readable from its config"
done

# Read one variable out of a container's environment. docker inspect rather than
# `exec env`, so it works even if the container is stopped.
from_container() {
  local container="$1" key="$2"
  docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$container" 2>/dev/null \
    | sed -n "s/^${key}=//p" | head -1
}

POSTGRES_USER=$(from_container tx-db POSTGRES_USER)
POSTGRES_PASSWORD=$(from_container tx-db POSTGRES_PASSWORD)
POSTGRES_DB=$(from_container tx-db POSTGRES_DB)

SECRET_KEY=$(from_container tx-api SECRET_KEY)
PUBLIC_BASE_URL=$(from_container tx-api PUBLIC_BASE_URL)
CORS_ORIGINS=$(from_container tx-api CORS_ORIGINS)
ENVIRONMENT=$(from_container tx-api ENVIRONMENT)
S3_ENDPOINT_URL=$(from_container tx-api S3_ENDPOINT_URL)
S3_REGION=$(from_container tx-api S3_REGION)
S3_ACCESS_KEY=$(from_container tx-api S3_ACCESS_KEY)
S3_SECRET_KEY=$(from_container tx-api S3_SECRET_KEY)
S3_BUCKET=$(from_container tx-api S3_BUCKET)
S3_PUBLIC_BASE_URL=$(from_container tx-api S3_PUBLIC_BASE_URL)
ANTHROPIC_API_KEY=$(from_container tx-api ANTHROPIC_API_KEY)

# The password is the one that cannot be regenerated: it is baked into the
# database volume. A SECRET_KEY can be replaced at the cost of signing everyone
# out; this cannot be replaced at all without a dump and restore.
[ -n "$POSTGRES_PASSWORD" ] || die "POSTGRES_PASSWORD was not readable from tx-db — do not recreate the containers, and say so"

# Which host port the web container is published on.
TX_HTTP_PORT=$(docker port tx-web 80 2>/dev/null | sed -n 's/.*:\([0-9]*\)$/\1/p' | head -1)
TX_HTTP_PORT=${TX_HTTP_PORT:-18080}

RECOVERED=$(cat <<EOF
# Recovered from the running containers on $(date -u '+%Y-%m-%d %H:%M UTC').
#
# These values were generated on this server and exist nowhere else. Back this
# file up somewhere outside /opt before the next time the directory is replaced:
#   cp .env.prod /root/env.prod.backup

TX_HTTP_PORT=${TX_HTTP_PORT}
TX_DB_PORT=55432
TX_MINIO_CONSOLE_PORT=19001

POSTGRES_USER=${POSTGRES_USER:-targetexpress}
POSTGRES_DB=${POSTGRES_DB:-targetexpress}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

SECRET_KEY=${SECRET_KEY}
ENVIRONMENT=${ENVIRONMENT:-production}

PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-}
CORS_ORIGINS=${CORS_ORIGINS:-}

S3_ENDPOINT_URL=${S3_ENDPOINT_URL:-}
S3_REGION=${S3_REGION:-}
S3_ACCESS_KEY=${S3_ACCESS_KEY:-}
S3_SECRET_KEY=${S3_SECRET_KEY:-}
S3_BUCKET=${S3_BUCKET:-}
S3_PUBLIC_BASE_URL=${S3_PUBLIC_BASE_URL:-}

ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
EOF
)

if [ "$SHOW_ONLY" = true ]; then
  printf '%s\n' "$RECOVERED"
  exit 0
fi

if [ -f "$ENV_FILE" ]; then
  cp "$ENV_FILE" "${ENV_FILE}.before-recover"
  warn "$ENV_FILE existed — the previous copy is at ${ENV_FILE}.before-recover"
fi

printf '%s\n' "$RECOVERED" > "$ENV_FILE"
chmod 600 "$ENV_FILE"

ok "wrote $ENV_FILE"
ok "database password recovered (${#POSTGRES_PASSWORD} characters)"
[ -n "$SECRET_KEY" ] && ok "SECRET_KEY recovered" || warn "SECRET_KEY was empty — sessions will need a new one"
[ -n "$S3_ACCESS_KEY" ] && ok "object storage keys recovered" || warn "no S3 keys were set"

case "${PUBLIC_BASE_URL:-}" in
  ""|*example.com*|*localhost*)
    warn "PUBLIC_BASE_URL is '${PUBLIC_BASE_URL:-unset}' — customer tracking links point nowhere real"
    warn "Set it to the address people actually reach, then: bash deploy/backend.sh restart"
    ;;
esac

echo
warn "Back it up somewhere the project directory cannot take with it:"
echo "    cp $ENV_FILE /root/env.prod.backup"
