#!/bin/sh
set -eu

# Autoscaled deployments run migrations once as a release job, before traffic.
# Render retains the existing default until that release job is configured.
python -m src.db.wait_ready
case "${RUN_STARTUP_MIGRATIONS:-true}" in
  true) python -m alembic upgrade head ;;
  false) ;;
  *) echo "RUN_STARTUP_MIGRATIONS must be true or false" >&2; exit 1 ;;
esac
exec python -m uvicorn src.main:app --host 0.0.0.0 --port "${PORT:-8000}"
