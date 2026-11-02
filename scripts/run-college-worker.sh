#!/usr/bin/env bash
# Run inside the college VDI: the GPU worker for jobs started with "Run on: College GPU".
# Usage: bash scripts/run-college-worker.sh <laptop IP> [port]
# The worker token is read without echo (or from NAZAR_WORKER_TOKEN); it is never printed.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -lt 1 ]; then
  echo "Usage: bash scripts/run-college-worker.sh <laptop IP> [port]" >&2
  exit 2
fi
api="http://$1:${2:-8000}"

if ! curl -sS -f -o /dev/null --max-time 5 "$api/api/health"; then
  echo "Cannot reach $api from this VDI. Check run-college.bat is in Online mode, the IP," >&2
  echo "and the laptop firewall; otherwise use Bundle mode." >&2
  exit 1
fi

if [ -z "${NAZAR_WORKER_TOKEN:-}" ]; then
  read -r -s -p "NAZAR_WORKER_TOKEN (input hidden): " NAZAR_WORKER_TOKEN
  echo
fi
export NAZAR_WORKER_TOKEN

exec uv run --package nazar-worker nazar-worker run \
  --api "$api" --modes standard --location college
