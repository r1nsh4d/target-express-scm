#!/usr/bin/env bash
# Preflight check for a shared Hetzner host.
#
# Read-only. Reports what is already running so the Target Express stack can be
# slotted in without disturbing anything else (e.g. Laam).
#
#   bash deploy/preflight.sh

set -uo pipefail

# Ports the Target Express stack would like to bind, all on 127.0.0.1.
WANTED_PORTS=(18080 18000 55432 19000 19001)

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32mfree\033[0m     %s\n' "$1"; }
busy() { printf '  \033[31mIN USE\033[0m   %s  <- %s\n' "$1" "$2"; }

bold "== Host =="
echo "  $(uname -a)"
echo "  uptime:$(uptime -p 2>/dev/null || true)"
echo

bold "== Memory and disk =="
free -h 2>/dev/null | sed 's/^/  /'
echo
df -h / 2>/dev/null | sed 's/^/  /'
echo

bold "== Docker =="
if command -v docker >/dev/null 2>&1; then
  echo "  $(docker --version)"
  echo "  compose: $(docker compose version --short 2>/dev/null || echo 'plugin not found')"
  echo
  echo "  Running containers:"
  docker ps --format '    {{.Names}}\t{{.Image}}\t{{.Ports}}' 2>/dev/null || echo "    (cannot list - permission?)"
  echo
  echo "  Compose projects already on this host:"
  docker ps -a --format '{{.Label "com.docker.compose.project"}}' 2>/dev/null \
    | grep -v '^$' | sort -u | sed 's/^/    /' || echo "    (none)"
  echo
  echo "  Volumes:"
  docker volume ls --format '    {{.Name}}' 2>/dev/null | head -30
else
  echo "  docker not installed"
fi
echo

bold "== Ports Target Express wants (127.0.0.1) =="
for port in "${WANTED_PORTS[@]}"; do
  holder=""
  if command -v ss >/dev/null 2>&1; then
    holder=$(ss -lntp 2>/dev/null | awk -v p=":$port" '$4 ~ p"$" {print $NF; exit}')
  elif command -v netstat >/dev/null 2>&1; then
    holder=$(netstat -lntp 2>/dev/null | awk -v p=":$port" '$4 ~ p"$" {print $NF; exit}')
  fi
  if [ -n "$holder" ]; then busy "$port" "$holder"; else ok "$port"; fi
done
echo

bold "== Everything currently listening =="
if command -v ss >/dev/null 2>&1; then
  ss -lntp 2>/dev/null | sed 's/^/  /'
else
  netstat -lntp 2>/dev/null | sed 's/^/  /'
fi
echo

bold "== Reverse proxy =="
for svc in nginx caddy traefik apache2 haproxy; do
  if systemctl is-active --quiet "$svc" 2>/dev/null; then
    echo "  $svc: ACTIVE"
  elif command -v "$svc" >/dev/null 2>&1; then
    echo "  $svc: installed, not running as a systemd unit"
  fi
done
if docker ps --format '{{.Image}}' 2>/dev/null | grep -Eiq 'nginx|caddy|traefik'; then
  echo "  a proxy appears to run as a container:"
  docker ps --format '    {{.Names}}\t{{.Image}}\t{{.Ports}}' 2>/dev/null \
    | grep -Ei 'nginx|caddy|traefik'
fi
echo
echo "  nginx sites enabled:"
ls -1 /etc/nginx/sites-enabled/ 2>/dev/null | sed 's/^/    /' || echo "    (none or no access)"
echo
echo "  Caddyfile:"
ls -1 /etc/caddy/Caddyfile 2>/dev/null | sed 's/^/    /' || echo "    (none)"
echo

bold "== Existing PostgreSQL =="
if command -v psql >/dev/null 2>&1; then
  echo "  host psql: $(psql --version)"
else
  echo "  no host psql (fine - the stack ships its own in a container)"
fi
echo

bold "== Done =="
echo "Paste this output back and the compose ports, proxy config and deploy steps"
echo "will be tailored to what is actually free on this machine."
