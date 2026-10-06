#!/usr/bin/env bash
#
# Push the source to the server.
#
#   bash deploy/push.sh root@135.181.31.231
#   bash deploy/push.sh root@host /opt/target-express      # custom target
#   bash deploy/push.sh root@host /opt/target-express --dry # list files, send nothing
#
# Sends only what git tracks, so node_modules, the local .venv, dist/ and every
# .env file are excluded by .gitignore rather than by a list that drifts out of
# date. Around 2 MB rather than 350 MB.
#
# Uses tar over ssh because rsync is often absent on a Windows workstation.

set -euo pipefail
cd "$(dirname "$0")/.."

REMOTE="${1:-}"
TARGET="${2:-/opt/target-express}"
DRY="${3:-}"

if [ -z "$REMOTE" ]; then
  echo "Usage: bash deploy/push.sh user@host [/opt/target-express] [--dry]" >&2
  exit 2
fi

command -v git >/dev/null || { echo "git is required (it decides what gets sent)" >&2; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "Not a git repository" >&2; exit 1; }

# Staged and tracked files. Works before the first commit, which is the state
# this repo is in.
FILES=$(git ls-files)
if [ -z "$FILES" ]; then
  echo "git has no tracked files - run 'git add -A' first" >&2
  exit 1
fi

COUNT=$(printf '%s\n' "$FILES" | wc -l | tr -d ' ')
echo "Sending $COUNT files to $REMOTE:$TARGET"

if [ "$DRY" = "--dry" ]; then
  printf '%s\n' "$FILES"
  echo
  echo "(dry run - nothing sent)"
  exit 0
fi

# Refuse to clobber a target that is not ours. An existing deployment is fine;
# an unrelated directory is not.
ssh "$REMOTE" "
  set -e
  if [ -d '$TARGET' ] && [ -n \"\$(ls -A '$TARGET' 2>/dev/null)\" ]; then
    if [ ! -f '$TARGET/docker-compose.prod.yml' ] && [ ! -d '$TARGET/.git' ]; then
      echo 'REFUSED: $TARGET exists, is not empty, and does not look like this project.' >&2
      echo 'Move it aside or choose another target.' >&2
      exit 1
    fi
  fi
  mkdir -p '$TARGET'
"

# .env.prod on the server holds generated secrets - never overwrite it.
git ls-files -z \
  | tar --null -T - -czf - \
  | ssh "$REMOTE" "tar -xzf - -C '$TARGET' --exclude='.env.prod'"

ssh "$REMOTE" "chmod +x '$TARGET/deploy.sh' '$TARGET/deploy/'*.sh 2>/dev/null || true"

cat <<EOF

Done. On the server:

  cd $TARGET
  bash deploy/preflight.sh          # what is already running on this host
  bash deploy.sh --bootstrap        # deploy, then create the 3 logins + 1 vehicle

EOF
