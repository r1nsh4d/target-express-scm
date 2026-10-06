#!/usr/bin/env bash
#
# Convert every tracked text file to LF line endings.
#
#   bash deploy/fix-line-endings.sh          convert
#   bash deploy/fix-line-endings.sh --check  report only, change nothing
#
# Why this exists: the project is edited on Windows and runs on Linux. Git's
# Windows default (core.autocrlf=true) rewrites LF to CRLF on checkout. On Linux
# a trailing carriage return is a character, not whitespace:
#
#   bash   reads  #!/usr/bin/env bash\r   -> "$'\r': command not found"
#   dotenv reads  TX_HTTP_PORT=18080\r    -> a port literally named "18080\r"
#   docker reads  a CRLF entrypoint       -> fails inside the image, no message
#
# .gitattributes pins the tree to LF for future checkouts. This script repairs a
# tree that was already checked out before that file existed.
#
# Binary files are skipped by extension. .bat and .ps1 are skipped too — they
# are only ever run by Windows, which wants CRLF.

set -euo pipefail
cd "$(dirname "$0")/.."

CHECK_ONLY=0
case "${1:-}" in
  --check) CHECK_ONLY=1 ;;
  "") ;;
  -h|--help) sed -n '2,24p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "Unknown option '$1' - try --check or --help" >&2; exit 1 ;;
esac

command -v git >/dev/null || { echo "git is required (it selects the files)" >&2; exit 1; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "Not a git repository" >&2; exit 1; }

changed=0
scanned=0

while IFS= read -r f; do
  case "$f" in
    *.png|*.jpg|*.jpeg|*.gif|*.ico|*.webp|*.pdf|*.woff|*.woff2|*.ttf|*.otf) continue ;;
    *.bat|*.ps1) continue ;;
  esac
  [ -f "$f" ] || continue
  scanned=$((scanned + 1))

  grep -qU $'\r' "$f" 2>/dev/null || continue

  if [ "$CHECK_ONLY" = "1" ]; then
    echo "  CRLF  $f"
  else
    # Only CRLF -> LF. A lone CR is left alone: in a text file that is data,
    # not a line ending, and rewriting it would corrupt the content.
    tmp="${f}.lf.$$"
    tr -d '\r' < "$f" > "$tmp" && mv "$tmp" "$f"
    echo "  fixed $f"
  fi
  changed=$((changed + 1))
done <<< "$(git ls-files)"

echo
if [ "$changed" = "0" ]; then
  echo "  All $scanned text files already use LF."
elif [ "$CHECK_ONLY" = "1" ]; then
  echo "  $changed of $scanned files have CRLF. Run without --check to fix them."
  exit 1
else
  echo "  Converted $changed of $scanned files to LF."
  echo "  Commit these, and .gitattributes will keep them that way."
fi
