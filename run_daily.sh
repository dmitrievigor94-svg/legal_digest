#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"
source .venv/bin/activate

set -a
source .env
set +a

python -m app.send_daily_digest