#!/bin/sh
# Runs automatically every time the app container starts: waits for
# PostgreSQL to accept connections, applies migrations, collects static
# files, then hands off to whatever CMD was given (gunicorn by default).
set -e

if [ "${DJANGO_USE_POSTGRES}" = "True" ] || [ "${DJANGO_USE_POSTGRES}" = "true" ]; then
  echo "Waiting for PostgreSQL at ${DJANGO_DB_HOST:-db}:${DJANGO_DB_PORT:-5432}..."
  until python -c "
import os, sys, socket
host = os.environ.get('DJANGO_DB_HOST', 'db')
port = int(os.environ.get('DJANGO_DB_PORT', '5432'))
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(2)
try:
    s.connect((host, port))
    s.close()
except OSError:
    sys.exit(1)
"; do
    echo "  ...still waiting"
    sleep 2
  done
  echo "PostgreSQL is up."
fi

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

exec "$@"
