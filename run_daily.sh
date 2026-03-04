#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "=== RUN $(date "+%Y-%m-%dT%H:%M:%S") ==="
echo "PWD=$(pwd)"

source .venv/bin/activate

set -a
source .env
set +a

echo "PY=$(which python)"
python -V

python -m app.send_daily_digest

echo "=== DONE $(date "+%Y-%m-%dT%H:%M:%S") ==="