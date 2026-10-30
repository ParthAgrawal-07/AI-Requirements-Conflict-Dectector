#!/bin/sh
# Runs once per container start, before the API or worker process takes over (`exec "$@"`
# replaces this script's process rather than forking, so signals/PID 1 behave correctly).
set -eu

echo "entrypoint: waiting for the database to accept connections..."
python -c "
import sys, time
from sqlalchemy import create_engine, text
from app.core.config import get_settings

engine = create_engine(get_settings().database_url)
for attempt in range(30):
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        break
    except Exception as exc:
        print(f'  ({attempt + 1}/30) not ready yet: {exc}', file=sys.stderr)
        time.sleep(2)
else:
    print('entrypoint: database never became ready', file=sys.stderr)
    sys.exit(1)
"

# RUN_MIGRATIONS=0 skips this — set on the worker service so two containers starting
# together can't both run `alembic upgrade head` at once; the API container migrates.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    echo "entrypoint: running database migrations..."
    alembic upgrade head
fi

exec "$@"
