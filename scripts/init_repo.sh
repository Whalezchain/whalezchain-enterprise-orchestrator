#!/usr/bin/env bash
#
# Initialize a new GitHub repository with the current project files.
# Usage: ./scripts/init_repo.sh <org>/<repo>

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <org>/<repo>" >&2
  exit 1
fi

REPO="$1"

gh repo create "$REPO" --public --source . --remote origin --push
echo "Repository $REPO created and initial commit pushed."