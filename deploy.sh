#!/usr/bin/env bash
#
# Target Express - deploy / update on the server.
#
#   bash deploy.sh              first run, or an update
#   bash deploy.sh --bootstrap  also create the minimum users and one vehicle
#   bash deploy.sh --seed       also load the demo data (Godrej masters, sample trips)
#   bash deploy.sh --check      report only, change nothing
#
# Safe to re-run. Every command is scoped to the `target-express` compose
# project, so nothing here can touch Laam or any other stack on this host.

set -euo pipefail
cd "$(dirname "$0")"

COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"
PROJECT="target-express"
DC="docker compose -f $COMPOSE_FILE --env-file $ENV_FILE -p $PROJECT"

SEED=false
BOOTSTRAP=false
CHECK_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --seed)      SEED=true ;;
    --bootstrap) BOOTSTRAP=true ;;
    --check)     CHECK_ONLY=true ;;
    -h|--help) sed -n '2,13p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

bold()  { printf '\n\033[1m%s\033[0m\n' "$1"; }
ok()    { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn()  { printf '  \033[33m!\033[0m %s\n' "$1"; }
die()   { printf '  \033[31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

# ---------------------------------------------------------------------------
bold "1. Prerequisites"

command -v docker >/dev/null 2>&1 || die "docker is not installed"
docker compose version >/dev/null 2>&1 || die "the docker compose plugin is not installed"
docker info >/dev/null 2>&1 || die "cannot reach the docker daemon (permissions? try sudo)"
ok "docker $(docker --version | awk '{print $3}' | tr -d ,)"
[ -f "$COMPOSE_FILE" ] || die "$COMPOSE_FILE not found - run this from the repo root"

# ---------------------------------------------------------------------------
bold "2. Configuration"

if [ ! -f "$ENV_FILE" ]; then
  [ "$CHECK_ONLY" = true ] && die "$ENV_FILE is missing"
  warn "$ENV_FILE not found - creating it with generated secrets"
  cp .env.prod.example "$ENV_FILE"

  # Generate the three secrets rather than leaving them blank. A deploy that
  # silently comes up on a default key is worse than one that fails.
  for key in SECRET_KEY POSTGRES_PASSWORD S3_SECRET_KEY; do
    if [ "$key" = "SECRET_KEY" ]; then value=$(openssl rand -hex 32)
    else value=$(openssl rand -base64 24 | tr -d '/+=' ); fi
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  done
  chmod 600 "$ENV_FILE"
  ok "secrets generated"
  warn "Edit $ENV_FILE and set PUBLIC_BASE_URL and CORS_ORIGINS to the real hostname."
  warn "Customer tracking links are built from PUBLIC_BASE_URL - wrong value, dead links."
else
  ok "$ENV_FILE present"
fi

# The next line sources this file into the shell. A carriage return at the end
# of a value is not whitespace on Linux — it becomes part of the value, and the
# shell reports `$'\r': command not found` on the first blank line. .env.prod is
# never shipped in the archive (it holds the server's generated secrets), so it
# cannot be fixed by replacing it; it is repaired in place, keeping a backup.
if grep -qU $'\r' "$ENV_FILE" 2>/dev/null; then
  if [ "$CHECK_ONLY" = true ]; then
    warn "$ENV_FILE has Windows line endings and would be repaired on a real run"
  else
    warn "$ENV_FILE has Windows line endings - repairing it"
    cp "$ENV_FILE" "${ENV_FILE}.crlf.bak"
    tr -d '\r' < "${ENV_FILE}.crlf.bak" > "$ENV_FILE"
    chmod 600 "$ENV_FILE" "${ENV_FILE}.crlf.bak"
    ok "repaired (previous copy kept at ${ENV_FILE}.crlf.bak)"

    # POSTGRES_PASSWORD just changed, because the carriage return was part of
    # it. Postgres only reads that variable when it first creates the data
    # directory; after that the password lives in the database. So an existing
    # volume still expects the old value and every query will fail with
    # "password authentication failed" until the role is realigned.
    if docker volume inspect "${PROJECT:-target-express}_tx-db-data" >/dev/null 2>&1; then
      warn "The database already exists and still expects the OLD password."
      warn "Realign it (no data is lost):  bash deploy/db.sh resync-password"
    fi
  fi
fi

# shellcheck disable=SC1090
set -a; . "./$ENV_FILE"; set +a

for key in SECRET_KEY POSTGRES_PASSWORD S3_SECRET_KEY; do
  [ -n "${!key:-}" ] || die "$key is empty in $ENV_FILE"
done
ok "secrets set"

# PUBLIC_BASE_URL is the hostname printed into every customer's tracking link.
# Left at the example value it produces links to a domain nobody owns, and the
# failure is invisible from inside the application - everything looks fine until
# a customer taps a link that goes nowhere. So it is checked, by name, here.
case "${PUBLIC_BASE_URL:-}" in
  ""|*example.com*|*localhost*)
    warn "PUBLIC_BASE_URL is '${PUBLIC_BASE_URL:-unset}'"
    warn "Customer tracking links are built from this. As it stands, every link"
    warn "sent to a customer points at a domain you do not own."
    warn "Set it in $ENV_FILE to the address people actually reach, e.g."
    warn "  PUBLIC_BASE_URL=https://tx.laam.space"
    warn "Then: bash deploy/backend.sh restart"
    ;;
  *) ok "tracking links use ${PUBLIC_BASE_URL}" ;;
esac

HTTP_PORT="${TX_HTTP_PORT:-18080}"

# ---------------------------------------------------------------------------
bold "3. Port check (this host also runs other applications)"

port_holder() {
  if command -v ss >/dev/null 2>&1; then
    ss -lntp 2>/dev/null | awk -v p=":$1" '$4 ~ p"$" {print $NF; exit}'
  fi
}

holder=$(port_holder "$HTTP_PORT" || true)
if [ -n "$holder" ]; then
  # Our own container re-binding the port on an update is expected.
  if docker ps --filter "name=tx-web" --format '{{.Names}}' | grep -q tx-web; then
    ok "port $HTTP_PORT held by our own tx-web (an update, not a clash)"
  else
    die "port $HTTP_PORT is taken by: $holder
     Another application is using it. Change TX_HTTP_PORT in $ENV_FILE and re-run."
  fi
else
  ok "port $HTTP_PORT is free"
fi

existing=$(docker ps -a --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null \
  | grep -v '^$' | grep -v "^${PROJECT}$" | sort -u | tr '\n' ' ' || true)
[ -n "$existing" ] && warn "other compose projects on this host (untouched): $existing"

if [ "$CHECK_ONLY" = true ]; then
  bold "Check complete - nothing was changed."
  exit 0
fi

# ---------------------------------------------------------------------------
bold "4. Build and start"

$DC up -d --build
ok "containers up"

# ---------------------------------------------------------------------------
bold "5. Waiting for the API"

for i in $(seq 1 60); do
  if $DC exec -T api python -c "
import urllib.request,sys
try:
    sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status==200 else 1)
except Exception:
    sys.exit(1)
" >/dev/null 2>&1; then
    ok "API healthy after ${i}s"
    break
  fi
  [ "$i" -eq 60 ] && {
    $DC logs --tail 40 api
    die "API did not come up within 60s - logs above"
  }
  sleep 1
done

# ---------------------------------------------------------------------------
bold "6. Database migrations"

copy_migrations_out() {
  # Out of the container, or the next image rebuild loses the schema history.
  docker cp "${PROJECT}-api-1:/srv/alembic/versions/." backend/alembic/versions/ 2>/dev/null \
    || docker cp "tx-api:/srv/alembic/versions/." backend/alembic/versions/ 2>/dev/null \
    || warn "could not copy the migrations back - do it by hand before the next deploy"
}

mkdir -p backend/alembic/versions

# On the very first deploy there is no migration file at all.
if [ -z "$(ls -A backend/alembic/versions 2>/dev/null | grep -v __pycache__ || true)" ]; then
  warn "no migration files found - generating the initial schema"
  $DC exec -T api alembic revision --autogenerate -m "initial schema"
  copy_migrations_out
  ok "initial migration generated"
fi

# Apply whatever exists. A failure here is almost always a migration generated
# by an earlier, broken deploy that is now jamming every later one, so say that
# rather than letting the traceback be the whole explanation.
if ! $DC exec -T api alembic upgrade head 2>&1 | tee /tmp/tx-upgrade.log; then
  if grep -q "contains null values" /tmp/tx-upgrade.log 2>/dev/null; then
    warn "A migration is trying to add a NOT NULL column to a table that already"
    warn "has rows, without a default for them. That migration can never apply."
    warn ""
    warn "It was generated by an earlier deploy from code that has since been"
    warn "fixed. Remove it and deploy again:"
    warn "  bash deploy/db.sh drop-unapplied"
  fi
  die "could not apply the existing migrations - see above"
fi

# ...and then CHECK, rather than announcing success.
#
# This step used to print "schema up to date" unconditionally straight after
# `upgrade head`. On an update that added columns there was no new migration
# file to apply, so upgrade did nothing, the message was printed anyway, and
# the application started against a schema that no longer matched its models -
# failing on every request with "column does not exist". The deploy reported
# success throughout.
#
# A deploy must not be able to finish quietly with the database out of step.
if $DC exec -T api alembic check >/dev/null 2>&1; then
  ok "schema up to date"
else
  warn "the code expects a schema the database does not have - generating a migration"
  $DC exec -T api alembic revision --autogenerate -m "deploy $(date +%Y%m%d-%H%M)"
  copy_migrations_out
  $DC exec -T api alembic upgrade head

  if $DC exec -T api alembic check >/dev/null 2>&1; then
    ok "schema brought up to date"
    warn "Commit backend/alembic/versions/ - that history now only exists here."
  else
    $DC logs --tail 20 api
    die "the database is still out of step. Run 'bash deploy/db.sh check' and read the output."
  fi
fi

# ---------------------------------------------------------------------------
if [ "$BOOTSTRAP" = true ]; then
  bold "7. Bootstrap"
  # Just the logins and one vehicle. Vendors, customers and trips get created
  # through the application, which is the point of walking the workflow.
  $DC exec -T api python -m app.bootstrap
  warn "Bootstrap logins use the password 'target123' - change them before real use."
fi

if [ "$SEED" = true ]; then
  bold "7. Demo data"
  $DC exec -T api python -m app.seed
  warn "Seeded logins use the password 'target123' - change them before real use."
fi

# ---------------------------------------------------------------------------
bold "Done"

$DC ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || $DC ps

cat <<EOF

  Local:  http://127.0.0.1:${HTTP_PORT}
  Health: curl -s http://127.0.0.1:${HTTP_PORT}/api/health

  Next, if this is the first deploy:
    - point your reverse proxy at 127.0.0.1:${HTTP_PORT}
      (samples in deploy/nginx-site.conf.example and deploy/Caddyfile.example)
    - commit backend/alembic/versions/ so the schema is version controlled

  Logs:   docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} -p ${PROJECT} logs -f api
  Stop:   docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE} -p ${PROJECT} down
          (this stack only - other applications on this host are unaffected)

EOF
