#!/usr/bin/env bash
#
# Shared by db.sh, backend.sh and frontend.sh. Not run directly.
#
# Everything here is scoped to the `target-express` compose project, so no
# command in any of these scripts can reach another stack on the host.

set -euo pipefail

PROJECT="target-express"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env.prod"

# Resolve to the repo root whichever directory the script was called from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

bold() { printf '\n\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
die()  { printf '  \033[31m✗ %s\033[0m\n' "$1" >&2; exit 1; }

require_docker() {
  command -v docker >/dev/null 2>&1 || die "docker is not installed"
  docker compose version >/dev/null 2>&1 || die "the docker compose plugin is missing"
  docker info >/dev/null 2>&1 || die "cannot reach the docker daemon (permissions? try sudo)"
}

require_env() {
  [ -f "$ENV_FILE" ] || die "$ENV_FILE is missing — run 'bash deploy.sh' once to create it"

  # .env.prod holds the server's secrets, so it is never shipped in the archive
  # and never overwritten by an update. That means a carriage return which got
  # into it once stays there forever unless something removes it — and docker
  # compose does not treat \r as whitespace. TX_HTTP_PORT=18080\r becomes a port
  # named "18080\r", and the stack fails to start with no useful message.
  #
  # This is the one file the repository cannot fix by replacing, so it is
  # repaired in place. A backup is kept because it contains generated secrets
  # that exist nowhere else.
  if grep -qU $'\r' "$ENV_FILE" 2>/dev/null; then
    warn "$ENV_FILE had Windows line endings — repairing it"
    cp "$ENV_FILE" "${ENV_FILE}.crlf.bak"
    tr -d '\r' < "${ENV_FILE}.crlf.bak" > "$ENV_FILE"
    chmod 600 "$ENV_FILE" "${ENV_FILE}.crlf.bak"
    ok "repaired (previous copy kept at ${ENV_FILE}.crlf.bak)"
  fi
}

# The only way any of these scripts talks to compose.
dc() {
  docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" -p "$PROJECT" "$@"
}

# Read a value out of .env.prod without exporting the whole file.
env_value() {
  local key="$1" default="${2:-}"
  local line
  line=$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | tail -1 || true)
  if [ -z "$line" ]; then printf '%s' "$default"; else printf '%s' "${line#*=}"; fi
}

# Anything that destroys data asks first, and asks for the word rather than a
# keystroke — 'y' is too easy to hit by accident on a production box.
confirm_destructive() {
  local what="$1"
  printf '\n\033[31mThis will %s.\033[0m\n' "$what"
  printf "Type 'yes' to continue: "
  local reply
  read -r reply
  [ "$reply" = "yes" ] || die "Cancelled"
}

service_running() {
  [ -n "$(dc ps -q "$1" 2>/dev/null)" ]
}

usage_and_exit() {
  sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}
