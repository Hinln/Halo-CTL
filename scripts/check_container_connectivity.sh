#!/usr/bin/env bash
set -euo pipefail

FROM=""
TO=()

usage() {
  echo "usage: $0 --from <container> --to <host:port> [--to <host:port> ...]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      FROM="$2"
      shift 2
      ;;
    --to)
      TO+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown arg: $1" >&2
      usage
      exit 2
      ;;
  esac
done

if [[ -z "$FROM" || ${#TO[@]} -eq 0 ]]; then
  usage
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found" >&2
  exit 1
fi

fail=0

for target in "${TO[@]}"; do
  host="${target%%:*}"
  port="${target##*:}"
  if [[ -z "$host" || -z "$port" || "$host" == "$port" ]]; then
    echo "FAIL input target=${target}" >&2
    fail=1
    continue
  fi

  if docker exec "$FROM" sh -lc "getent hosts '$host' >/dev/null 2>&1"; then
    echo "OK dns from=${FROM} host=${host}"
  else
    echo "FAIL dns from=${FROM} host=${host}" >&2
    fail=1
  fi

  if docker exec "$FROM" sh -lc "nc -vz -w 2 '$host' '$port' >/dev/null 2>&1"; then
    echo "OK tcp from=${FROM} to=${host}:${port}"
  else
    echo "FAIL tcp from=${FROM} to=${host}:${port}" >&2
    fail=1
  fi
done

exit "$fail"

