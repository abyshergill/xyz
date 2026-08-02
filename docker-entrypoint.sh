#!/bin/sh
# Runs automatically every time the app container starts: applies
# migrations, collects static files, then hands off to whatever CMD was
# given (gunicorn by default).
#
# Using SQLite by default, so there's no database server to wait for. If
# you've switched to PostgreSQL (see README.md "Switching this Docker
# setup to PostgreSQL"), add a wait-for-postgres step here before
# `migrate` runs, so the app doesn't start before the db container is
# ready to accept connections.
set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

exec "$@"
