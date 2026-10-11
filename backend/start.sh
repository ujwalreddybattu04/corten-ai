#!/bin/sh
set -eu

# Fail deployment if the schema cannot be created or upgraded.
python -m src.db.wait_ready
python -m alembic upgrade head
exec python -m uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
