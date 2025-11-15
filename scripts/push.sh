#!/usr/bin/env bash
#
# Push local commits to GitHub.
# Usage: ./scripts/push.sh "commit message"

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 \"commit message\"" >&2
  exit 1
fi

COMMIT_MSG="$1"

git add .
git commit -m "$COMMIT_MSG"
git push origin main
echo "Changes pushed with message: $COMMIT_MSG"