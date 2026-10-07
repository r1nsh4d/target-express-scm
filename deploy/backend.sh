#!/usr/bin/env bash
# Backend — the FastAPI service.
#
#   bash deploy/backend.sh up            build if needed, then start
#   bash deploy/backend.sh rebuild       rebuild the image from scratch
#   bash deploy/backend.sh restart       restart without rebuilding
#   bash deploy/backend.sh down          stop it
#   bash deploy/backend.sh status        running? healthy?
#   bash deploy/backend.sh logs [-f]     recent logs, -f to follow
#   bash deploy/backend.sh errors        just the tracebacks
#   bash deploy/backend.sh shell         a shell inside the container
#   bash deploy/backend.sh test          run the test suite
#   bash deploy/backend.sh bootstrap     create the 3 logins and one vehicle
#   bash deploy/backend.sh seed          load the full Godrej demo data
#   bash deploy/backend.sh demo          seed + everything that hangs off it
#   bash deploy/backend.sh routes        list every endpoint
#   bash deploy/backend.sh storage       check object storage is reachable
#   bash deploy/backend.sh users         who can sign in, and with what role
#   bash deploy/backend.sh set-password PHONE   set a login's password
#   bash deploy/backend.sh check-password PHONE confirm a password is the right one
#
# Passwords are stored as bcrypt hashes and CANNOT be read back — not by this
# script, not by psql, not by anyone. A forgotten password is reset, never
# recovered. That is the point of hashing them.

. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

# Help must work on a machine with no Docker and no .env.prod.
case "${1:-}" in ""|-h|--help) usage_and_exit ;; esac

require_docker
require_env

HTTP_PORT=$(env_value TX_HTTP_PORT 18080)

wait_healthy() {
  for i in $(seq 1 60); do
    if dc exec -T api python -c "
import urllib.request,sys
try: sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2).status==200 else 1)
except Exception: sys.exit(1)
" >/dev/null 2>&1; then
      ok "healthy after ${i}s"; return 0
    fi
    sleep 1
  done
  dc logs --tail 40 api
  die "the API did not become healthy — logs above"
}


require_module() {
  # The application is COPIED into the image at build time. A file that exists
  # in the working tree after a git pull is NOT in the running container until
  # the image is rebuilt, and the only symptom is "No module named app.x" —
  # which reads like a broken script rather than a stale image.
  local module="$1"
  if ! dc exec -T api python -c "import ${module}" >/dev/null 2>&1; then
    warn "${module} is not in the running container."
    warn "The code is copied into the image when it is built, so a file added by"
    warn "a git pull does not reach the container until it is rebuilt:"
    warn ""
    warn "    bash deploy/backend.sh up"
    warn ""
    die "rebuild first, then run this again"
  fi
}

case "${1:-}" in

  up)
    bold "Starting the API"
    # The API is useless without its database, so bring that first.
    dc up -d db
    dc up -d --build api
    wait_healthy
    ok "http://127.0.0.1:${HTTP_PORT}/api/health"
    ;;

  rebuild)
    bold "Rebuilding the API image from scratch"
    dc build --no-cache api
    dc up -d api
    wait_healthy
    ;;

  restart)
    bold "Restarting the API"
    dc restart api
    wait_healthy
    ;;

  down)
    bold "Stopping the API"
    dc stop api && ok "stopped"
    ;;

  status)
    bold "API"
    dc ps api
    echo
    if service_running api; then
      curl -s "http://127.0.0.1:${HTTP_PORT}/api/health" 2>/dev/null \
        && echo && ok "responding through the web container" \
        || warn "not reachable on ${HTTP_PORT} — is the web container up?"
    else
      warn "not running"
    fi
    ;;

  logs)
    if [ "${2:-}" = "-f" ]; then dc logs -f api; else dc logs --tail 80 api; fi
    ;;

  errors)
    bold "Recent errors"
    # Tracebacks span many lines, so show context rather than matching lines.
    dc logs --tail 400 api 2>&1 | grep -B2 -A12 -E "Traceback|ERROR|Internal Server Error" \
      || ok "no errors in the last 400 lines"
    ;;

  shell)
    bold "Shell inside the API container — exit to leave"
    dc exec api bash 2>/dev/null || dc exec api sh
    ;;

  test)
    bold "Running the test suite"
    # Tests are excluded from the image, so they run from the source on disk.
    dc exec -T api python -m pytest -q 2>/dev/null \
      || warn "tests are not in the image — run them on your own machine instead"
    ;;

  bootstrap)
    bold "Creating the minimum accounts"
    require_module app.bootstrap
    dc exec -T api python -m app.bootstrap
    warn "These use the password 'target123' — change them before real use."
    ;;

  seed)
    bold "Loading the Godrej demo data"
    require_module app.seed
    warn "This adds vendors, vehicles, drivers and worked freights. Not for a live database."
    # Accepts y, Y and yes. The earlier version tested `= "y"`, so pressing Y or
    # typing yes silently cancelled — the same bug that left a migration
    # unapplied on a live box.
    printf "Continue? [y/N] "
    read -r reply
    case "$reply" in [Yy]*) ;; *) die "Cancelled" ;; esac
    dc exec -T api python -m app.seed
    ;;

  demo)
    # Everything a client should see on a walkthrough.
    #
    # `seed` creates the masters and the freights, which leaves most screens
    # saying "no data yet": no bills, so nothing to label; no invoice, no
    # settlement, no saved routes, an empty phonebook. A demo where two screens
    # work and nine are blank is worse than no demo.
    bold "Loading the demo data"
    require_module app.demo
    dc exec -T api python -m app.seed
    dc exec -T api python -m app.demo
    ;;

  routes)
    bold "Endpoints"
    dc exec -T api python -c "
from app.main import app
paths = sorted(app.openapi()['paths'])
for p in paths:
    methods = ','.join(sorted(m.upper() for m in app.openapi()['paths'][p]))
    print(f'  {methods:<22} {p}')
print(f'\n  {len(paths)} endpoints')
"
    ;;

  storage)
    bold "Object storage"
    dc exec -T api python -c "
from app.core.config import settings
from app.services import storage
if not storage.is_configured():
    print('  not configured — set S3_ACCESS_KEY and S3_SECRET_KEY in .env.prod')
    raise SystemExit(1)
print(f'  endpoint: {settings.s3_endpoint_url}')
print(f'  bucket:   {settings.s3_bucket}')
try:
    storage.ensure_bucket()
    print('  reachable, bucket exists')
except Exception as exc:
    raise SystemExit(f'  FAILED: {exc}')
"
    ;;

  users)
    bold "Logins"
    dc exec -T api python -c "
from sqlalchemy import select
from app.db.session import SessionLocal
from app.models.user import User

db = SessionLocal()
rows = db.execute(select(User).order_by(User.role, User.phone)).scalars().all()
if not rows:
    print('  No users yet. Run: bash deploy/backend.sh bootstrap')
    raise SystemExit(0)

print(f\"  {'Phone':<14} {'Name':<24} {'Role':<17} {'Active':<7} Earnings\")
print('  ' + '-' * 72)
for u in rows:
    print(
        f'  {u.phone:<14} {(u.full_name or \"\")[:23]:<24} '
        f'{u.role:<17} {(\"yes\" if u.is_active else \"NO\"):<7} '
        f'{\"yes\" if u.can_view_earnings else \"no\"}'
    )
print(f'\n  {len(rows)} users. The phone number is the username.')
print('  Passwords are bcrypt hashes and cannot be shown. To set one:')
print('    bash deploy/backend.sh set-password <phone>')
"
    ;;

  check-password)
    # Answers "is this the password?" without revealing what the password is.
    # Useful when a login fails and you need to know whether it is the
    # credential or something else — a disabled account, the wrong phone.
    PHONE="${2:-}"
    [ -n "$PHONE" ] || die "Which login? bash deploy/backend.sh check-password 9000000001"

    # Read without echoing, so it does not land in the shell history or scroll
    # back on a shared screen.
    printf 'Password to test for %s: ' "$PHONE"
    read -rs PW; echo
    [ -n "$PW" ] || die "nothing entered"

    dc exec -T -e TX_PHONE="$PHONE" -e TX_PW="$PW" api python -c "
import os
from sqlalchemy import select
from app.core.security import verify_password
from app.db.session import SessionLocal
from app.models.user import User

db = SessionLocal()
user = db.execute(
    select(User).where(User.phone == os.environ['TX_PHONE'])
).scalar_one_or_none()

if user is None:
    raise SystemExit('  No login with that phone number.')
if verify_password(os.environ['TX_PW'], user.hashed_password):
    print(f'  CORRECT — {user.full_name} ({user.role})')
    if not user.is_active:
        raise SystemExit('  ...but the account is DEACTIVATED, so sign-in will still fail.')
else:
    raise SystemExit('  WRONG password for that login.')
"
    ;;

  set-password)
    PHONE="${2:-}"
    [ -n "$PHONE" ] || die "Which login? bash deploy/backend.sh set-password 9000000001"

    printf 'New password for %s: ' "$PHONE"
    read -rs PW; echo
    printf 'Repeat it: '
    read -rs PW2; echo

    [ -n "$PW" ] || die "nothing entered"
    [ "$PW" = "$PW2" ] || die "the two entries do not match"
    [ "${#PW}" -ge 6 ] || die "use at least 6 characters"

    # Passed as environment variables, not as argv: arguments are visible to
    # every process on the box through /proc, and land in the shell history.
    dc exec -T -e TX_PHONE="$PHONE" -e TX_PW="$PW" api python -c "
import os
from sqlalchemy import select
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User

db = SessionLocal()
user = db.execute(
    select(User).where(User.phone == os.environ['TX_PHONE'])
).scalar_one_or_none()

if user is None:
    raise SystemExit('  No login with that phone number. Try: bash deploy/backend.sh users')

user.hashed_password = hash_password(os.environ['TX_PW'])
db.commit()
print(f'  Password set for {user.full_name} ({user.role}).')
if not user.is_active:
    print('  NOTE: this account is deactivated, so it still cannot sign in.')
" && ok "done — sign in with $PHONE and the new password"
    ;;

  *) die "Unknown command '$1' — run 'bash deploy/backend.sh --help'" ;;
esac
