#!/usr/bin/env bash
set -euo pipefail

REPO_NAME="Halo-CTL"
APP_DIR="${HOME}/${REPO_NAME}"

if [[ ! -d "$APP_DIR" ]]; then
  echo "Not found: ${APP_DIR}" >&2
  exit 0
fi

cd "$APP_DIR"

if command -v docker >/dev/null 2>&1; then
  if docker compose version >/dev/null 2>&1; then
    docker compose down --remove-orphans || true
  fi
fi

echo "Removed containers. Directory kept: ${APP_DIR}"
echo "To fully remove files: rm -rf ${APP_DIR}"
