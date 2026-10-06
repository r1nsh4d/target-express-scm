#!/usr/bin/env bash
# Frontend — the built React app, served by nginx in its own container.
#
#   bash deploy/frontend.sh up          build if needed, then start
#   bash deploy/frontend.sh rebuild     rebuild the image from scratch
#   bash deploy/frontend.sh restart     restart without rebuilding
#   bash deploy/frontend.sh down        stop it
#   bash deploy/frontend.sh status      running? serving?
#   bash deploy/frontend.sh logs [-f]   nginx access and error logs
#   bash deploy/frontend.sh shell       a shell inside the container
#   bash deploy/frontend.sh check       verify the built assets are being served
#   bash deploy/frontend.sh brand       what brand files are in the image
#
# The frontend is built at image build time, so a source change needs
# 'rebuild' — 'restart' alone will serve the previous build.

. "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

# Help must work on a machine with no Docker and no .env.prod.
case "${1:-}" in ""|-h|--help) usage_and_exit ;; esac

require_docker
require_env

HTTP_PORT=$(env_value TX_HTTP_PORT 18080)
PUBLIC_URL=$(env_value PUBLIC_BASE_URL "")

wait_serving() {
  for i in $(seq 1 40); do
    if curl -fsS "http://127.0.0.1:${HTTP_PORT}/" >/dev/null 2>&1; then
      ok "serving after ${i}s"; return 0
    fi
    sleep 1
  done
  dc logs --tail 30 web
  die "the web container is not serving — logs above"
}

case "${1:-}" in

  up)
    bold "Starting the web container"
    dc up -d --build web
    wait_serving
    ok "http://127.0.0.1:${HTTP_PORT}"
    [ -n "$PUBLIC_URL" ] && ok "$PUBLIC_URL"
    ;;

  rebuild)
    bold "Rebuilding the frontend from source"
    # Source changes only reach users through a rebuild: the app is compiled
    # into the image, not read from disk at runtime.
    dc build --no-cache web
    dc up -d web
    wait_serving
    warn "Hard-refresh the browser (Ctrl+Shift+R) — the old bundle may be cached."
    ;;

  restart)
    bold "Restarting the web container"
    warn "This serves the EXISTING build. For source changes use 'rebuild'."
    dc restart web
    wait_serving
    ;;

  down)
    bold "Stopping the web container"
    dc stop web && ok "stopped"
    ;;

  status)
    bold "Web"
    dc ps web
    echo
    if service_running web; then
      code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${HTTP_PORT}/" || echo 000)
      [ "$code" = "200" ] && ok "page returns 200" || warn "page returns $code"

      api=$(curl -s "http://127.0.0.1:${HTTP_PORT}/api/health" || echo '')
      [ -n "$api" ] && ok "API reachable through it: $api" \
        || warn "the /api proxy is not reaching the backend"
    else
      warn "not running"
    fi
    ;;

  logs)
    if [ "${2:-}" = "-f" ]; then dc logs -f web; else dc logs --tail 80 web; fi
    ;;

  shell)
    bold "Shell inside the web container — exit to leave"
    dc exec web sh
    ;;

  check)
    bold "What is actually being served"
    dc exec -T web ls -la /usr/share/nginx/html /usr/share/nginx/html/assets 2>/dev/null | sed 's/^/  /'
    echo
    ok "index.html references:"
    dc exec -T web grep -oE '/assets/[a-zA-Z0-9._-]+' /usr/share/nginx/html/index.html \
      | sort -u | sed 's/^/    /'
    ;;

  brand)
    bold "Brand files in the image"
    if dc exec -T web ls /usr/share/nginx/html/brand 2>/dev/null | grep -q .; then
      dc exec -T web ls -la /usr/share/nginx/html/brand | sed 's/^/  /'
      echo
      dc exec -T web ls /usr/share/nginx/html/brand | grep -q '^logo.svg$' \
        && ok "logo.svg present — the real mark is in use" \
        || warn "no logo.svg — the app is showing the typographic TE fallback"
    else
      warn "no brand folder in the image"
      warn "Put logo.svg, logo-dark.svg and the icons in frontend/public/brand/, then rebuild."
    fi
    ;;

  *) die "Unknown command '$1' — run 'bash deploy/frontend.sh --help'" ;;
esac
