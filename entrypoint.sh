#!/bin/sh
set -e

alembic upgrade head
python -m app.db.seed

exec "$@"
