#!/usr/bin/env bash
# Database — Postgres, migrations and backups.
#
#   bash deploy/db.sh up               start Postgres
#   bash deploy/db.sh down             stop it (data is kept)
#   bash deploy/db.sh status           is it running, and how big
#   bash deploy/db.sh migrate          apply any pending migrations
#   bash deploy/db.sh sync             bring the database in step with the code
#   bash deploy/db.sh drop-unapplied   remove migrations outside the applied history
#   bash deploy/db.sh make-baseline    one migration that builds the schema from empty
#   bash deploy/db.sh rebuild-history  restart the history from the live schema
#   bash deploy/db.sh makemigration    generate one from the models, then apply
#   bash deploy/db.sh check            report schema drift without changing anything
#   bash deploy/db.sh backup           dump to backups/ and prune old ones
#   bash deploy/db.sh restore FILE     replace the data with a dump  (destructive)
#   bash deploy/db.sh psql             open a SQL shell
#   bash deploy/db.sh tables           list the tables and their row counts
#   bash deploy/db.sh resync-password  make the DB role match .env.prod
#   bash deploy/db.sh reset            drop everything and rebuild  (destructive)

. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

# Help must work on a machine with no Docker and no .env.prod.
case "${1:-}" in ""|-h|--help) usage_and_exit ;; esac

require_docker
require_env

DB_USER=$(env_value POSTGRES_USER targetexpress)
DB_NAME=$(env_value POSTGRES_DB targetexpress)
BACKUP_DIR="backups"
KEEP_DAYS=14

psql_q() { dc exec -T db psql -U "$DB_USER" -d "$DB_NAME" -qtAX -c "$1"; }

# Migrations run inside the api container, which is where alembic lives.
alembic_in_api() {
  service_running api || die "the api container is not running — 'bash deploy/backend.sh up' first"
  dc exec -T api alembic "$@"
}

case "${1:-}" in

  up)
    bold "Starting Postgres"
    dc up -d db
    for i in $(seq 1 40); do
      if dc exec -T db pg_isready -U "$DB_USER" >/dev/null 2>&1; then
        ok "ready after ${i}s"; exit 0
      fi
      [ "$i" -eq 40 ] && { dc logs --tail 30 db; die "Postgres did not come up"; }
      sleep 1
    done
    ;;

  down)
    bold "Stopping Postgres"
    # No -v: the volume, and therefore the data, stays.
    dc stop db && ok "stopped (data kept)"
    ;;

  status)
    bold "Postgres"
    dc ps db
    if service_running db; then
      echo
      ok "size: $(psql_q "SELECT pg_size_pretty(pg_database_size('$DB_NAME'));")"
      ok "tables: $(psql_q "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")"
      ok "schema version: $(psql_q "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null || echo 'none')"
    fi
    ;;

  migrate)
    bold "Applying migrations"
    alembic_in_api upgrade head
    ok "schema up to date"
    ;;

  makemigration)
    MSG="${2:-schema update}"
    bold "Generating a migration from the models"
    alembic_in_api revision --autogenerate -m "$MSG"

    # Copy it out of the container, or the next rebuild loses it.
    mkdir -p backend/alembic/versions
    docker cp "tx-api:/srv/alembic/versions/." backend/alembic/versions/ 2>/dev/null \
      && ok "copied into backend/alembic/versions/" \
      || warn "could not copy it out — do it by hand before rebuilding"

    warn "Autogenerate is a draft, not an answer — read the file if the change was subtle."
    # Applying is the DEFAULT, and the old behaviour here caused a live outage.
    # It prompted [y/N] and tested `= "y"`, so pressing Enter — or typing Y, or
    # yes — all silently skipped the apply. The migration sat unapplied while
    # the running application threw "column does not exist" on every request.
    # Not applying is the deliberate act; it should never be the accidental one.
    printf "Apply it now? [Y/n] "
    read -r reply
    case "${reply:-y}" in
      [Nn]*)
        warn "NOT applied."
        warn "The application will fail until you run 'bash deploy/db.sh migrate'."
        ;;
      *) alembic_in_api upgrade head && ok "applied" ;;
    esac
    ;;

  drop-unapplied)
    # Delete migration files that are NOT part of the applied history.
    #
    # A migration that cannot run — most commonly one adding a NOT NULL column
    # to a populated table with no default — is left on disk after it fails and
    # then jams every later deploy, because the next run retries that same file
    # before it can generate a corrected one.
    #
    # The first version of this command was dangerously wrong. It treated
    # alembic_version as a list of everything ever applied, when it holds only
    # the CURRENT revision. Every ancestor therefore looked unapplied, and it
    # deleted the initial-schema file out from under a working database, leaving
    # a hole in the chain that no later command could walk past.
    #
    # The correct question is not "is this revision in alembic_version" but
    # "is this revision an ancestor of where the database is". Alembic can
    # answer that itself, so it is asked rather than guessed at.
    bold "Removing migration files outside the applied history"
    service_running api || die "the api container is not running — 'bash deploy/backend.sh up' first"

    dc exec -T api python -c "
import os, re
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text

engine = create_engine(os.environ['DATABASE_URL'])
with engine.connect() as conn:
    try:
        current = conn.execute(text('SELECT version_num FROM alembic_version')).scalar()
    except Exception:
        current = None

print(f'  database is at: {current or \"(nothing applied)\"}')

folder = '/srv/alembic/versions'

# Everything from the current revision back to the beginning. These files are
# the history of the live database and must never be removed.
keep = set()
if current:
    try:
        script = ScriptDirectory.from_config(Config('/srv/alembic.ini'))
        keep = {rev.revision for rev in script.iterate_revisions(current, 'base')}
    except Exception as exc:
        raise SystemExit(
            f'  cannot read the migration history ({exc}).\n'
            '  The chain is already broken - use: bash deploy/db.sh rebuild-history'
        )

print(f'  protected (the applied history): {len(keep)} revision(s)')

removed = []
for name in sorted(os.listdir(folder)):
    if not name.endswith('.py'):
        continue
    path = os.path.join(folder, name)
    found = re.search(r'''^revision(?::\s*str)?\s*=\s*['\\\"]([^'\\\"]+)''', open(path).read(), re.M)
    if not found or found.group(1) in keep:
        continue
    os.remove(path)
    removed.append(f'{name}  ({found.group(1)})')

if removed:
    print('  removed:')
    for line in removed:
        print(f'    {line}')
else:
    print('  nothing to remove')
" || die "could not inspect the migration history - see above"

    bold "Syncing the local copy"
    rm -rf backend/alembic/versions
    mkdir -p backend/alembic/versions
    docker cp "tx-api:/srv/alembic/versions/." backend/alembic/versions/ 2>/dev/null \
      && ok "backend/alembic/versions/ matches the container" \
      || warn "could not copy back — check backend/alembic/versions/ by hand"

    ok "now run: bash deploy.sh"
    ;;

  rebuild-history)
    # Start the migration history again from where the database actually is.
    #
    # For when the chain is broken beyond walking: a file is missing, or a
    # revision points at a parent that no longer exists, and every alembic
    # command dies with KeyError before it can do anything useful.
    #
    # This does NOT touch the schema. It throws away the migration FILES and the
    # alembic_version pointer, then asks alembic to diff the models against the
    # live database and write one migration containing whatever is genuinely
    # missing. Tables that already exist are not in that diff, so nothing is
    # recreated and no data is touched.
    #
    # The cost is real and worth stating: the step-by-step history is gone,
    # replaced by one baseline. The schema is unchanged, and a backup is taken
    # first regardless.
    bold "Rebuilding the migration history from the live schema"
    service_running api || die "the api container is not running — 'bash deploy/backend.sh up' first"

    confirm_destructive "DISCARD the migration history and rebuild it from the current database (the schema and all data are left alone)"

    bold "Backing up first"
    "$0" backup

    bold "1. Removing the broken migration files"
    dc exec -T api sh -c 'rm -f /srv/alembic/versions/*.py' && ok "cleared"
    rm -rf backend/alembic/versions
    mkdir -p backend/alembic/versions

    bold "2. Clearing the revision pointer"
    psql_q "DROP TABLE IF EXISTS alembic_version;" >/dev/null && ok "cleared"

    bold "3. Writing one migration for whatever the database is missing"
    dc exec -T api alembic revision --autogenerate -m "baseline from live schema" \
      || die "could not generate the baseline"

    bold "4. Applying it"
    dc exec -T api alembic upgrade head || die "could not apply the baseline - read the error above"

    bold "5. Copying the history out"
    docker cp "tx-api:/srv/alembic/versions/." backend/alembic/versions/ 2>/dev/null \
      && ok "backend/alembic/versions/ now holds the baseline — commit it" \
      || warn "could not copy it out; do it by hand before rebuilding the image"

    bold "Verifying"
    if dc exec -T api alembic check >/dev/null 2>&1; then
      ok "the database matches the models"
    else
      die "still out of step — run 'bash deploy/db.sh check' and read the output"
    fi
    ;;

  make-baseline)
    # Produce a migration that can build the schema from NOTHING.
    #
    # This exists because `rebuild-history` produced something that looked like
    # a baseline and was not. It autogenerates against the LIVE database, so
    # everything already there is absent from the diff: the file it wrote
    # created four tables out of thirty-five. Run against an empty database it
    # would have produced a schema missing almost everything, and nobody would
    # have found out until they actually needed it.
    #
    # The fix is to diff the models against a genuinely empty database. So this
    # makes one, on the same Postgres, autogenerates against THAT, and throws it
    # away. The live database is then stamped with the new revision, because its
    # tables already exist and must not be recreated.
    #
    # Nothing touches the real schema. The only write to it is one row in
    # alembic_version.
    bold "Building a complete baseline migration"
    service_running api || die "the api container is not running"
    service_running db || die "Postgres is not running"

    confirm_destructive "REPLACE the migration history with a single complete baseline (the schema and all data are left alone)"

    bold "Backing up first"
    "$0" backup

    TMPDB="tx_baseline_tmp"
    STASH="/srv/alembic/_versions_stash"

    bold "1. Making an empty database to diff against"
    dc exec -T db psql -U "$DB_USER" -d postgres -qtAX \
      -c "DROP DATABASE IF EXISTS ${TMPDB};" >/dev/null
    dc exec -T db psql -U "$DB_USER" -d postgres -qtAX \
      -c "CREATE DATABASE ${TMPDB};" >/dev/null || die "could not create ${TMPDB}"
    ok "created ${TMPDB}"

    bold "2. Setting the existing migrations aside"
    dc exec -T api sh -c "mkdir -p ${STASH} && mv /srv/alembic/versions/*.py ${STASH}/ 2>/dev/null; true"
    ok "stashed"

    bold "3. Writing the baseline against the empty database"
    # DATABASE_URL is rebuilt here so alembic diffs the models against TMPDB.
    # env.py reads it, so nothing else needs to change.
    if ! dc exec -T api sh -c "
         DATABASE_URL=\$(python -c \"
import os, re
url = os.environ['DATABASE_URL']
print(re.sub(r'/[^/?]+(\\\\?|\$)', '/${TMPDB}\\\\1', url, count=1))
\") alembic revision --autogenerate -m 'complete baseline'"; then
      warn "generation failed — putting the old migrations back"
      dc exec -T api sh -c "mv ${STASH}/*.py /srv/alembic/versions/ 2>/dev/null; true"
      dc exec -T db psql -U "$DB_USER" -d postgres -qtAX -c "DROP DATABASE IF EXISTS ${TMPDB};" >/dev/null
      die "could not generate the baseline"
    fi

    bold "4. Checking it actually covers everything"
    dc exec -T api python -c "
import os, re
from app.models import Base

folder = '/srv/alembic/versions'
files = [f for f in os.listdir(folder) if f.endswith('.py')]
if len(files) != 1:
    raise SystemExit(f'  expected one baseline, found {len(files)}')

text = open(os.path.join(folder, files[0])).read()
created = set(re.findall(r\"op\.create_table\('([^']+)'\", text))
wanted = set(Base.metadata.tables) - {'alembic_version'}

missing = wanted - created
if missing:
    raise SystemExit(f'  INCOMPLETE - {len(missing)} table(s) missing: {sorted(missing)}')

print(f'  creates all {len(created)} tables')
print(f'  file: {files[0]}')
" || {
      warn "the generated baseline is incomplete — putting the old migrations back"
      dc exec -T api sh -c "rm -f /srv/alembic/versions/*.py; mv ${STASH}/*.py /srv/alembic/versions/ 2>/dev/null; true"
      dc exec -T db psql -U "$DB_USER" -d postgres -qtAX -c "DROP DATABASE IF EXISTS ${TMPDB};" >/dev/null
      die "baseline rejected — nothing was changed"
    }

    bold "5. Dropping the scratch database"
    dc exec -T db psql -U "$DB_USER" -d postgres -qtAX \
      -c "DROP DATABASE IF EXISTS ${TMPDB};" >/dev/null && ok "dropped"
    dc exec -T api sh -c "rm -rf ${STASH}"

    bold "6. Stamping the live database"
    # Stamp, not upgrade. The tables are already there; running the baseline
    # against them would fail on the first CREATE TABLE.
    psql_q "DROP TABLE IF EXISTS alembic_version;" >/dev/null
    dc exec -T api alembic stamp head || die "could not stamp the live database"
    ok "stamped at $(psql_q "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null || echo '?')"

    bold "7. Copying it out"
    rm -rf backend/alembic/versions
    mkdir -p backend/alembic/versions
    docker cp "tx-api:/srv/alembic/versions/." backend/alembic/versions/ 2>/dev/null \
      && ok "backend/alembic/versions/ holds the complete baseline — COMMIT IT" \
      || warn "could not copy it out; do it by hand"

    bold "Verifying"
    if dc exec -T api alembic check >/dev/null 2>&1; then
      ok "the database matches the models, and the baseline can rebuild it from empty"
    else
      die "still out of step — run 'bash deploy/db.sh check'"
    fi
    ;;

  sync)
    # One command, because two was one too many.
    #
    # Generating a migration and applying it were separate steps with a prompt
    # in between. On a live box the prompt was skipped, the schema stayed
    # behind, and every request failed. This does the whole thing and ends by
    # proving there is no drift left.
    MSG="${2:-schema update}"

    bold "1. Applying anything already generated"
    alembic_in_api upgrade head && ok "up to date with the migrations on disk"

    bold "2. Checking the database against the models"
    if alembic_in_api check >/dev/null 2>&1; then
      ok "no drift — nothing to generate"
    else
      warn "the models and the database differ — generating a migration"
      alembic_in_api revision --autogenerate -m "$MSG"

      mkdir -p backend/alembic/versions
      if docker cp "tx-api:/srv/alembic/versions/." backend/alembic/versions/ 2>/dev/null; then
        ok "copied into backend/alembic/versions/ — commit these"
      else
        warn "could not copy it out; do it by hand before rebuilding the image"
      fi

      bold "3. Applying it"
      alembic_in_api upgrade head && ok "applied"
    fi

    bold "Verifying"
    if alembic_in_api check >/dev/null 2>&1; then
      ok "the database matches the models"
      ok "schema version: $(psql_q "SELECT version_num FROM alembic_version LIMIT 1;" 2>/dev/null || echo '?')"
    else
      die "still out of step — run 'bash deploy/db.sh check' and read the output"
    fi
    ;;

  check)
    bold "Checking for drift between the models and the database"
    alembic_in_api check 2>/dev/null && ok "no drift — the schema matches the models" || {
      warn "The models and the database differ."
      warn "Run 'bash deploy/db.sh makemigration \"what changed\"' to capture it."
    }
    ;;

  backup)
    bold "Backing up"
    mkdir -p "$BACKUP_DIR"
    FILE="$BACKUP_DIR/${DB_NAME}-$(date +%F_%H%M).sql.gz"
    dc exec -T db pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$FILE"
    ok "$FILE ($(du -h "$FILE" | cut -f1))"

    # Keep a fortnight. A backup nobody prunes eventually fills the disk, which
    # takes the database down — the thing the backup was for.
    find "$BACKUP_DIR" -name "${DB_NAME}-*.sql.gz" -mtime +$KEEP_DAYS -delete 2>/dev/null || true
    ok "kept the last $KEEP_DAYS days ($(ls -1 "$BACKUP_DIR" | wc -l | tr -d ' ') files)"
    ;;

  restore)
    FILE="${2:-}"
    [ -n "$FILE" ] || die "Give the dump to restore: bash deploy/db.sh restore backups/....sql.gz"
    [ -f "$FILE" ] || die "$FILE not found"

    confirm_destructive "REPLACE every row in '$DB_NAME' with the contents of $FILE"

    bold "Restoring from $FILE"
    dc exec -T db psql -U "$DB_USER" -d postgres -c \
      "DROP DATABASE IF EXISTS $DB_NAME WITH (FORCE); CREATE DATABASE $DB_NAME;"
    gunzip -c "$FILE" | dc exec -T db psql -U "$DB_USER" -d "$DB_NAME" >/dev/null
    ok "restored"
    warn "Restart the API so it picks up fresh connections: bash deploy/backend.sh restart"
    ;;

  psql)
    bold "SQL shell — \\q to leave"
    dc exec db psql -U "$DB_USER" -d "$DB_NAME"
    ;;

  tables)
    bold "Tables"
    psql_q "
      SELECT relname, n_live_tup
      FROM pg_stat_user_tables
      ORDER BY n_live_tup DESC, relname;
    " | awk -F'|' '{ printf "  %-28s %s\n", $1, $2 }'
    ;;

  resync-password)
    # POSTGRES_PASSWORD is only read on the FIRST start of a data volume. After
    # that the role's password lives in the database, and changing .env.prod
    # changes only what the API sends — so the two drift apart and every request
    # fails with "password authentication failed for user".
    #
    # This realigns them without touching a row. The alternative, deleting the
    # volume, would take the data with it.
    bold "Re-syncing the database role with $ENV_FILE"
    service_running db || die "Postgres is not running — 'bash deploy/db.sh up' first"

    PW=$(env_value POSTGRES_PASSWORD "")
    [ -n "$PW" ] || die "POSTGRES_PASSWORD is empty in $ENV_FILE"

    # Connections over the container's unix socket are trusted, so this needs no
    # password — which is the point, since the password is what is broken.
    #
    # The statement goes in on STDIN, not through -c. psql only interpolates its
    # :'name' variables in input it parses itself; a -c string is handed to the
    # server verbatim, so the colon arrives as SQL and the server rejects it.
    #
    # :'pw' is worth the trouble: psql quotes and escapes the value, so a
    # password containing a quote or a backslash cannot break out of the
    # statement. Building the SQL by string concatenation here would be an
    # injection into the one command that resets a database credential.
    #
    # ON_ERROR_STOP is what makes a failure a failure. Without it psql prints
    # the error and still exits 0, so this would report success and restart the
    # API against a password that was never changed.
    printf '%s\n' "ALTER USER \"$DB_USER\" WITH PASSWORD :'pw';" \
      | dc exec -T db psql -U "$DB_USER" -d postgres -qtAX \
          -v ON_ERROR_STOP=1 -v pw="$PW" >/dev/null \
      || die "could not change the role password — inspect with 'bash deploy/db.sh psql'"

    ok "role '$DB_USER' now uses the password in $ENV_FILE"

    # The API holds a pool of connections opened with the old credentials.
    if service_running api; then
      bold "Restarting the API so its connection pool reconnects"
      dc restart api >/dev/null
      ok "restarted"
    else
      warn "Start the API: bash deploy/backend.sh up"
    fi
    ;;

  reset)
    confirm_destructive "DESTROY the database and every freight, invoice and photo record in it"
    bold "Backing up first — a reset without one is just data loss"
    "$0" backup

    bold "Rebuilding the database"
    dc stop db >/dev/null
    dc rm -f db >/dev/null
    docker volume rm "${PROJECT}_tx-db-data" >/dev/null 2>&1 || true
    "$0" up
    warn "Now run: bash deploy/backend.sh up && bash deploy/db.sh migrate"
    ;;

  *) die "Unknown command '$1' — run 'bash deploy/db.sh --help'" ;;
esac
